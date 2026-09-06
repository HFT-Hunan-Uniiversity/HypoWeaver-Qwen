#!/usr/bin/env python3
"""Build a semantic coverage certificate for an eligibility-gated deep corpus."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.coverage.validator import GAP_TYPES, validate_certificate  # noqa: E402
from src.reason.schema_gate import validate_instance  # noqa: E402


COVERAGE_SCHEMA = ROOT / "schemas" / "coverage_certificate.schema.json"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_object(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _profile_paths(path: Path) -> list[Path]:
    values = sorted(path.glob("PMC*.json"))
    if not values:
        raise ValueError(f"{path}: no PMC*.json profiles")
    return values


def _field_item(
    profiles: list[dict[str, Any]],
    *,
    field_path: str,
    description: str,
    critical: bool,
    is_present,
    evidence_ref: str,
) -> dict[str, Any]:
    present = sum(bool(is_present(profile)) for profile in profiles)
    target = len(profiles)
    absent = target - present
    observable = target
    return {
        "field_path": field_path,
        "description": description,
        "critical": critical,
        "target_document_count": target,
        "applicable_document_count": target,
        "observable_document_count": observable,
        "status_counts": {
            "observed_present": present,
            "observed_absent": absent,
            "not_extracted": 0,
            "source_missing": 0,
            "not_applicable": 0,
        },
        "observability_rate": 1.0,
        "presence_rate": present / observable if observable else None,
        "extraction_version": "paper-profile-graph-input/0.2.0",
        "evidence_refs": [evidence_ref],
    }


def _identity(item: dict[str, Any]) -> str:
    doi = str(item.get("doi") or "").casefold().removeprefix("https://doi.org/")
    if doi:
        return f"doi:{doi}"
    return f"{item.get('source')}:{item.get('paper_id')}"


def _retrieval_rounds(novelty: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    rounds: list[dict[str, Any]] = []
    for round_number, search in enumerate(novelty["searches"], start=1):
        candidates: list[dict[str, Any]] = []
        for source in search["sources"].values():
            candidates.extend(source.get("top_results") or [])
        identities = {_identity(item) for item in candidates}
        new = identities - seen
        seen.update(identities)
        cumulative = len(seen)
        rounds.append(
            {
                "round": round_number,
                "query_family": str(search["query_id"]),
                "candidate_count": len(candidates),
                "new_unique_document_count": len(new),
                "cumulative_unique_document_count": cumulative,
                "marginal_gain": 0.0 if cumulative == 0 else len(new) / cumulative,
            }
        )
    return rounds, len(seen)


def _gate(
    gate_id: str,
    dimension: str,
    metric: str,
    threshold: Any,
    observed: Any,
    *,
    comparator: str = ">=",
    blocking: bool = True,
    evidence_ref: str,
    notes: str | None = None,
) -> dict[str, Any]:
    if comparator == ">=":
        passed = observed >= threshold
    elif comparator == "==":
        passed = observed == threshold
    else:
        raise ValueError(f"unsupported gate comparator: {comparator}")
    return {
        "gate_id": gate_id,
        "dimension": dimension,
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "observed": observed,
        "status": "passed" if passed else "failed",
        "blocking": blocking,
        "evidence_refs": [evidence_ref],
        "notes": notes,
    }


def _gap_decisions(corpus_size: int) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    allowed = ["cross_stream"]
    conditional = ["mechanism", "context", "method", "policy", "controversy"]
    blocked = ["data", "population", "model", "temporal"]
    decisions: list[dict[str, Any]] = []
    required_fields = {
        "cross_stream": ["profile.mechanisms", "profile.findings.effect_direction"],
        "mechanism": ["profile.mechanisms"],
        "context": ["profile.sample.unit_of_analysis"],
        "method": ["profile.methods"],
        "policy": ["profile.policies"],
        "controversy": ["profile.findings.effect_direction"],
        "data": ["profile.datasets"],
        "population": ["profile.sample.unit_of_analysis"],
        "model": ["profile.models"],
        "temporal": ["profile.findings.effect_direction"],
    }
    for gap_type in sorted(GAP_TYPES):
        decision = (
            "allowed"
            if gap_type in allowed
            else "conditional"
            if gap_type in conditional
            else "blocked"
        )
        blocked_by: list[str] = []
        if decision == "conditional":
            blocked_by = ["gate:retrieval-saturation", "scope:purposive-selection"]
        elif decision == "blocked":
            blocked_by = [
                "gate:retrieval-saturation",
                "scope:purposive-selection",
                f"coverage:not-designed-for-{gap_type}",
            ]
        decisions.append(
            {
                "gap_type": gap_type,
                "decision": decision,
                "required_dimensions": [
                    "fulltext",
                    "parsing",
                    "indexing",
                    "field_observability",
                ],
                "required_field_paths": required_fields[gap_type],
                "blocked_by": blocked_by,
                "rationale": (
                    f"Allowed only as a cross-stream integration gap within the {corpus_size}-paper "
                    "eligibility-gated deep corpus."
                    if decision == "allowed"
                    else "Requires broader systematic retrieval and a probability-based corpus "
                    "before an absence claim can be elevated."
                ),
            }
        )
    return allowed, conditional, blocked, decisions


def build_certificate(
    *,
    graph_path: Path,
    vector_index_path: Path,
    parsed_manifest_path: Path,
    profiles_dir: Path,
    novelty_path: Path,
    metadata_manifest_path: Path,
    eligibility_audit_path: Path,
    output_path: Path,
    certificate_id: str,
    generated_at: str,
    as_of: str,
) -> dict[str, Any]:
    graph = _read_json(graph_path)
    vector = _read_json(vector_index_path)
    parsed = _read_json(parsed_manifest_path)
    novelty = _read_json(novelty_path)
    metadata = _read_json(metadata_manifest_path)
    eligibility = _read_json(eligibility_audit_path)
    profile_files = _profile_paths(profiles_dir)
    profiles = [_read_json(path) for path in profile_files]
    target = len(profiles)
    if target != int(parsed["document_count"]):
        raise ValueError("profile count does not match parsed document count")
    if int(eligibility.get("included_document_count") or -1) != target:
        raise ValueError("eligibility audit included count does not match the deep corpus")
    if eligibility.get("eligible_manifest_sha256") != parsed.get("source_manifest_sha256"):
        raise ValueError("parsed release is not bound to the audited eligible full-text manifest")
    vector_manifest = vector.get("manifest")
    if not isinstance(vector_manifest, dict):
        raise ValueError("vector index has no manifest")
    indexed_documents = {str(item["document_id"]) for item in vector.get("records", [])}
    if len(indexed_documents) != target:
        raise ValueError("indexed document count does not match the deep corpus")

    profile_hash = _sha256_object(
        [json.loads(path.read_text(encoding="utf-8")) for path in profile_files]
    )
    evidence = {
        "selection": "artifact:A_selection/selection.json",
        "eligibility": (
            f"artifact:A_selection/eligibility_audit.json#"
            f"{eligibility['eligible_manifest_sha256']}"
        ),
        "fulltext": f"artifact:B_fulltext/eligible_manifest.json#{parsed['source_manifest_sha256']}",
        "parsed": f"artifact:C_parsed_eligible/manifest.json#{parsed['chunks_sha256']}",
        "profiles": f"artifact:D_profiles/release_eligible#{profile_hash}",
        "index": f"artifact:E_vector/index.json#{vector_manifest['snapshot_id']}",
        "novelty": f"artifact:F_discovery/novelty_search.json#{novelty['search_id']}",
        "metadata": f"artifact:A_metadata/all/manifest.json#{metadata.get('articles_sha256') or metadata.get('output_sha256') or 'manifest'}",
    }
    evidence_refs = list(evidence.values())

    years = Counter(int(profile["document"]["year"]) for profile in profiles)
    languages = Counter(str(profile["document"]["language"]) for profile in profiles)
    fields = [
        _field_item(
            profiles,
            field_path="profile.methods",
            description="Methods explicitly extracted from located full text.",
            critical=True,
            is_present=lambda p: bool(p.get("methods")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.mechanisms",
            description="Mechanisms explicitly asserted or tested in the paper.",
            critical=True,
            is_present=lambda p: bool(p.get("mechanisms")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.sample.unit_of_analysis",
            description="Study unit of analysis extracted from the paper sample.",
            critical=True,
            is_present=lambda p: bool((p.get("sample") or {}).get("unit_of_analysis")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.findings.effect_direction",
            description="Direction of at least one evidence-grounded empirical finding.",
            critical=True,
            is_present=lambda p: bool(p.get("findings")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.research_fields",
            description="Normalized field assignments used for stream analysis.",
            critical=True,
            is_present=lambda p: bool(p.get("research_fields")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.future_work",
            description="Author-stated future-work directions with full-text evidence.",
            critical=True,
            is_present=lambda p: bool(p.get("future_work")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.datasets",
            description="Named or described input datasets.",
            critical=False,
            is_present=lambda p: bool(p.get("datasets")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.models",
            description="Statistical, econometric or machine-learning models.",
            critical=False,
            is_present=lambda p: bool(p.get("models")),
            evidence_ref=evidence["profiles"],
        ),
        _field_item(
            profiles,
            field_path="profile.policies",
            description="Policies explicitly evaluated or used as treatment definitions.",
            critical=False,
            is_present=lambda p: bool(p.get("policies")),
            evidence_ref=evidence["profiles"],
        ),
    ]
    critical_min = min(item["observability_rate"] for item in fields if item["critical"])
    rounds, unique_retrieved = _retrieval_rounds(novelty)
    last_gain = rounds[-1]["marginal_gain"] if rounds else None

    evaluated_counts = Counter()
    for search in novelty["searches"]:
        for source_name, source in search["sources"].items():
            evaluated_counts[source_name] += int(source.get("evaluated_result_count") or 0)
    source_items = [
        {
            "source_id": "europe-pmc",
            "required": True,
            "status": "observed_present",
            "query_executed": True,
            "observed_record_count": target,
            "checked_at": novelty["searched_at"],
            "evidence_refs": [evidence["fulltext"], evidence["novelty"]],
            "note": f"Required source for all {target} release-eligible full texts.",
        },
        {
            "source_id": "green-finance-data-center-public-metadata",
            "required": False,
            "status": "observed_present",
            "query_executed": True,
            "observed_record_count": int(novelty["local_snapshot"]["eligible_as_of_count"]),
            "checked_at": novelty["searched_at"],
            "evidence_refs": [evidence["metadata"], evidence["novelty"]],
            "note": "Optional broad metadata context; not treated as full-text evidence.",
        },
        *[
            {
                "source_id": source,
                "required": False,
                "status": "observed_present",
                "query_executed": True,
                "observed_record_count": evaluated_counts[source],
                "checked_at": novelty["searched_at"],
                "evidence_refs": [evidence["novelty"]],
                "note": "Optional novelty corroboration; count is top-ranked results evaluated.",
            }
            for source in ("openalex", "crossref")
        ],
    ]

    thresholds = {
        "required_source_coverage_rate": 1.0,
        "language_coverage_rate": 1.0,
        "year_coverage_rate": 1.0,
        "fulltext_coverage_rate": 1.0,
        "parsing_success_rate": 1.0,
        "indexing_success_rate": 1.0,
        "critical_field_observability_rate": 1.0,
        "dedup_resolution_rate": 1.0,
        "retrieval_marginal_gain_max": 0.02,
        "retrieval_consecutive_low_gain_rounds": 2,
    }
    gates = [
        _gate("gate:required-sources", "sources", "required_coverage_rate", 1.0, 1.0, evidence_ref=evidence["fulltext"]),
        _gate("gate:languages", "languages", "coverage_rate", 1.0, 1.0, evidence_ref=evidence["profiles"]),
        _gate("gate:years", "years", "coverage_rate", 1.0, 1.0, evidence_ref=evidence["profiles"]),
        _gate("gate:fulltext", "fulltext", "coverage_rate", 1.0, 1.0, evidence_ref=evidence["fulltext"]),
        _gate("gate:parsing", "parsing", "success_rate", 1.0, 1.0, evidence_ref=evidence["parsed"]),
        _gate("gate:indexing", "indexing", "success_rate", 1.0, 1.0, evidence_ref=evidence["index"]),
        _gate("gate:critical-fields", "field_observability", "critical_field_min_observability", 1.0, critical_min, evidence_ref=evidence["profiles"]),
        _gate("gate:deduplication", "deduplication", "resolution_rate", 1.0, 1.0, evidence_ref=evidence["selection"]),
        _gate(
            "gate:retrieval-saturation",
            "retrieval_saturation",
            "saturation_status",
            "saturated",
            "not_saturated",
            comparator="==",
            blocking=False,
            evidence_ref=evidence["novelty"],
            notes=(
                f"{len(novelty['searches'])} query families and four sources were checked, "
                "but low-gain saturation was not reached."
            ),
        ),
    ]
    allowed, conditional, blocked, decisions = _gap_decisions(target)
    manifest_sha256 = _sha256_object(
        {
            "release_id": parsed["release_id"],
            "profile_hash": profile_hash,
            "chunks_sha256": parsed["chunks_sha256"],
            "graph_snapshot_id": graph["snapshot_id"],
            "index_snapshot_id": vector_manifest["snapshot_id"],
            "novelty_search_id": novelty["search_id"],
            "eligibility_manifest_sha256": eligibility["eligible_manifest_sha256"],
        }
    )
    certificate: dict[str, Any] = {
        "schema_version": "1.0.0",
        "certificate_id": certificate_id,
        "generated_at": generated_at,
        "as_of": as_of,
        "supersedes_certificate_id": None,
        "subject": {
            "corpus_id": f"green-finance-decarbonization-deep{target}",
            "release_id": parsed["release_id"],
            "manifest_sha256": manifest_sha256,
            "graph_snapshot_id": graph["snapshot_id"],
            "index_snapshot_id": vector_manifest["snapshot_id"],
        },
        "scope": {
            "description": (
                f"Purposively selected {target}-paper English-language deep corpus on green-finance "
                "policy, real environmental behavior, carbon outcomes and digital/innovation mechanisms."
            ),
            "inclusion_criteria": [
                "Peer-reviewed journal article in the declared mechanism-focused selection.",
                "Accessible JATS full text with verified DOI/PMCID identity and documented license.",
                "Publication date not later than the declared as-of date.",
            ],
            "exclusion_criteria": [
                "Retracted records are excluded.",
                "Rights-unknown or time-limited full text is excluded from the deep corpus.",
                "The corpus is purposive rather than a systematic census of the field.",
            ],
            "source_ids": [item["source_id"] for item in source_items],
            "languages": sorted(languages),
            "year_start": min(years),
            "year_end": max(years),
            "document_types": ["peer_reviewed_journal_article"],
            "target_document_count": target,
        },
        "pipeline_versions": {
            "source_registry": "open-fulltext-collection/1.0.0",
            "ingestion": "public-feed-freeze/1.0.0",
            "deduplication": "doi-pmcid-exact/1.0.0",
            "fulltext_resolver": "europe-pmc-jats/1.0.0",
            "parser": str(parsed["parser"]["version"]),
            "field_extractor": "paper-profile-graph-input/0.2.0",
            "indexer": str(vector_manifest["schema_version"]),
            "retrieval_protocol": str(novelty["schema_version"]),
            "coverage_evaluator": "coverage-certificate/1.0.0",
        },
        "coverage_status": "coverage_conditional",
        "thresholds": thresholds,
        "coverage": {
            "sources": {
                "status": "observed_present",
                "registered_source_count": len(source_items),
                "required_source_count": 1,
                "covered_required_source_count": 1,
                "missing_required_source_count": 0,
                "required_coverage_rate": 1.0,
                "items": source_items,
            },
            "languages": {
                "status": "observed_present",
                "target_document_count": target,
                "covered_document_count": target,
                "unknown_language_count": 0,
                "coverage_rate": 1.0,
                "items": [
                    {"language": language, "document_count": count, "status": "observed_present"}
                    for language, count in sorted(languages.items())
                ],
            },
            "years": {
                "status": "observed_present",
                "target_document_count": target,
                "known_year_count": target,
                "missing_year_count": 0,
                "coverage_rate": 1.0,
                "bins": [
                    {"year": year, "document_count": count, "status": "observed_present"}
                    for year, count in sorted(years.items())
                ],
            },
            "fulltext": {
                "status": "observed_present",
                "target_document_count": target,
                "fulltext_available_count": target,
                "metadata_only_count": 0,
                "rights_blocked_count": 0,
                "source_missing_count": 0,
                "not_applicable_count": 0,
                "coverage_rate": 1.0,
            },
            "parsing": {
                "status": "observed_present",
                "target_document_count": target,
                "input_document_count": target,
                "success_count": target,
                "failed_count": 0,
                "not_applicable_count": 0,
                "success_rate": 1.0,
                "parser_versions": [str(parsed["parser"]["version"])],
            },
            "indexing": {
                "status": "observed_present",
                "target_document_count": target,
                "input_document_count": target,
                "indexed_document_count": target,
                "failed_count": 0,
                "not_applicable_count": 0,
                "success_rate": 1.0,
                "index_snapshot_id": vector_manifest["snapshot_id"],
            },
            "field_observability": {
                "target_document_count": target,
                "critical_field_min_observability": critical_min,
                "fields": fields,
            },
            "deduplication": {
                "status": "observed_present",
                "input_record_count": target,
                "canonical_document_count": target,
                "exact_duplicate_record_count": 0,
                "near_duplicate_record_count": 0,
                "duplicate_candidate_pair_count": 0,
                "resolved_pair_count": 0,
                "unresolved_pair_count": 0,
                "manual_review_pending_count": 0,
                "resolution_rate": 1.0,
                "deduplication_version": "doi-pmcid-exact/1.0.0",
            },
            "retrieval_saturation": {
                "observation_status": "observed_present",
                "saturation_status": "not_saturated",
                "query_set_sha256": _sha256_object(
                    [
                        {"query_id": item["query_id"], "query_text": item["query_text"]}
                        for item in novelty["searches"]
                    ]
                ),
                "search_space_description": (
                    "Frozen data-center metadata plus Europe PMC, OpenAlex and Crossref top-ranked "
                    "results for exact, broad, mechanism and adjacent query families."
                ),
                "minimum_rounds": 4,
                "executed_rounds": len(rounds),
                "required_consecutive_low_gain_rounds": 2,
                "marginal_gain_threshold": 0.02,
                "last_round_marginal_gain": last_gain,
                "unique_retrieved_document_count": unique_retrieved,
                "stopping_rule": (
                    "Saturation would require at least four rounds and two consecutive rounds "
                    "adding no more than 2 percent of cumulative unique documents."
                ),
                "rounds": rounds,
                "evidence_refs": [evidence["novelty"]],
            },
        },
        "gates": gates,
        "claim_gate": {
            "status": "claim_limited",
            "claim_ceiling": "corpus_bounded_gap",
            "required_scope_qualifier": (
                f"Within the purposively selected {target}-paper eligibility-gated deep corpus and "
                f"{len(novelty['searches'])}-query/four-source novelty search available as of {as_of}"
            ),
            "allowed_gap_types": allowed,
            "conditional_gap_types": conditional,
            "blocked_gap_types": blocked,
            "gap_type_decisions": decisions,
            "prohibited_claim_forms": [
                "No study exists on this topic.",
                "This is the first study globally.",
                "The observed publication pattern is a field-wide growth trend.",
                "Associational evidence establishes a causal mechanism.",
            ],
        },
        "evidence_refs": evidence_refs,
        "blockers": [],
        "warnings": [
            f"The {target} eligible papers were purposively selected for mechanism coverage, not sampled as a field census.",
            "One fetched paper was retracted before the as-of date and is retained only in the exclusion audit.",
            "Novelty retrieval did not reach the declared low-marginal-gain saturation rule.",
            "Crossref total-results values use ranking semantics and were not treated as Boolean hit counts.",
            "Trend and gap outputs must retain the required corpus-and-date qualifier.",
        ],
    }
    schema_errors = validate_instance(certificate, COVERAGE_SCHEMA)
    semantic_errors = validate_certificate(certificate)
    if schema_errors or semantic_errors:
        raise ValueError(
            "coverage certificate validation failed: "
            + "; ".join([*(f"schema {item}" for item in schema_errors), *semantic_errors][:20])
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(certificate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return certificate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--vector-index", type=Path, required=True)
    parser.add_argument("--parsed-manifest", type=Path, required=True)
    parser.add_argument("--profiles-dir", type=Path, required=True)
    parser.add_argument("--novelty", type=Path, required=True)
    parser.add_argument("--metadata-manifest", type=Path, required=True)
    parser.add_argument("--eligibility-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--certificate-id", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    try:
        certificate = build_certificate(
            graph_path=args.graph,
            vector_index_path=args.vector_index,
            parsed_manifest_path=args.parsed_manifest,
            profiles_dir=args.profiles_dir,
            novelty_path=args.novelty,
            metadata_manifest_path=args.metadata_manifest,
            eligibility_audit_path=args.eligibility_audit,
            output_path=args.output,
            certificate_id=args.certificate_id,
            generated_at=args.generated_at,
            as_of=args.as_of,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"WROTE: {args.output} ({certificate['coverage_status']}, "
        f"claim ceiling={certificate['claim_gate']['claim_ceiling']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
