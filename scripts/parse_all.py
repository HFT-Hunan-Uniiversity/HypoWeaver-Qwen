# ============================================================================
# 批量文档解析 — scripts/parse_all.py
# ============================================================================
# 遍历 input/ 全部 PDF/TXT/XML，调用 MinerU 解析 + 清洗 + 元数据。
#
# 支持格式自动检测:
#   .pdf  → MinerU 云 API
#   .txt  → 直接读取，跳过 MinerU
#   .xml  → 直接读取，跳过 MinerU
#
# 断点续跑: 已解析的 doc_id 跳过（cleaned_meta/*.json 存在即视为已处理）
#
# 用法:
#   python scripts/parse_all.py --input ./input --output ./cleaned \
#       --meta-output ./cleaned_meta --mode incremental
# ============================================================================

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse.adapters.mineru_api import parse_pdf, get_quota_summary, get_pdf_page_count
from src.parse.clean.cleaning import clean_mineru_markdown
from src.parse.ir.parsed_doc import ParsedDoc
from src.parse.adapters.metadata_extractor import extract_metadata
from src.parse.config.doc_types import infer_doc_type
from src.status import mark_kg_pending  # 重置 KG 状态

import hashlib


def _compute_md5(filepath: str) -> str:
    """计算文件 MD5 哈希。"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_filename(filename: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符。"""
    name = Path(filename).stem
    name = "".join(c for c in name if c.isalnum() or c in "-_ ")
    name = name.strip()[:max_len]
    return name


def _collect_input_files(input_dir: Path) -> list:
    """收集 input/ 下所有可解析文件，按格式分类。

    返回:
      [(相对路径, 格式), ...] 按 PDF → TXT → XML 排序。
    """
    pdfs = []
    txts = []
    xmls = []

    for f in input_dir.rglob("*"):
        if not f.is_file():
            continue
        suffix = f.suffix.lower()
        if suffix == ".pdf":
            pdfs.append((f, "pdf"))
        elif suffix == ".txt":
            txts.append((f, "txt"))
        elif suffix == ".xml":
            xmls.append((f, "xml"))

    # PDF 优先处理（英文在前，中文在后）
    en_pdfs = [p for p in pdfs if not any('一' <= c <= '鿿' for c in p[0].name)]
    cn_pdfs = [p for p in pdfs if any('一' <= c <= '鿿' for c in p[0].name)]
    return sorted(en_pdfs) + sorted(cn_pdfs) + sorted(txts) + sorted(xmls)


