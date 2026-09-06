from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://green-finance-dashboard.vercel.app"


def _get_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GreenFin-Scientist-Metadata-Pilot/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object from {url}")
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fetch_feed(
    *, base_url: str, scope: str, limit: int, output_dir: Path
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    before = _get_json(f"{base_url}/api/feed")
    dataset_version = before.get("dataset_version")
    if not isinstance(dataset_version, str) or not dataset_version:
        raise ValueError("feed manifest has no dataset_version")

    next_url: str | None = (
        f"{base_url}/api/feed/articles?"
        + urllib.parse.urlencode({"scope": scope, "limit": limit})
    )
    records_by_id: dict[str, dict[str, Any]] = {}
    page_count = 0
    while next_url:
        page = _get_json(next_url)
        page_count += 1
        records = page.get("records")
        if not isinstance(records, list):
            raise ValueError(f"page {page_count} has no records array")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"page {page_count} contains a non-object record")
            article_id = record.get("article_id")
            if not isinstance(article_id, str) or not article_id:
                raise ValueError(f"page {page_count} contains a record without article_id")
            existing = records_by_id.get(article_id)
            if existing is not None and existing != record:
                raise ValueError(f"article_id {article_id} changed within one crawl")
            records_by_id[article_id] = record
        raw_next = page.get("next")
        if raw_next is not None and not isinstance(raw_next, str):
            raise ValueError(f"page {page_count} has an invalid next URL")
        next_url = urllib.parse.urljoin(base_url, raw_next) if raw_next else None

    after = _get_json(f"{base_url}/api/feed")
    if after.get("dataset_version") != dataset_version:
        raise RuntimeError(
            "dataset_version changed during crawl; discard output and retry"
        )

    records = [records_by_id[key] for key in sorted(records_by_id)]
    ndjson_text = "".join(_canonical_json(record) + "\n" for record in records)
    ndjson_bytes = ndjson_text.encode("utf-8")
    expected_count = (after.get("counts") or {}).get(scope)
    if isinstance(expected_count, int) and expected_count != len(records):
        raise RuntimeError(
            f"feed count mismatch: manifest={expected_count}, fetched={len(records)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    articles_path = output_dir / "articles.ndjson"
    articles_path.write_bytes(ndjson_bytes)
    manifest = {
        "schema_version": "public-metadata-crawl/1.0.0",
        "source_contract_version": before.get("contract_version"),
        "source_url": f"{base_url}/api/feed/articles?scope={scope}&limit={limit}",
        "scope": scope,
        "dataset_version": dataset_version,
        "snapshot_at": after.get("snapshot_at"),
        "data_updated_at": after.get("data_updated_at"),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "page_count": page_count,
        "record_count": len(records),
        "articles_sha256": hashlib.sha256(ndjson_bytes).hexdigest(),
        "rights": after.get("rights"),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a version-consistent public metadata feed snapshot."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--scope", choices=("all", "green"), default="green")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be between 1 and 500")
    try:
        manifest = fetch_feed(
            base_url=args.base_url,
            scope=args.scope,
            limit=args.limit,
            output_dir=args.output_dir,
        )
    except Exception as exc:  # pragma: no cover - CLI failure boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
