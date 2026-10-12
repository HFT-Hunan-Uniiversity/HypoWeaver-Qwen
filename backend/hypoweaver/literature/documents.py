import json
import re
from pathlib import Path
from urllib.parse import quote
import httpx
import pymupdf
from pydantic import BaseModel, Field, ValidationError
from ..errors import AppError
from .sources import crossref_card, doi_normalize

class LocalCard(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    cited_by: int | None = None
    abstract: str | None = None
    fulltext_excerpt: str | None = None
    concepts: list[str] = Field(default_factory=list)


MAX_PDF_BYTES = 30 * 1024 * 1024


def extract_pdf(data, name):
    if len(data) > MAX_PDF_BYTES:
        raise AppError("pdf_too_large", "PDF 不得超过 30 MB")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise AppError("pdf_locked", "PDF 已加密，请先解锁后上传")
            text = "\n".join(doc[i].get_text() for i in range(min(len(doc), 100)))[:100000]
            first_page = doc[0].get_text() if len(doc) else ""
            metadata = doc.metadata or {}
    except AppError:
        raise
    except Exception as exc:
        raise AppError("pdf_invalid", "无法读取 PDF，请确认文件完整且格式正确") from exc
    if not text.strip():
        raise AppError("pdf_no_text", "PDF 没有可提取文本；扫描件请先完成 OCR 再上传")
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 5]
    title = metadata.get("title") or (lines[0] if lines else Path(name).stem)
    doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", first_page, re.I)
    date = re.search(r"(?:19|20)\d{2}", text[:5000])
    return dict(source="pdf", sources=["pdf"], title=title[:2000], year=int(date[0]) if date else None,
                authors=[metadata["author"]] if metadata.get("author") else [], doi=doi_normalize(doi[0].rstrip('.,;') if doi else None),
                venue="", cited_by=None, abstract=None, fulltext_excerpt=text[:12000], concepts=[])


async def enrich_pdf(card, settings):
    if not card["doi"]:
        return card, "未检测到 DOI，请检查并编辑标题和年份"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(settings.crossref_url.rstrip('/') + '/' + quote(card['doi'], safe=''),
                                        params={"mailto": settings.contact_email} if settings.contact_email else {})
            response.raise_for_status()
            metadata = crossref_card(response.json()["message"])
        for key in ["title", "year", "authors", "venue", "abstract", "concepts", "cited_by"]:
            if metadata.get(key):
                card[key] = metadata[key]
        card["sources"].append("crossref")
        return card, "已通过 DOI 补齐元数据，请核对"
    except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        return card, f"Crossref 元数据补齐失败（{type(exc).__name__}），已保留 PDF 摘录，可手动编辑"


def search_local(directory, queries):
    root = Path(directory).expanduser()
    if not root.is_dir():
        return [], {"status": "failed", "reason": "本地文献库目录不存在", "hits": 0}
    cards, errors = [], []
    keywords = {term.lower() for q in queries for term in re.findall(r"[\w]+", q["text"]) if len(term)>1}
    library = root / "library.jsonl"
    if library.is_file():
        if library.stat().st_size > 10 * 1024 * 1024:
            return [], {"status":"failed", "reason":"library.jsonl 超过 10 MB，请缩小文献库", "hits":0}
        try:
            with library.open(encoding="utf-8") as stream:
                for index, line in enumerate(stream):
                    if index >= 2000:
                        errors.append("本次仅读取前 2000 条本地文献")
                        break
                    if not line.strip():
                        continue
                    try:
                        allowed = LocalCard.model_validate_json(line).model_dump()
                        cards.append({**allowed, "source":"local", "sources":["local"]})
                    except ValidationError:
                        errors.append(f"本地索引第 {index + 1} 行格式无效，已跳过")
        except (ValueError, OSError) as exc:
            errors.append(f"本地索引读取失败（{type(exc).__name__}）")
    else:
        for index, path in enumerate(root.glob('*.pdf')):
            if index >= 200:
                errors.append("本次仅读取前 200 个 PDF")
                break
            try:
                if path.stat().st_size > MAX_PDF_BYTES:
                    errors.append(f"文件超过 30 MB：{path.name}")
                    continue
                card=extract_pdf(path.read_bytes(), path.name)
                card.update(source="local", sources=["local"])
                cards.append(card)
            except (OSError, AppError) as exc:
                errors.append(f"无法提取：{path.name}")
    matched = [card for card in cards if any(k in (card.get('title','')+' '+(card.get('abstract') or '')+' '+(card.get('fulltext_excerpt') or '')).lower() for k in keywords)]
    return matched, {"status":"failed" if errors else "ok", "reason":"; ".join(errors[:10]), "hits":len(matched)}
