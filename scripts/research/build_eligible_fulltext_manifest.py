#!/usr/bin/env python3
"""Create a release-eligible full-text manifest without deleting source assets.

The source collection is immutable.  A dated eligibility registry decides which
documents may flow into parsed chunks, retrieval, graph construction and
discovery.  Every source item must have exactly one decision so a newly retracted
or otherwise ineligible work cannot enter a formal release by omission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


INCLUDE_DECISION = "include"
EXCLUDE_DECISIONS = {
    "exclude_retracted",
    "exclude_rights",
    "exclude_preprint",
    "exclude_quality",
    "exclude_out_of_scope",
}


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _pretty_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value, raw


def _identity(item: dict[str, Any]) -> str:
    pmcid = str(item.get("pmcid") or "").strip().upper()
    doi = str(item.get("doi") or "").strip().casefold()
    if pmcid:
        return f"pmcid:{pmcid}"
    if doi:
        return f"doi:{doi}"
    raise ValueError("manifest/registry item has neither pmcid nor doi")


def build_eligible_manifest(
    source_manifest_path: Path,
    decision_registry_path: Path,
    output_manifest_path: Path,
    audit_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source, source_raw = _read_object(source_manifest_path)
    registry, registry_raw = _read_object(decision_registry_path)
    if registry.get("schema_version") != "document-eligibility/1.0.0":
        raise ValueError("unsupported eligibility registry schema_version")
    decisions = registry.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("eligibility registry decisions must be a non-empty array")
    source_items = source.get("items")
    if not isinstance(source_items, list) or not source_items:
        raise ValueError("source manifest items must be a non-empty array")
    if source.get("record_count") != len(source_items):
        raise ValueError("source manifest record_count does not match items")

    decision_by_identity: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("each eligibility decision must be an object")
        identity = _identity(decision)
        if identity in decision_by_identity:
            raise ValueError(f"duplicate eligibility decision for {identity}")
        disposition = decision.get("decision")
        if disposition != INCLUDE_DECISION and disposition not in EXCLUDE_DECISIONS:
            raise ValueError(f"{identity}: unsupported decision {disposition!r}")
        if not str(decision.get("reason") or "").strip():
            raise ValueError(f"{identity}: decision reason is required")
        if disposition == "exclude_retracted":
            for field in ("status_source", "status_uri", "retraction_notice_doi"):
                if not str(decision.get(field) or "").strip():
                    raise ValueError(f"{identity}: {field} is required for a retraction")
        decision_by_identity[identity] = decision

    source_identities = [_identity(item) for item in source_items]
    if len(set(source_identities)) != len(source_identities):
        raise ValueError("source manifest contains duplicate document identities")
    missing = sorted(set(source_identities) - set(decision_by_identity))
    extra = sorted(set(decision_by_identity) - set(source_identities))
    if missing or extra:
        raise ValueError(
            f"eligibility registry must cover the source manifest exactly; missing={missing}, extra={extra}"
        )

    included: list[dict[str, Any]] = []
    excluded_audit: list[dict[str, Any]] = []
    for item in source_items:
        identity = _identity(item)
        decision = decision_by_identity[identity]
        disposition = decision["decision"]
        source_retracted = item.get("is_retracted")
        if disposition == INCLUDE_DECISION:
            if source_retracted not in (None, False, "N", "No", "NO", 0):
                raise ValueError(
                    f"{identity}: source metadata marks the work retracted; it cannot be included"
                )
            included.append(item)
        else:
            excluded_audit.append(
                {
                    "identity": identity,
                    "pmcid": item.get("pmcid"),
                    "doi": item.get("doi"),
                    "title": item.get("title"),
                    "decision": disposition,
                    "reason": decision["reason"],
                    "status_source": decision.get("status_source"),
                    "status_uri": decision.get("status_uri"),
                    "retraction_notice_doi": decision.get("retraction_notice_doi"),
                    "raw_file_retained": item.get("raw_file"),
                    "raw_sha256": item.get("raw_sha256"),
                }
            )

    if not included:
        raise ValueError("eligibility gate excluded every source document")
    eligible_manifest = {
        "items": included,
        "record_count": len(included),
        "retrieved_at": source.get("retrieved_at"),
        "schema_version": source.get("schema_version"),
        "source": source.get("source"),
    }
    output_bytes = _pretty_bytes(eligible_manifest)
    audit = {
        "schema_version": "document-eligibility-audit/1.0.0",
        "as_of": registry.get("as_of"),
        "source_manifest": str(source_manifest_path.as_posix()),
        "source_manifest_sha256": _sha256(source_raw),
        "decision_registry": str(decision_registry_path.as_posix()),
        "decision_registry_sha256": _sha256(registry_raw),
        "eligible_manifest": str(output_manifest_path.as_posix()),
        "eligible_manifest_sha256": _sha256(output_bytes),
        "source_document_count": len(source_items),
        "included_document_count": len(included),
        "excluded_document_count": len(excluded_audit),
        "included_identities": [_identity(item) for item in included],
        "excluded": excluded_audit,
        "raw_assets_deleted": False,
        "downstream_rule": (
            "Only documents in eligible_manifest may enter parsed release, retrieval index, "
            "formal graph, trend, gap or hypothesis support."
        ),
    }
    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    output_manifest_path.write_bytes(output_bytes)
    audit_path.write_bytes(_pretty_bytes(audit))
    return eligible_manifest, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest, audit = build_eligible_manifest(
            args.source_manifest,
            args.decisions,
            args.output_manifest,
            args.audit,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"WROTE: {args.output_manifest} ({manifest['record_count']} included, "
        f"{audit['excluded_document_count']} excluded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
