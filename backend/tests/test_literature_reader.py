from __future__ import annotations

import io
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from hypoweaver.literature_reader import (
    LiteratureAskRequest,
    LiteratureDocumentError,
    LiteratureDocumentStore,
    ask_literature,
)
from hypoweaver.runtime_config import EffectiveRuntimeConfig


def _pdf_bytes(*page_texts: str) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        resources = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        page[NameObject("/Resources")] = resources
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Title": "Original PDF Test", "/Author": "Source Author"})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def _chunks(data: bytes):
    midpoint = max(1, len(data) // 2)
    yield data[:midpoint]
    yield data[midpoint:]


def _config(api_key: str | None = "secret-key") -> EffectiveRuntimeConfig:
    return EffectiveRuntimeConfig(
        qwen_api_key=api_key,
        qwen_model="qwen3.7-plus",
        qwen_base_url="https://dashscope.example/compatible-mode/v1",
        research_engine_url=None,
        research_engine_token=None,
        sources={
            "qwen_api_key": "environment" if api_key else "missing",
            "qwen_model": "file",
            "qwen_base_url": "file",
            "research_engine_url": "missing",
            "research_engine_token": "missing",
        },
    )


class LiteratureReaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        test_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        self.test_dir = test_root / uuid4().hex
        self.test_dir.mkdir(parents=True, exist_ok=False)
        self.store = LiteratureDocumentStore(self.test_dir / "literature")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_saves_original_pdf_and_page_text_with_hashes(self) -> None:
        source = _pdf_bytes("Original PDF page one.", "Original PDF page two.")
        document = await self.store.save("paper.pdf", _chunks(source))

        self.assertEqual(document.filename, "paper.pdf")
        self.assertEqual(document.title, "Original PDF Test")
        self.assertEqual(document.page_count, 2)
        self.assertEqual(document.extracted_page_count, 2)
        self.assertEqual(self.store.get_original_pdf(document.document_id).read_bytes(), source)
        self.assertIn("Original PDF page one.", self.store.get_page(document.document_id, 1).text)
        self.assertEqual(len(document.pages[0].text_sha256), 64)
        self.assertTrue(self.store.render_page_png(document.document_id, 1).startswith(b"\x89PNG\r\n\x1a\n"))

    async def test_rejects_non_pdf_and_pdf_without_text_layer(self) -> None:
        with self.assertRaisesRegex(LiteratureDocumentError, "文件内容不是有效 PDF"):
            await self.store.save("fake.pdf", _chunks(b"not a pdf"))

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesRegex(LiteratureDocumentError, "没有可读取的原文文本层"):
            await self.store.save("scan.pdf", _chunks(buffer.getvalue()))

    async def test_deletes_only_the_selected_original_pdf(self) -> None:
        first = await self.store.save("first.pdf", _chunks(_pdf_bytes("First source.")))
        second = await self.store.save("second.pdf", _chunks(_pdf_bytes("Second source.")))

        deleted = await self.store.delete(first.document_id)

        self.assertEqual(deleted.document_id, first.document_id)
        self.assertEqual(
            [item.document_id for item in self.store.list_documents()],
            [second.document_id],
        )
        with self.assertRaisesRegex(LiteratureDocumentError, "找不到"):
            self.store.get_document(first.document_id)
        self.assertEqual(self.store.get_document(second.document_id).document_id, second.document_id)

    async def test_qwen_receives_server_owned_original_pages_and_returns_page_citations(self) -> None:
        source = _pdf_bytes("Original finding on page one.", "Original method on page two.")
        document = await self.store.save("paper.pdf", _chunks(source))

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertIn("Original finding on page one.", serialized)
            self.assertIn("Original method on page two.", serialized)
            self.assertIn(document.sha256, serialized)
            self.assertNotIn("secret-key", serialized)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "结论来自原始文本[原文第 1 页]，方法见[原文第 2 页]。"
                            }
                        }
                    ]
                },
            )

        response = await ask_literature(
            document.document_id,
            LiteratureAskRequest(question="原文说了什么？"),
            _config(),
            self.store,
            transport=httpx.MockTransport(handler),
        )
        self.assertEqual(response.cited_pages, [1, 2])
        self.assertEqual(response.used_pages, [1, 2])
        self.assertEqual(response.document_sha256, document.sha256)

    async def test_requires_qwen_key(self) -> None:
        document = await self.store.save("paper.pdf", _chunks(_pdf_bytes("Original source.")))
        with self.assertRaisesRegex(RuntimeError, "API Key"):
            await ask_literature(
                document.document_id,
                LiteratureAskRequest(question="原文说了什么？"),
                _config(None),
                self.store,
            )


if __name__ == "__main__":
    unittest.main()
