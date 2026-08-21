# ============================================================================
# 数据中心论文下载 — scripts/download_papers.py
# ============================================================================
# 从数据中心获取论文，支持两种数据源：
#   路径 A: 公开 Feed API（元数据，无需凭据）
#   路径 B: 内部全文下载工具（需 GREEN_FINANCE_RESEARCH_TOKEN）
#
# 用法:
#   python scripts/download_papers.py --output-dir ./input --mode incremental
#   python scripts/download_papers.py --output-dir ./input --mode full
# ============================================================================

from __future__ import annotations

import json
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 公开 Feed API 端点（优先服务器本地，兜底公网域名）
FEED_API_LOCAL = "http://127.0.0.1:4173/api/feed"
FEED_API_PUBLIC = "https://green-finance-dashboard.vercel.app/api/feed"

# 全文下载工具配置（green-finance-data-center 项目）
FULLTEXT_TOOL_DIR = os.environ.get(
    "FULLTEXT_TOOL_DIR",
    str(Path.home() / "green-finance-data-center"),
)
FULLTEXT_BASE_URL = os.environ.get(
    "FULLTEXT_BASE_URL",
    "https://106.53.153.215",
)


def _get_feed_api() -> str:
    """探测可用的 Feed API 端点。"""
    for url in [FEED_API_LOCAL, FEED_API_PUBLIC]:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return url
        except requests.RequestException:
            continue
    return FEED_API_PUBLIC  # 都不可用时用公网（可能超时）


def fetch_metadata(scope: str = "green", limit: int = 500) -> List[dict]:
    """从 Feed API 分页获取全部元数据。

    参数:
      scope: "green"（绿色金融候选）或 "all"（全部）
      limit: 每页条数

    返回:
      按 article_id 去重后的元数据记录列表。
    """
    base_url = _get_feed_api()
    print(f"📡 Feed API: {base_url}")

    # 第一页，获取 dataset_version
    r = requests.get(
        f"{base_url}/articles",
        params={"scope": scope, "limit": limit},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    dataset_version = data.get("dataset_version", "")
    snapshot_at = data.get("snapshot_at", "")
    records = data.get("records", [])
    next_cursor = data.get("next")

    print(f"  版本: {dataset_version}, 快照: {snapshot_at}")
    print(f"  第一页: {len(records)} 条")

    # 后续分页
    page = 1
    while next_cursor:
        page += 1
        r = requests.get(
            f"{base_url}/articles",
            params={"scope": scope, "limit": limit, "next": next_cursor},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        page_records = data.get("records", [])
        records.extend(page_records)
        next_cursor = data.get("next")
        print(f"  第 {page} 页: {len(page_records)} 条 (累计 {len(records)})")

    # 一致性检查
    r = requests.get(base_url, timeout=30)
    r.raise_for_status()
    final_version = r.json().get("dataset_version", "")
    if final_version != dataset_version:
        print(f"⚠️  dataset_version 变化: {dataset_version} → {final_version}")
        print("   数据可能不一致，建议重新运行")

    # 去重
    seen = set()
    deduped = []
    for rec in records:
        aid = rec.get("article_id", "")
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(rec)

    print(f"✅ 元数据: {len(records)} 条（去重后 {len(deduped)} 条）")
    return deduped


def download_fulltext(output_dir: Path) -> dict:
    """通过 green-finance-data-center 工具下载全文。

    需要:
      - GREEN_FINANCE_RESEARCH_TOKEN 环境变量
      - green-finance-data-center 项目已克隆到本地

    返回:
      下载结果 dict（records / written / unchanged）。
    """
    token = os.environ.get("GREEN_FINANCE_RESEARCH_TOKEN", "")
    if not token:
        print("⚠️  未设置 GREEN_FINANCE_RESEARCH_TOKEN，跳过全文下载")
        return {"records": 0, "written": 0, "unchanged": 0, "skipped": True}

    tool_dir = Path(FULLTEXT_TOOL_DIR)
    if not tool_dir.exists():
        print(f"⚠️  未找到全文下载工具: {tool_dir}")
        print("   请先克隆 green-finance-data-center 项目")
        return {"records": 0, "written": 0, "unchanged": 0, "error": "tool_not_found"}

    # 确保安装了依赖
    if not (tool_dir / "node_modules").exists():
        print("  安装 npm 依赖...")
        subprocess.run(
            ["npm", "ci"],
            cwd=str(tool_dir),
            check=True,
            capture_output=True,
        )

    # 执行下载
    print(f"  下载全文到: {output_dir}")
    result = subprocess.run(
        [
            "npm", "run", "fulltext:download", "--",
            "--base-url", FULLTEXT_BASE_URL,
            "--output-dir", str(output_dir),
        ],
        cwd=str(tool_dir),
        capture_output=True,
        text=True,
        timeout=600,  # 10 分钟超时
        env={
            **os.environ,
            "GREEN_FINANCE_RESEARCH_TOKEN": token,
        },
    )

    # 解析输出
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    print(stdout[:500])

    try:
        # 尝试从最后一行 JSON 解析结果
        for line in reversed(stdout.split("\n")):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        pass

    if result.returncode != 0:
        print(f"  ⚠️  下载工具返回非零: {result.returncode}")
        print(f"  stderr: {stderr[:300]}")

    return {"records": 0, "written": 0, "unchanged": 0, "returncode": result.returncode}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="数据中心论文下载")
    parser.add_argument("--output-dir", default="./input", help="输出目录")
    parser.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    parser.add_argument("--metadata-only", action="store_true", help="只下载元数据，不下载全文")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 下载元数据
    print("=" * 50)
    print("📥 下载元数据（Feed API）")
    print("=" * 50)
    metadata = fetch_metadata(scope="green")

    meta_dir = output_dir / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "articles.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  元数据已保存: {meta_dir / 'articles.json'}")
    print(f"  共 {len(metadata)} 篇文章")

    # 2. 下载全文（可选）
    if not args.metadata_only:
        print()
        print("=" * 50)
        print("📄 下载全文（green-finance-data-center）")
        print("=" * 50)
        fulltext_dir = output_dir / "fulltexts"
        result = download_fulltext(fulltext_dir)
        print(f"  结果: {json.dumps(result, ensure_ascii=False)}")

        # 检查 manifest
        manifest_path = fulltext_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            print(f"  manifest: {manifest.get('total_assets', '?')} 篇资产")

        # 检查 articles.ndjson
        ndjson_path = fulltext_dir / "articles.ndjson"
        if ndjson_path.exists():
            count = sum(1 for _ in ndjson_path.open(encoding="utf-8"))
            print(f"  articles.ndjson: {count} 条记录")

    print()
    print("✅ 下载完成")


if __name__ == "__main__":
    main()