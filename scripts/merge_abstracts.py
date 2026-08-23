#!/usr/bin/env python3
"""
合并 Feed API 摘要到现有 cleaned md，并为无全文的论文创建 cleaned md + cleaned_meta。

流程:
1. 加载 input/feed_metadata.json（1088 条元数据）
2. 遍历现有 cleaned/ 文件：
   - 如果无【摘要】标记，从 Feed API 插入摘要（不论文件大小）
3. 遍历 Feed API 记录：
   - 如果 article_id 没有对应的 cleaned 文件，创建新的 cleaned md + cleaned_meta
"""

import json
import os
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEED_PATH = PROJECT_ROOT / "input" / "feed_metadata.json"
CLEANED_DIR = PROJECT_ROOT / "cleaned"
CLEANED_META_DIR = PROJECT_ROOT / "cleaned_meta"


def load_feed() -> Dict[str, dict]:
    """加载 Feed API 数据，返回 {article_id: record} 字典。"""
    if not FEED_PATH.exists():
        print(f"❌ 未找到 Feed API 数据: {FEED_PATH}")
        print("   请先运行 scripts/download_feed_metadata.py")
        return {}
    data = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    return {d["article_id"]: d for d in data}


def get_article_id_from_filename(name: str) -> str:
    """从 cleaned 文件名提取 article_id（第一个 '-' 前的部分）。"""
    return name.split("-")[0]


def build_meta_md(record: dict) -> str:
    """从 Feed API 记录构建 cleaned md 内容。"""
    title = record.get("title", "") or ""
    abstract = record.get("abstract", "") or ""
    authors = record.get("authors_text", "") or ""
    journal = record.get("journal_name", "") or ""
    keywords = record.get("keywords", []) or []

    parts = []
    if title:
        parts.append(f"#【标题】{title}")
    if abstract:
        parts.append(f"#【摘要】{abstract}")
    if journal:
        parts.append(f"#【期刊】{journal}")
    if authors:
        parts.append(f"#【作者】{authors}")
    if keywords:
        parts.append(f"#【关键词】{'；'.join(keywords)}")

    return "\n\n".join(parts)


def main():
    feed = load_feed()
    if not feed:
        return

    print(f"📚 Feed API: {len(feed)} 条记录")

    # ================================================================
    # 1. 遍历现有 cleaned 文件，合并摘要（不论文件大小）
    # ================================================================
    existing = sorted(CLEANED_DIR.glob("*.md"))
    upgrade_count = 0
    already_have = 0
    no_abstract_in_feed = 0
    not_in_feed = 0

    SUMMARY_MARKER = "#【摘要】"

    for md_path in existing:
        article_id = get_article_id_from_filename(md_path.stem)
        if article_id not in feed:
            not_in_feed += 1
            continue

        feed_record = feed[article_id]
        abstract = feed_record.get("abstract", "").strip()
        if not abstract:
            no_abstract_in_feed += 1
            continue  # Feed API 也没有摘要

        # 检查是否已有摘要
        content = md_path.read_text(encoding="utf-8", errors="replace")
        if SUMMARY_MARKER in content:
            already_have += 1
            continue

        # 在末尾插入摘要
        abstract_block = f"\n\n{SUMMARY_MARKER}{abstract}"
        md_path.write_text(content + abstract_block, encoding="utf-8")
        upgrade_count += 1
        print(f"  ✅ 升级: {md_path.name[:60]} ({md_path.stat().st_size} 字符)")

    print(f"\n📊 升级摘要: {upgrade_count} 篇")
    print(f"  📌 已有摘要: {already_have}")
    print(f"  ⚠️  Feed 无摘要: {no_abstract_in_feed}")
    print(f"  ⚠️  不在 Feed 中: {not_in_feed}")

    # ================================================================
    # 2. 为无全文的 Feed API 记录创建 cleaned md + cleaned_meta
    # ================================================================
    existing_ids = {get_article_id_from_filename(f.stem) for f in existing}
    new_count = 0
    skipped_no_abstract = 0

    for article_id, record in feed.items():
        if article_id in existing_ids:
            continue

        # 跳过完全没有摘要的记录（没必要建空文件）
        abstract = record.get("abstract", "").strip()
        title = record.get("title", "").strip()
        if not abstract and not title:
            skipped_no_abstract += 1
            continue

        # 创建 cleaned md
        md_content = build_meta_md(record)
        md_path = CLEANED_DIR / f"{article_id}.md"
        md_path.write_text(md_content, encoding="utf-8")

        # 创建 cleaned_meta
        authors_text = record.get("authors_text", "") or ""
        journal = record.get("journal_name", "") or ""
        doi = ""
        if record.get("identifiers"):
            for ident in record["identifiers"]:
                if ident.get("type") == "doi":
                    doi = ident.get("value", "")
                    break
        keywords = record.get("keywords", []) or []

        meta = {
            "doc_id": article_id,
            "doc_type": "feed_api",
            "doc_type_cn": "元数据",
            "title": title,
            "source_loc": f"feed_api:{article_id}",
            "markdown_path": str(md_path),
            "extra_info": {
                "title": title,
                "authors": [a.strip() for a in authors_text.split(",") if a.strip()] if authors_text else [],
                "abstract": abstract,
                "keywords": keywords,
                "journal": journal,
                "doi": doi,
                "year": "",
                "issuer": None,
                "doc_number": None,
                "date": record.get("published_at", ""),
                "extraction_method": "feed_api",
                "extraction_notes": "从 Feed API 元数据创建",
                "md5": "",
            },
            "normalized_values": [],
        }
        meta_path = CLEANED_META_DIR / f"{article_id}.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        new_count += 1

        if new_count % 50 == 0:
            print(f"  ... 已创建 {new_count} 篇")

    print(f"\n📊 新建: {new_count} 篇（无全文，仅元数据）")
    print(f"  ⚠️  跳过（无标题无摘要）: {skipped_no_abstract}")

    # ================================================================
    # 3. 汇总
    # ================================================================
    total_after = len(list(CLEANED_DIR.glob("*.md")))
    print(f"\n{'='*50}")
    print(f"📊 汇总: cleaned 目录 {total_after} 篇")
    print(f"  - 升级摘要: {upgrade_count}")
    print(f"  - 新建: {new_count}")
    print(f"  - 之前已有: {len(existing)}")
    print(f"  - 变更: {upgrade_count + new_count}")


if __name__ == "__main__":
    main()