def process_pdf(
    pdf_path: Path,
    index: int,
    total: int,
    cleaned_dir: Path,
    meta_dir: Path,
    skip_done: bool,
) -> Optional[str]:
    """处理单个 PDF: MinerU 解析 + 清洗 + 元数据 + ParsedDoc。

    返回 doc_id（成功）或 None（失败）。
    """
    doc_id = _safe_filename(pdf_path.stem)
    cleaned_md_path = cleaned_dir / f"{doc_id}.md"
    cleaned_meta_path = meta_dir / f"{doc_id}.json"

    # 断点续跑
    if skip_done and cleaned_meta_path.exists():
        print(f"[{index}/{total}] ⏭️  已处理, 跳过: {pdf_path.name[:50]}")
        return doc_id

    print(f"\n[{index}/{total}] {'='*55}")
    print(f"[{index}/{total}] 📄 PDF: {pdf_path.name[:60]}")

    # 1. 文档类型推断
    doc_type, doc_type_cn = infer_doc_type(pdf_path.name, str(pdf_path))
    print(f"[{index}/{total}] 🏷️  类型: {doc_type} ({doc_type_cn})")

    # 2. 页数与配额检查
    try:
        pages = get_pdf_page_count(str(pdf_path))
        print(f"[{index}/{total}]   页数: {pages}")
        print(f"[{index}/{total}]   {get_quota_summary()}")
    except Exception as e:
        print(f"[{index}/{total}]   ⚠️  页数获取失败: {e}")
        pages = 0

    # 3. MinerU 解析
    try:
        result = parse_pdf(str(pdf_path))
        if result is None:
            print(f"[{index}/{total}] ❌ MinerU 解析失败，跳过")
            return None
        md_text = result["markdown"]
        content_list = result["content_list"]
        print(f"[{index}/{total}] ✅ MinerU: {len(md_text)} 字符, content_list {len(content_list)} 项")
    except Exception as e:
        print(f"[{index}/{total}] ❌ MinerU 异常: {e}")
        return None

    # 4. 清洗 + 章节标记
    try:
        cleaned_md, normalized_values = clean_mineru_markdown(md_text, doc_type)
        cleaned_md_path.write_text(cleaned_md, encoding="utf-8")
        print(f"[{index}/{total}] ✅ 清洗后: {cleaned_md_path.name} ({len(cleaned_md)} 字符)")
    except Exception as e:
        print(f"[{index}/{total}] ❌ 清洗异常: {e}")
        return None

    # 5. 元数据抽取
    try:
        meta = extract_metadata(str(pdf_path), doc_type)
        print(f"[{index}/{total}] ✅ 元数据: 标题={meta.get('title', '')[:40]}, "
              f"作者={len(meta.get('authors', []))}人, "
              f"关键词={len(meta.get('keywords', []))}个")
    except Exception as e:
        print(f"[{index}/{total}] ⚠️  元数据抽取异常: {e}")
        meta = {"title": doc_id, "authors": [], "abstract": "", "keywords": [],
                "journal": "", "doi": "", "year": "", "extraction_method": "fallback",
                "extraction_notes": str(e)[:200]}

    # 6. 构建 ParsedDoc
    md5 = _compute_md5(str(pdf_path))
    extra_info = {
        "authors": meta.get("authors", []),
        "abstract": meta.get("abstract", ""),
        "keywords": meta.get("keywords", []),
        "journal": meta.get("journal", ""),
        "doi": meta.get("doi", ""),
        "year": meta.get("year", ""),
        "issuer": meta.get("issuer"),
        "doc_number": meta.get("doc_number"),
        "date": meta.get("date"),
        "extraction_method": meta.get("extraction_method", "mineru"),
        "extraction_notes": meta.get("extraction_notes", ""),
        "md5": md5,
    }
    parsed = ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        doc_type_cn=doc_type_cn,
        title=pdf_path.name,
        source_loc=str(pdf_path),
        markdown_path=str(cleaned_md_path),
        normalized_values=normalized_values,
        extra_info=extra_info,
    )
    cleaned_meta_path.write_text(
        parsed.model_dump_json(ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[{index}/{total}] ✅ 元数据 JSON 保存: {cleaned_meta_path.name}")

    return doc_id


def process_txt_xml(
    file_path: Path,
    index: int,
    total: int,
    cleaned_dir: Path,
    meta_dir: Path,
    fmt: str,
    skip_done: bool,
) -> Optional[str]:
    """处理 TXT/XML 文件（无需 MinerU，直接读取）。"""
    doc_id = _safe_filename(file_path.stem)
    cleaned_md_path = cleaned_dir / f"{doc_id}.md"
    cleaned_meta_path = meta_dir / f"{doc_id}.json"

    if skip_done and cleaned_meta_path.exists():
        print(f"[{index}/{total}] ⏭️  已处理, 跳过: {file_path.name[:50]}")
        return doc_id

    print(f"\n[{index}/{total}] 📄 {fmt.upper()}: {file_path.name[:60]}")

    # 直接读取
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"[{index}/{total}] ❌ 空文件，跳过")
        return None

    # 直接作为 Markdown 保存（无需清洗）
    cleaned_md_path.write_text(text, encoding="utf-8")
    print(f"[{index}/{total}] ✅ 已保存: {cleaned_md_path.name} ({len(text)} 字符)")

    # 简易元数据
    meta = {
        "title": doc_id,
        "authors": [],
        "abstract": "",
        "keywords": [],
        "journal": "",
        "doi": "",
        "year": "",
        "issuer": None,
        "doc_number": None,
        "date": None,
        "extraction_method": "direct_read",
        "extraction_notes": f"直接从 {fmt.upper()} 读取",
    }
    md5 = _compute_md5(str(file_path))
    extra_info = {**meta, "md5": md5}
    parsed = ParsedDoc(
        doc_id=doc_id,
        doc_type="txt" if fmt == "txt" else "xml",
        doc_type_cn="文本" if fmt == "txt" else "XML",
        title=file_path.name,
        source_loc=str(file_path),
        markdown_path=str(cleaned_md_path),
        normalized_values={},
        extra_info=extra_info,
    )
    cleaned_meta_path.write_text(
        parsed.model_dump_json(ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[{index}/{total}] ✅ 元数据 JSON 保存: {cleaned_meta_path.name}")

    return doc_id


def main():
    import argparse

    parser = argparse.ArgumentParser(description="批量文档解析（MinerU + 清洗 + 元数据）")
    parser.add_argument("--input", default="./input", help="输入目录（含 PDF/TXT/XML）")
    parser.add_argument("--output", default="./cleaned", help="输出 cleaned md 目录")
    parser.add_argument("--meta-output", default="./cleaned_meta", help="输出 cleaned meta 目录")
    parser.add_argument("--mode", choices=["incremental", "full", "retry_failed"],
                        default="incremental", help="运行模式")
    parser.add_argument("--no-skip-done", action="store_true", help="不跳过已处理的文件")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return 1

    cleaned_dir = Path(args.output)
    meta_dir = Path(args.meta_output)
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    skip_done = not args.no_skip_done and args.mode != "full"

    # 收集输入文件
    files = _collect_input_files(input_dir)
    if not files:
        print(f"⚠️  输入目录无可解析文件: {input_dir}")
        return 0

    total = len(files)
    print(f"📂 共 {total} 个文件待处理")
    if total > 0:
        pdf_count = sum(1 for _, f in files if f == "pdf")
        txt_count = sum(1 for _, f in files if f == "txt")
        xml_count = sum(1 for _, f in files if f == "xml")
        print(f"   PDF: {pdf_count}, TXT: {txt_count}, XML: {xml_count}")

    if total > 0 and files[0][1] == "pdf":
        print(get_quota_summary())
    print()

    success = 0
    failed = 0
    failed_ids = []

    for i, (file_path, fmt) in enumerate(files, 1):
        if fmt == "pdf":
            result = process_pdf(
                file_path, i, total, cleaned_dir, meta_dir, skip_done,
            )
        else:
            result = process_txt_xml(
                file_path, i, total, cleaned_dir, meta_dir, fmt, skip_done,
            )

        if result:
            success += 1
        else:
            failed += 1
            failed_ids.append(file_path.name)

        # 请求间隔（MinerU 限流）
        if fmt == "pdf":
            time.sleep(1)

    print(f"\n{'='*60}")
    print(f"✅ 解析完成: 成功 {success} / 失败 {failed} / 共 {total}")
    if failed_ids:
        print(f"❌ 失败文件 ({len(failed_ids)}):")
        for f in failed_ids[:10]:
            print(f"  - {f}")
    print(get_quota_summary())


if __name__ == "__main__":
    main()