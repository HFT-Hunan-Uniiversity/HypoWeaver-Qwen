# 全量 37 篇 PDF 批量 MinerU 解析脚本
# 用法: python -X utf8 src/parse/run_batch_mineru.py
# 输出: cleaned/ 下的 markdown + cleaned_meta/ 下的 ParsedDoc JSON

import json, os, sys, time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse.adapters.mineru_api import parse_pdf, get_quota_summary, get_pdf_page_count
from src.parse.clean.cleaning import clean_mineru_markdown
from src.parse.ir.parsed_doc import ParsedDoc
from src.parse.adapters.metadata_extractor import extract_metadata
from src.parse.config.doc_types import infer_doc_type
import hashlib

RAW_DIR = PROJECT_ROOT / "PDFs"
CLEANED_DIR = PROJECT_ROOT / "cleaned"
CLEANED_META_DIR = PROJECT_ROOT / "cleaned_meta"
CLEANED_DIR.mkdir(exist_ok=True)
CLEANED_META_DIR.mkdir(exist_ok=True)


def compute_md5(filepath: str) -> str:
    """计算文件 MD5 哈希"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(filename: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符"""
    name = Path(filename).stem
    name = "".join(c for c in name if c.isalnum() or c in "-_ ")
    name = name.strip()[:max_len]
    return name


def process_one(pdf_path: str, index: int, total: int):
    """处理单个 PDF: MinerU 解析 + 清洗 + 元数据 + ParsedDoc"""
    pdf_path = str(pdf_path)
    file_name = os.path.basename(pdf_path)
    doc_id = safe_filename(Path(pdf_path).stem)

    cleaned_md_path = CLEANED_DIR / f"{doc_id}.md"
    cleaned_meta_path = CLEANED_META_DIR / f"{doc_id}.json"

    # 已处理过则跳过（断点续跑）
    if cleaned_meta_path.exists():
        print(f"[{index}/{total}] ⏭️  已处理, 跳过: {file_name[:50]}")
        return doc_id

    print(f"\n[{index}/{total}] {'='*55}")
    print(f"[{index}/{total}] 📄 处理: {file_name[:60]}")

    # 1. 文档类型推断（文件名关键词 → LLM 兜底）
    doc_type, doc_type_cn = infer_doc_type(file_name, pdf_path)
    print(f"[{index}/{total}] 🏷️  文档类型: {doc_type} ({doc_type_cn})")

    # 2. 配额检查
    pages = get_pdf_page_count(pdf_path)
    print(f"[{index}/{total}]   页数: {pages}")
    print(f"[{index}/{total}]   {get_quota_summary()}")

    # 3. MinerU 解析
    result = parse_pdf(pdf_path)
    if result is None:
        print(f"[{index}/{total}] ❌ MinerU 解析失败，跳过")
        return None
    md_text = result["markdown"]
    content_list = result["content_list"]
    print(f"[{index}/{total}] ✅ MinerU: {len(md_text)} 字符, content_list {len(content_list)} 项")

    # 4. 清洗 + 章节标记（按文档类型加载章节映射）
    cleaned_md, normalized_values = clean_mineru_markdown(md_text, doc_type)
    cleaned_md_path.write_text(cleaned_md, encoding="utf-8")
    print(f"[{index}/{total}] ✅ 清洗后 Markdown: {cleaned_md_path.name} ({len(cleaned_md)} 字符)")

    # 5. 元数据抽取（按文档类型走正则+LLM 或 LLM 全量）
    meta = extract_metadata(pdf_path, doc_type)
    print(f"[{index}/{total}] ✅ 元数据: 标题={meta['title'][:40] if meta['title'] else 'None'}, "
          f"作者={len(meta['authors'])}人, 摘要={len(meta['abstract']) if meta['abstract'] else 0}字, "
          f"关键词={len(meta['keywords'])}个，方法={meta['extraction_method']}")

    # 6. 构建 ParsedDoc
    md5 = compute_md5(pdf_path)
    extra_info = {
        "authors": meta["authors"],
        "abstract": meta["abstract"],
        "keywords": meta["keywords"],
        "journal": meta["journal"],
        "doi": meta["doi"],
        "year": meta["year"],
        "issuer": meta.get("issuer"),
        "doc_number": meta.get("doc_number"),
        "date": meta.get("date"),
        "extraction_method": meta["extraction_method"],
        "extraction_notes": meta["extraction_notes"],
        "md5": md5,
    }
    parsed = ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        doc_type_cn=doc_type_cn,
        title=file_name,
        source_loc=pdf_path,
        markdown_path=str(cleaned_md_path),
        normalized_values=normalized_values,
        extra_info=extra_info,
    )
    cleaned_meta_path.write_text(
        parsed.model_dump_json(ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[{index}/{total}] ✅ 元数据 JSON 保存: {cleaned_meta_path.name}")

    return doc_id


def main():
    # 收集 PDF 列表，英文优先
    pdfs = [p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    if not pdfs:
        print("❌ 无 PDF 文件")
        return

    # 中英分离：英文文件名含汉字 → 中文
    en_pdfs = [p for p in pdfs if not any('一' <= c <= '鿿' for c in p.name)]
    cn_pdfs = [p for p in pdfs if any('一' <= c <= '鿿' for c in p.name)]
    pdfs_all = sorted(en_pdfs) + sorted(cn_pdfs)

    total = len(pdfs_all)
    print(f"📂 共 {total} 篇 PDF (英文 {len(en_pdfs)} + 中文 {len(cn_pdfs)})")
    print(get_quota_summary())
    print()

    success = 0
    failed = 0
    for i, pdf in enumerate(pdfs_all, 1):
        result = process_one(pdf, i, total)
        if result:
            success += 1
        else:
            failed += 1
        # 间隔 1s 避免请求过频
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"✅ 完成: 成功 {success} / 失败 {failed} / 共 {total}")
    print(get_quota_summary())


if __name__ == "__main__":
    main()