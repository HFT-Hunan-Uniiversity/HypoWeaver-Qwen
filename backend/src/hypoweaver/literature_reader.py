"""Original-PDF storage and bounded Qwen reading.

The server owns the PDF and its extracted text layer. The browser only sends a
document id, an optional page scope, and a question; it cannot substitute
summaries or rewritten passages for the source document.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterable
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pymupdf
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pypdf import PdfReader

from .runtime_config import EffectiveRuntimeConfig
from .storage_limits import (
    LOCAL_VAR_QUOTA_BYTES,
    MAX_UPLOAD_DIRECTORIES,
    LocalStorageLimitError,
    directory_size_bytes,
    ensure_local_storage_capacity,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LITERATURE_ROOT = PROJECT_ROOT / "backend" / "var" / "literature"
SHOWCASE_LITERATURE_ROOT = PROJECT_ROOT / "backend" / "assets" / "showcase_literature"
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 1000
MAX_CONTEXT_CHARACTERS = 500_000
_DOCUMENT_ID_PATTERN = re.compile(r"^pdf_[0-9a-f]{32}$")
_CITATION_PATTERN = re.compile(r"\[原文第\s*(\d+)\s*页\]")

SHOWCASE_LITERATURE = (
    {
        "filename": "green-finance-environmental-violations-jfr.pdf",
        "title": "绿色金融政策抑制了企业的环境违规吗？——基于绿色金融改革创新试验区的一项准自然实验",
        "author": "杜兴强、谢裕慧、曾泉",
        "publication_year": 2024,
        "journal": "金融研究",
        "doi": None,
        "source_url": "http://www.jryj.org.cn/CN/Y2024/V527/I5/132",
        "license": "期刊官网公开全文",
        "showcase_order": 1,
    },
    {
        "filename": "corporate-green-bonds-jfe.pdf",
        "title": "Corporate Green Bonds",
        "author": "Caroline Flammer",
        "publication_year": 2021,
        "journal": "Journal of Financial Economics",
        "doi": "10.1016/j.jfineco.2021.01.010",
        "source_url": "https://sites.bu.edu/cflammer/files/2021/10/Corporate-Green-Bonds_Flammer_JFE2021.pdf",
        "license": "作者公开全文",
        "showcase_order": 2,
    },
    {
        "filename": "carbon-risk-jfe.pdf",
        "title": "Do Investors Care about Carbon Risk?",
        "author": "Patrick Bolton and Marcin Kacperczyk",
        "publication_year": 2021,
        "journal": "Journal of Financial Economics",
        "doi": "10.1016/j.jfineco.2021.05.008",
        "source_url": "https://www.nber.org/papers/w26968",
        "license": "NBER 公开工作论文",
        "showcase_order": 3,
    },
    {
        "filename": "green-finance-air-quality.pdf",
        "title": "The Impact of Green Financial Policy on the Regional Economic Development Level and AQI—Evidence from Zhejiang Province, China",
        "author": "Min-Xing Wang, Lufei Huang and Zhen-Ming Chen",
        "publication_year": 2023,
        "journal": "Sustainability",
        "doi": "10.3390/su15054068",
        "source_url": "https://doi.org/10.3390/su15054068",
        "license": "CC BY 4.0",
        "showcase_order": 4,
    },
    {
        "filename": "green-finance-green-innovation.pdf",
        "title": "The Impact of the Green Finance Reform and Innovation Pilot Zone on the Green Innovation—Evidence from China",
        "author": "Yanbo Zhang and Xiang Li",
        "publication_year": 2022,
        "journal": "International Journal of Environmental Research and Public Health",
        "doi": "10.3390/ijerph19127330",
        "source_url": "https://doi.org/10.3390/ijerph19127330",
        "license": "CC BY 4.0",
        "showcase_order": 5,
    },
    {
        "filename": "green-finance-enterprise-technology.pdf",
        "title": "How Does Green Finance Reform Affect Enterprise Green Technology Innovation? Evidence from China",
        "author": "Na Lu, Jiahui Wu and Ziming Liu",
        "publication_year": 2022,
        "journal": "Sustainability",
        "doi": "10.3390/su14169865",
        "source_url": "https://doi.org/10.3390/su14169865",
        "license": "CC BY 4.0",
        "showcase_order": 6,
    },
)


class LiteratureDocumentError(ValueError):
    pass


class LiteraturePageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    character_count: int = Field(ge=0)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LiteraturePage(LiteraturePageSummary):
    text: str


class LiteratureDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^pdf_[0-9a-f]{32}$")
    filename: str
    title: str
    author: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    page_count: int = Field(ge=1)
    extracted_page_count: int = Field(ge=1)
    extracted_character_count: int = Field(ge=1)
    uploaded_at: str
    pages: list[LiteraturePageSummary]
    is_showcase: bool = False
    publication_year: int | None = None
    journal: str | None = None
    doi: str | None = None
    source_url: str | None = None
    license: str | None = None
    showcase_order: int | None = None


class LiteratureAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=2000)
    page_numbers: list[int] | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("page_numbers")
    @classmethod
    def unique_positive_pages(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(page < 1 for page in value):
            raise ValueError("page numbers must be positive")
        if len(set(value)) != len(value):
            raise ValueError("page numbers must be unique")
        return value


class LiteratureAskResponse(BaseModel):
    document_id: str
    document_sha256: str
    answer: str
    cited_pages: list[int]
    model: str
    used_pages: list[int]
    used_characters: int


class LiteratureDocumentStore:
    """Private local store for immutable original PDFs and page text layers."""

    def __init__(self, root: Path | None = None) -> None:
        configured_root = os.getenv("HYPOWEAVER_LITERATURE_ROOT")
        self.root = (
            Path(configured_root).expanduser()
            if root is None and configured_root
            else (root or DEFAULT_LITERATURE_ROOT)
        )
        self._save_lock = asyncio.Lock()

    async def save(self, filename: str, chunks: AsyncIterable[bytes]) -> LiteratureDocument:
        async with self._save_lock:
            return await self._save(filename, chunks)

    async def _save(self, filename: str, chunks: AsyncIterable[bytes]) -> LiteratureDocument:
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename or Path(safe_name).suffix.casefold() != ".pdf":
            raise LiteratureDocumentError("只接受单个 PDF 原文文件。")

        self.root.mkdir(parents=True, exist_ok=True)
        document_count = sum(1 for path in self.root.iterdir() if path.is_dir())
        if document_count >= MAX_UPLOAD_DIRECTORIES:
            raise LocalStorageLimitError(
                "literature_directories",
                document_count,
                MAX_UPLOAD_DIRECTORIES,
            )
        ensure_local_storage_capacity(self.root.parent)
        baseline_size = directory_size_bytes(self.root.parent)

        document_id = f"pdf_{uuid4().hex}"
        document_dir = self.root / document_id
        document_dir.mkdir(parents=True)
        self._harden_permissions(document_dir, 0o700)
        pdf_path = document_dir / "original.pdf"
        size = 0
        digest = hashlib.sha256()
        try:
            with pdf_path.open("xb") as handle:
                self._harden_permissions(pdf_path, 0o600)
                async for chunk in chunks:
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise LiteratureDocumentError("PDF 超过 100 MiB 上传限制。")
                    projected_size = baseline_size + size
                    if projected_size > LOCAL_VAR_QUOTA_BYTES:
                        raise LocalStorageLimitError(
                            "backend_var_bytes",
                            projected_size,
                            LOCAL_VAR_QUOTA_BYTES,
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise LiteratureDocumentError("上传的 PDF 为空。")
            with pdf_path.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise LiteratureDocumentError("文件扩展名是 PDF，但文件内容不是有效 PDF。")

            document = await asyncio.to_thread(
                self._extract_original_text,
                document_id,
                safe_name,
                pdf_path,
                size,
                digest.hexdigest(),
            )
            self._write_manifest(document_dir / "manifest.json", document)
            return document
        except Exception:
            if document_dir.exists() and document_dir.parent.resolve() == self.root.resolve():
                shutil.rmtree(document_dir)
            raise

    def install_showcase_documents(self) -> list[LiteratureDocument]:
        """Install bundled open-access PDFs into the private reader store once.

        The deterministic id is derived from the immutable PDF hash, so normal
        application restarts do not duplicate the showcase shelf.
        """
        if not SHOWCASE_LITERATURE_ROOT.is_dir():
            return []
        self.root.mkdir(parents=True, exist_ok=True)
        installed: list[LiteratureDocument] = []
        for metadata in SHOWCASE_LITERATURE:
            asset_path = SHOWCASE_LITERATURE_ROOT / str(metadata["filename"])
            if not asset_path.is_file():
                continue
            size_bytes = asset_path.stat().st_size
            if size_bytes <= 0 or size_bytes > MAX_PDF_BYTES:
                continue
            sha256 = self._sha256_file(asset_path)
            document_id = f"pdf_{sha256[:32]}"
            document_dir = self.root / document_id
            manifest_path = document_dir / "manifest.json"
            if manifest_path.is_file():
                try:
                    document = self._load_manifest(manifest_path).model_copy(update={
                        "title": metadata["title"],
                        "author": metadata["author"],
                        "is_showcase": True,
                        "publication_year": metadata["publication_year"],
                        "journal": metadata["journal"],
                        "doi": metadata["doi"],
                        "source_url": metadata["source_url"],
                        "license": metadata["license"],
                        "showcase_order": metadata["showcase_order"],
                    })
                    self._write_manifest(manifest_path, document)
                    installed.append(document)
                    continue
                except (OSError, ValueError):
                    pass

            ensure_local_storage_capacity(self.root.parent)
            if document_dir.exists():
                shutil.rmtree(document_dir)
            document_dir.mkdir(parents=True)
            self._harden_permissions(document_dir, 0o700)
            pdf_path = document_dir / "original.pdf"
            try:
                shutil.copyfile(asset_path, pdf_path)
                self._harden_permissions(pdf_path, 0o600)
                document = self._extract_original_text(
                    document_id,
                    str(metadata["filename"]),
                    pdf_path,
                    size_bytes,
                    sha256,
                ).model_copy(update={
                    "title": metadata["title"],
                    "author": metadata["author"],
                    "is_showcase": True,
                    "publication_year": metadata["publication_year"],
                    "journal": metadata["journal"],
                    "doi": metadata["doi"],
                    "source_url": metadata["source_url"],
                    "license": metadata["license"],
                    "showcase_order": metadata["showcase_order"],
                })
                self._write_manifest(manifest_path, document)
                installed.append(document)
            except Exception:
                if document_dir.exists() and document_dir.parent.resolve() == self.root.resolve():
                    shutil.rmtree(document_dir)
                raise
        return sorted(installed, key=lambda item: item.showcase_order or 999)

    def list_documents(self) -> list[LiteratureDocument]:
        if not self.root.exists():
            return []
        documents: list[LiteratureDocument] = []
        for manifest_path in self.root.glob("pdf_*/manifest.json"):
            try:
                documents.append(self._load_manifest(manifest_path))
            except (OSError, ValueError):
                continue
        return sorted(documents, key=lambda item: item.uploaded_at, reverse=True)

    def get_document(self, document_id: str) -> LiteratureDocument:
        document_dir = self._document_dir(document_id)
        manifest_path = document_dir / "manifest.json"
        if not manifest_path.is_file():
            raise LiteratureDocumentError("找不到这篇原始 PDF。")
        return self._load_manifest(manifest_path)

    async def delete(self, document_id: str) -> LiteratureDocument:
        async with self._save_lock:
            document = self.get_document(document_id)
            if document.is_showcase:
                raise LiteratureDocumentError("内置展示论文不能删除。")
            document_dir = self._document_dir(document_id)
            await asyncio.to_thread(shutil.rmtree, document_dir)
            return document

    def get_original_pdf(self, document_id: str) -> Path:
        document_dir = self._document_dir(document_id)
        pdf_path = document_dir / "original.pdf"
        if not pdf_path.is_file():
            raise LiteratureDocumentError("原始 PDF 文件不可用。")
        document = self.get_document(document_id)
        digest = self._sha256_file(pdf_path)
        if digest != document.sha256:
            raise LiteratureDocumentError("原始 PDF 哈希校验失败。")
        return pdf_path

    def get_page(self, document_id: str, page_number: int) -> LiteraturePage:
        document = self.get_document(document_id)
        summary = next((item for item in document.pages if item.page_number == page_number), None)
        if summary is None:
            raise LiteratureDocumentError(f"原文不存在第 {page_number} 页。")
        page_path = self._document_dir(document_id) / "pages" / f"page-{page_number:04d}.txt"
        if not page_path.is_file():
            raise LiteratureDocumentError(f"第 {page_number} 页原文文本层不可用。")
        text = page_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != summary.text_sha256:
            raise LiteratureDocumentError(f"第 {page_number} 页原文哈希校验失败。")
        return LiteraturePage(**summary.model_dump(), text=text)

    def render_page_png(self, document_id: str, page_number: int) -> bytes:
        document = self.get_document(document_id)
        if page_number < 1 or page_number > document.page_count:
            raise LiteratureDocumentError(f"原文不存在第 {page_number} 页。")
        pdf_path = self.get_original_pdf(document_id)
        try:
            with pymupdf.open(pdf_path) as pdf:
                page = pdf.load_page(page_number - 1)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
                return pixmap.tobytes("png")
        except LiteratureDocumentError:
            raise
        except Exception as error:
            raise LiteratureDocumentError(f"无法渲染原始 PDF 第 {page_number} 页。") from error

    def get_pages(
        self,
        document_id: str,
        page_numbers: list[int] | None = None,
    ) -> list[LiteraturePage]:
        document = self.get_document(document_id)
        selected = page_numbers or [page.page_number for page in document.pages]
        return [self.get_page(document_id, page_number) for page_number in selected]

    def _extract_original_text(
        self,
        document_id: str,
        filename: str,
        pdf_path: Path,
        size_bytes: int,
        sha256: str,
    ) -> LiteratureDocument:
        try:
            reader = PdfReader(str(pdf_path), strict=False)
        except Exception as error:
            raise LiteratureDocumentError("PDF 解析失败，文件可能损坏。") from error
        if reader.is_encrypted:
            raise LiteratureDocumentError("暂不支持加密 PDF，请先移除密码后上传。")
        if not reader.pages or len(reader.pages) > MAX_PDF_PAGES:
            raise LiteratureDocumentError(f"PDF 页数必须在 1 到 {MAX_PDF_PAGES} 页之间。")

        pages_dir = pdf_path.parent / "pages"
        pages_dir.mkdir()
        self._harden_permissions(pages_dir, 0o700)
        page_summaries: list[LiteraturePageSummary] = []
        extracted_character_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            if "/Contents" not in page:
                text = ""
            else:
                try:
                    text = page.extract_text(extraction_mode="layout") or ""
                except TypeError:
                    text = page.extract_text() or ""
                except Exception as error:
                    raise LiteratureDocumentError(f"无法读取 PDF 第 {page_number} 页文本层。") from error
            page_path = pages_dir / f"page-{page_number:04d}.txt"
            page_path.write_text(text, encoding="utf-8")
            self._harden_permissions(page_path, 0o600)
            text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            page_summaries.append(
                LiteraturePageSummary(
                    page_number=page_number,
                    character_count=len(text),
                    text_sha256=text_sha256,
                )
            )
            extracted_character_count += len(text)

        extracted_pages = sum(1 for page in page_summaries if page.character_count > 0)
        if extracted_pages == 0 or extracted_character_count == 0:
            raise LiteratureDocumentError(
                "PDF 没有可读取的原文文本层；扫描件需要先完成 OCR，系统不会把空白页伪装成可读原文。"
            )

        metadata = reader.metadata
        metadata_title = str(metadata.title).strip() if metadata and metadata.title else ""
        metadata_author = str(metadata.author).strip() if metadata and metadata.author else None
        return LiteratureDocument(
            document_id=document_id,
            filename=filename,
            title=metadata_title or Path(filename).stem,
            author=metadata_author or None,
            sha256=sha256,
            size_bytes=size_bytes,
            page_count=len(reader.pages),
            extracted_page_count=extracted_pages,
            extracted_character_count=extracted_character_count,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            pages=page_summaries,
        )

    def _document_dir(self, document_id: str) -> Path:
        if not _DOCUMENT_ID_PATTERN.fullmatch(document_id):
            raise LiteratureDocumentError("无效的 PDF 文档 ID。")
        document_dir = (self.root / document_id).resolve()
        root = self.root.resolve()
        if document_dir.parent != root:
            raise LiteratureDocumentError("PDF 文档路径越界。")
        return document_dir

    @staticmethod
    def _load_manifest(path: Path) -> LiteratureDocument:
        return LiteratureDocument.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _harden_permissions(path: Path, mode: int) -> None:
        # Windows chmod only maps a small subset of POSIX modes and can make a
        # newly created directory unusable under inherited sandbox ACLs.
        if os.name != "nt":
            os.chmod(path, mode)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_manifest(path: Path, document: LiteratureDocument) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".manifest-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                if hasattr(os, "fchmod"):
                    os.fchmod(handle.fileno(), 0o600)
                json.dump(document.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            LiteratureDocumentStore._harden_permissions(path, 0o600)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()


async def ask_literature(
    document_id: str,
    request: LiteratureAskRequest,
    config: EffectiveRuntimeConfig,
    store: LiteratureDocumentStore,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LiteratureAskResponse:
    if not config.qwen_api_key:
        raise RuntimeError("尚未配置 Qwen API Key，无法使用 AI 原文阅读。")

    document = store.get_document(document_id)
    pages = store.get_pages(document_id, request.page_numbers)
    used_characters = sum(len(page.text) for page in pages)
    if used_characters > MAX_CONTEXT_CHARACTERS:
        raise LiteratureDocumentError(
            f"所选原文共 {used_characters} 个字符，超过单次 {MAX_CONTEXT_CHARACTERS} 字符限制；"
            "请选择具体页码后再提问，系统不会静默截断原文。"
        )

    original_text = "\n\n".join(
        f"--- [原文第 {page.page_number} 页 | text_sha256={page.text_sha256}] ---\n{page.text}"
        for page in pages
    )
    system_prompt = (
        "你是严谨的论文原文阅读助手。以下内容直接来自用户上传 PDF 的逐页文本层，"
        "不是摘要、改写稿或检索片段。只能依据这些原文回答，不能补充原文中没有的事实。"
        "每个关键判断后必须引用形如[原文第 3 页]的页码；无法从原文确认时直接说明。"
        "区分作者原话、你的概括和你的推断。不得伪造章节、段落或参考文献。"
    )
    user_prompt = (
        f"原始文件：{document.filename}\n"
        f"标题：{document.title}\n"
        f"PDF SHA-256：{document.sha256}\n"
        f"问题：{request.question}\n\n"
        f"以下为所选 PDF 原文文本层：\n{original_text}"
    )
    payload = {
        "model": config.qwen_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 1200,
        "enable_thinking": False,
    }
    url = f"{config.qwen_base_url}/chat/completions"
    trust_env = urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}
    try:
        async with httpx.AsyncClient(timeout=60, transport=transport, trust_env=trust_env) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {config.qwen_api_key}"},
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        answer = str(body["choices"][0]["message"]["content"]).strip()
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code in {401, 403}:
            message = "Qwen 鉴权失败，请核对 API Key 所属地域与 API Host 是否一致。"
        elif status_code == 404:
            message = "Qwen 模型或 API 地址不存在，请核对模型 ID 与 API Host。"
        else:
            message = f"Qwen 原文阅读调用返回 HTTP {status_code}。"
        raise RuntimeError(message) from error
    except httpx.RequestError as error:
        raise RuntimeError(
            f"Qwen 网络连接失败（{type(error).__name__}），请检查代理、TLS 与 API Host。"
        ) from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError("Qwen 返回格式异常，未能读取原文回答。") from error

    if not answer:
        raise RuntimeError("Qwen 返回了空的原文阅读回答。")
    cited_pages = list(dict.fromkeys(int(item) for item in _CITATION_PATTERN.findall(answer)))
    return LiteratureAskResponse(
        document_id=document.document_id,
        document_sha256=document.sha256,
        answer=answer,
        cited_pages=cited_pages,
        model=config.qwen_model,
        used_pages=[page.page_number for page in pages],
        used_characters=used_characters,
    )
