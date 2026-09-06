#!/usr/bin/env python3
"""Summarize corpus-bounded topic signals in a frozen metadata snapshot."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_text(record: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            [
                str(record.get("title") or ""),
                str(record.get("abstract") or ""),
                " ".join(map(str, record.get("keywords") or [])),
                " ".join(map(str, record.get("matched_keywords") or [])),
            ]
        )
    )


def _matches(text: str, groups: list[list[str]]) -> bool:
    return all(any(_normalize(term) in text for term in group) for group in groups)


def analyze(metadata_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    raw = metadata_path.read_bytes()
    as_of_date = str(config["as_of"])[:10]
    eligible: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    for line in raw.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        published = str(record.get("published_at") or record.get("issue_date") or "")[:10]
        if published and published > as_of_date:
            future.append(record)
        else:
            eligible.append(record)

    year_distribution = Counter()
    unknown_year_count = 0
    for record in eligible:
        published = str(record.get("published_at") or record.get("issue_date") or "")
        if len(published) >= 4 and published[:4].isdigit():
            year_distribution[int(published[:4])] += 1
        else:
            unknown_year_count += 1

    signals = []
    for definition in config["signals"]:
        matches = [
            record
            for record in eligible
            if _matches(_record_text(record), definition["concept_groups"])
        ]
        years = Counter()
        for record in matches:
            published = str(record.get("published_at") or record.get("issue_date") or "")
            if len(published) >= 4 and published[:4].isdigit():
                years[int(published[:4])] += 1
        matches.sort(
            key=lambda item: (
                str(item.get("published_at") or item.get("issue_date") or ""),
                str(item.get("title") or "").casefold(),
            ),
            reverse=True,
        )
        signals.append(
            {
                "signal_id": definition["signal_id"],
                "label": definition["label"],
                "concept_groups": definition["concept_groups"],
                "match_count": len(matches),
                "share_of_eligible_snapshot": len(matches) / len(eligible) if eligible else 0.0,
                "year_counts": [
                    {"year": year, "count": count} for year, count in sorted(years.items())
                ],
                "sample_matches": [
                    {
                        "article_id": item.get("article_id"),
                        "title": item.get("title"),
                        "published_at": item.get("published_at") or item.get("issue_date"),
                        "final_decision": item.get("final_decision"),
                    }
                    for item in matches[:10]
                ],
            }
        )
    return {
        "schema_version": "metadata-topic-signals/1.0.0",
        "as_of": config["as_of"],
        "source_path": str(metadata_path.resolve()),
        "source_sha256": _sha256_bytes(raw),
        "input_record_count": len(eligible) + len(future),
        "eligible_as_of_count": len(eligible),
        "future_dated_excluded_count": len(future),
        "unknown_year_count": unknown_year_count,
        "year_distribution": [
            {"year": year, "count": count} for year, count in sorted(year_distribution.items())
        ],
        "signals": signals,
        "claim_gate": {
            "status": "descriptive_snapshot_only",
            "growth_rate_allowed": False,
            "reason": (
                "The snapshot is dominated by its 2025-2026 ingestion window and is not a "
                "year-balanced field census; annual counts cannot identify field-wide growth."
            ),
        },
        "warnings": [
            "Signal matches use deterministic concept-group substring rules over title, abstract and keywords.",
            "A match is a screening signal, not evidence that the article tests the full mechanism.",
            "Future-dated records were excluded using the declared as-of date.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = analyze(args.metadata, config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"WROTE: {args.output} ({len(result['signals'])} topic signals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
