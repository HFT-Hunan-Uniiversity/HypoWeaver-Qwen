#!/usr/bin/env python3
"""Run an auditable, multi-source novelty search for a candidate research gap.

The script combines a frozen local metadata snapshot with three public scholarly
APIs.  It intentionally stores normalized metadata only; no remote full text is
downloaded.  Query semantics for the local snapshot are declared as concept
groups: every group must match, while any synonym within a group may match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "GreenFinanceResearchPilot/1.0 (auditable literature novelty search)"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _fetch_json(url: str, *, attempts: int = 4) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}: {last_error}")


def _load_local(path: Path, *, as_of: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    raw = path.read_bytes()
    records: list[dict[str, Any]] = []
    excluded_future = 0
    as_of_date = as_of[:10]
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        published = str(value.get("published_at") or value.get("issue_date") or "")[:10]
        if published and published > as_of_date:
            excluded_future += 1
            continue
        records.append(value)
    return records, {
        "input_record_count": len(records) + excluded_future,
        "eligible_as_of_count": len(records),
        "future_dated_excluded_count": excluded_future,
        "input_sha256": _sha256_bytes(raw),
    }


def _record_text(record: dict[str, Any]) -> str:
    identifiers = " ".join(
        str(item.get("value") or "")
        for item in record.get("identifiers", [])
        if isinstance(item, dict)
    )
    return _normalize(
        " ".join(
            [
                str(record.get("title") or ""),
                str(record.get("abstract") or ""),
                " ".join(map(str, record.get("keywords") or [])),
                " ".join(map(str, record.get("matched_keywords") or [])),
                identifiers,
            ]
        )
    )


def _local_query(
    records: list[dict[str, Any]], concept_groups: list[list[str]], *, limit: int
) -> dict[str, Any]:
    normalized_groups = [[_normalize(term) for term in group] for group in concept_groups]
    matches: list[dict[str, Any]] = []
    for record in records:
        text = _record_text(record)
        group_hits = [any(term in text for term in group) for group in normalized_groups]
        if all(group_hits):
            matches.append(
                {
                    "paper_id": str(record.get("article_id") or "unknown"),
                    "doi": next(
                        (
                            str(item.get("value"))
                            for item in record.get("identifiers", [])
                            if isinstance(item, dict) and item.get("type") == "doi"
                        ),
                        None,
                    ),
                    "title": str(record.get("title") or "Untitled"),
                    "year": int(str(record.get("published_at") or record.get("issue_date") or "0")[:4] or 0) or None,
                    "source": "green-finance-data-center-public-metadata",
                    "matched_group_count": sum(group_hits),
                }
            )
    matches.sort(key=lambda item: (-(item.get("year") or 0), item["title"].casefold()))
    return {
        "hit_count": len(matches),
        "hit_count_semantics": "Boolean matches in the frozen local snapshot",
        "evaluated_result_count": min(len(matches), limit),
        "top_results": matches[:limit],
    }


def _europe_pmc(query: str, *, limit: int, as_of: str) -> dict[str, Any]:
    dated_query = f"({query}) AND FIRST_PDATE:[2000-01-01 TO {as_of[:10]}]"
    params = urllib.parse.urlencode(
        {"query": dated_query, "format": "json", "pageSize": limit, "resultType": "core"}
    )
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    value = _fetch_json(url)
    results = []
    for item in value.get("resultList", {}).get("result", []):
        results.append(
            {
                "paper_id": item.get("pmcid") or item.get("pmid") or item.get("id"),
                "doi": item.get("doi"),
                "title": item.get("title"),
                "year": int(item["pubYear"]) if str(item.get("pubYear") or "").isdigit() else None,
                "source": "europe-pmc",
                "cited_by_count": item.get("citedByCount"),
            }
        )
    return {
        "request_url": url,
        "hit_count": int(value.get("hitCount") or 0),
        "hit_count_semantics": "Europe PMC query matches after FIRST_PDATE cutoff",
        "evaluated_result_count": len(results),
        "top_results": results,
    }


def _openalex(query: str, *, limit: int, as_of: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "search": query,
            "filter": f"from_publication_date:2000-01-01,to_publication_date:{as_of[:10]}",
            "per-page": limit,
            "select": "id,doi,title,publication_year,publication_date,cited_by_count",
        }
    )
    url = f"https://api.openalex.org/works?{params}"
    value = _fetch_json(url)
    results = [
        {
            "paper_id": item.get("id"),
            "doi": item.get("doi"),
            "title": item.get("title"),
            "year": item.get("publication_year"),
            "source": "openalex",
            "cited_by_count": item.get("cited_by_count"),
        }
        for item in value.get("results", [])
    ]
    return {
        "request_url": url,
        "hit_count": int(value.get("meta", {}).get("count") or 0),
        "hit_count_semantics": "OpenAlex search matches after publication-date filter",
        "evaluated_result_count": len(results),
        "top_results": results,
    }


def _crossref(query: str, *, limit: int, as_of: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "query.bibliographic": query,
            "filter": f"from-pub-date:2000-01-01,until-pub-date:{as_of[:10]},type:journal-article",
            "rows": limit,
            "select": "DOI,title,published,container-title,URL,is-referenced-by-count",
        }
    )
    url = f"https://api.crossref.org/works?{params}"
    value = _fetch_json(url)
    message = value.get("message", {})
    results = []
    for item in message.get("items", []):
        date_parts = (item.get("published") or {}).get("date-parts") or []
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        titles = item.get("title") or []
        results.append(
            {
                "paper_id": item.get("DOI"),
                "doi": item.get("DOI"),
                "title": titles[0] if titles else None,
                "year": year,
                "source": "crossref",
                "cited_by_count": item.get("is-referenced-by-count"),
            }
        )
    return {
        "request_url": url,
        "hit_count": int(message.get("total-results") or 0),
        "hit_count_semantics": (
            "Crossref bibliographic ranking universe, not a Boolean exact-match count; "
            "use only the evaluated top results for nearest-work review"
        ),
        "evaluated_result_count": len(results),
        "top_results": results,
    }


def run(config: dict[str, Any], metadata_path: Path, *, limit: int) -> dict[str, Any]:
    as_of = str(config["as_of"])
    local_records, local_manifest = _load_local(metadata_path, as_of=as_of)
    searches: list[dict[str, Any]] = []
    for query in config["queries"]:
        text = str(query["query_text"])
        item = {
            "query_id": query["query_id"],
            "query_type": query["query_type"],
            "query_text": text,
            "concept_groups": query["concept_groups"],
            "sources": {
                "green-finance-data-center-public-metadata": _local_query(
                    local_records, query["concept_groups"], limit=limit
                ),
                "europe-pmc": _europe_pmc(text, limit=limit, as_of=as_of),
                "openalex": _openalex(text, limit=limit, as_of=as_of),
                "crossref": _crossref(text, limit=limit, as_of=as_of),
            },
        }
        searches.append(item)
    material = {
        "protocol_version": "novelty-search/1.0.1",
        "as_of": as_of,
        "candidate_gap": config["candidate_gap"],
        "queries": config["queries"],
        "local_input_sha256": local_manifest["input_sha256"],
    }
    return {
        "schema_version": "novelty-search/1.0.1",
        "search_id": f"novelty:{_sha256_bytes(_canonical_json(material).encode('utf-8'))[:24]}",
        "searched_at": config.get("searched_at") or datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "candidate_gap": config["candidate_gap"],
        "query_protocol": {
            "local_semantics": "AND across concept groups; OR across synonyms within a group",
            "remote_semantics": "bibliographic full-text search semantics defined by each named API",
            "top_result_limit": limit,
        },
        "local_snapshot": {
            "path": str(metadata_path.resolve()),
            **local_manifest,
        },
        "searches": searches,
        "warnings": [
            "Hit counts are source-specific and are not directly comparable across APIs.",
            "A zero hit is evidence only within the declared query, source, date and metadata coverage.",
            "Nearest-work relevance requires human scientific review before a novelty claim is accepted.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = run(config, args.metadata, limit=args.limit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"WROTE: {args.output} ({len(result['searches'])} query families)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
