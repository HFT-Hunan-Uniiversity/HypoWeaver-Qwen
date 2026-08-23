#!/usr/bin/env python3
"""
从 Feed API 拉取全部论文元数据（游标分页）
输出: input/feed_metadata.json
"""

import json
from pathlib import Path

import requests

FEED_BASE = "http://127.0.0.1:4173/api/feed/articles"
LIMIT = 500
OUTPUT = Path(__file__).resolve().parent.parent / "input" / "feed_metadata.json"


def fetch_all() -> list:
    """游标分页拉取全部论文元数据。"""
    all_records = []
    page = 0

    # 首次请求
    url = f"{FEED_BASE}?scope=green&limit={LIMIT}"
    while url:
        page += 1
        print(f"  第 {page} 页...", end=" ", flush=True)
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"失败: {e}")
            break

        data = resp.json()
        records = data.get("records", [])
        total = data.get("matching_total", "?")
        next_url = data.get("next")

        print(f"返回 {len(records)} 条 (total={total})")

        if not records:
            break

        all_records.extend(records)
        url = next_url  # 可能是相对路径或绝对路径

        # 如果 next_url 是相对路径，补全
        if url and url.startswith("/"):
            url = f"http://127.0.0.1:4173{url}"

    return all_records


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"📥 从 Feed API 拉取论文元数据...")
    articles = fetch_all()
    print(f"\n共拉取 {len(articles)} 条记录")

    # 去重（以防万一）
    seen = set()
    deduped = []
    for a in articles:
        aid = a.get("article_id", "")
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(a)
    if len(deduped) < len(articles):
        print(f"  去重: {len(articles)} → {len(deduped)}")

    # 基本字段统计
    with_abstract = sum(1 for a in deduped if a.get("abstract"))
    with_keywords = sum(1 for a in deduped if a.get("keywords"))
    print(f"  有摘要: {with_abstract}/{len(deduped)} ({100*with_abstract/len(deduped):.1f}%)")
    print(f"  有关键词: {with_keywords}/{len(deduped)}")

    OUTPUT.write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已保存: {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()