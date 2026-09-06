#!/usr/bin/env python3
"""Align PaperProfile evidence to a parsed JATS release and its chunk IDs.

The extractor may author claims against XML section locators before chunking is
final.  This release step makes the graph and retrieval paths share the same
document/version/release/asset identity and proves that each full-text quote is
contained verbatim in the referenced chunk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reason.build_research_graph import GraphBuilder  # noqa: E402


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        values.append(value)
    return values


def _profile_doi(profile: dict[str, Any]) -> str:
    document = profile.get("document") or {}
    doi = str(document.get("doi") or "").strip().casefold()
    if not doi:
        document_id = str(document.get("document_id") or "")
        if document_id.casefold().startswith("doi:"):
            doi = document_id[4:].strip().casefold()
    if not doi:
        raise ValueError(f"profile {profile.get('profile_id')} has no DOI")
    return doi


def _locator_score(evidence: dict[str, Any], chunk: dict[str, Any]) -> tuple[int, str]:
    hint = _normalize_space(str(evidence.get("section") or "")).casefold()
    xml_id = str(chunk.get("xml_id") or "").casefold()
    section = _normalize_space(str(chunk.get("section") or "")).casefold()
    score = 0
    if hint and xml_id and xml_id in hint:
        score += 4
    if hint and section and (hint in section or section in hint):
        score += 2
    return score, str(chunk.get("chunk_id") or "")


def _align_one(
    profile: dict[str, Any],
    *,
    parsed_manifest: dict[str, Any],
    fulltext_manifest: dict[str, Any],
    parsed_dir: Path,
    chunks_by_document: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    doi = _profile_doi(profile)
    manifest_documents = {
        str(item.get("doi") or "").casefold(): item
        for item in parsed_manifest.get("documents", [])
    }
    fulltext_items = {
        str(item.get("doi") or "").casefold(): item
        for item in fulltext_manifest.get("items", [])
    }
    if doi not in manifest_documents or doi not in fulltext_items:
        raise ValueError(f"DOI {doi} is absent from parsed/full-text manifests")
    document_entry = manifest_documents[doi]
    fulltext_item = fulltext_items[doi]
    parsed = _read_json(parsed_dir / str(document_entry["parsed_file"]))
    document_id = str(document_entry["document_id"])
    document_version = str(document_entry["document_version"])
    release_id = str(parsed_manifest["release_id"])
    asset_id = str(document_entry["asset_id"])
    content_sha256 = str(document_entry["raw_sha256"])
    pmcid = str(document_entry["pmcid"])
    source_uri = str(fulltext_item.get("source_url") or parsed.get("source_uri") or "")
    access_level = str(fulltext_item.get("access_level") or parsed.get("access_level") or "unknown")
    license_value = str(fulltext_item.get("license") or parsed.get("license") or "")
    rights_status = str(fulltext_item.get("rights_status") or parsed.get("rights_status") or "unknown")

    output = json.loads(json.dumps(profile))
    output["profile_id"] = f"paper-profile:epmc:{pmcid}:v0.2.0"
    document = output["document"]
    document.update(
        {
            "document_id": document_id,
            "document_version": document_version,
            "release_id": release_id,
            "asset_id": asset_id,
            "content_sha256": content_sha256,
            "rights_status": rights_status,
            "parsed_doc_version": str(parsed.get("schema_version") or "greenfin-parsed-jats/1.0.0"),
            "source_uri": source_uri,
        }
    )

    chunks = chunks_by_document.get(document_id) or []
    aligned = 0
    for evidence in output.get("evidence", []):
        evidence.update(
            {
                "document_id": document_id,
                "document_version": document_version,
                "release_id": release_id,
                "asset_id": asset_id,
                "content_sha256": content_sha256,
                "access_level": access_level,
                "license": license_value,
            }
        )
        source_type = evidence.get("source_type")
        if source_type not in {"paper_fulltext", "paper_abstract"}:
            evidence["chunk_id"] = None
            continue
        quote = _normalize_space(str(evidence.get("quote") or ""))
        if not quote:
            raise ValueError(f"{output['profile_id']}:{evidence.get('evidence_id')}: blank quote")
        candidates: list[tuple[tuple[int, str], dict[str, Any], int]] = []
        for chunk in chunks:
            chunk_text = str(chunk.get("text") or "")
            start = chunk_text.find(quote)
            if start < 0:
                continue
            if str(chunk.get("source_type")) != source_type:
                continue
            candidates.append((_locator_score(evidence, chunk), chunk, start))
        if not candidates:
            raise ValueError(
                f"{output['profile_id']}:{evidence.get('evidence_id')}: quote is not "
                f"contained in one {source_type} chunk; shorten/correct the quote"
            )
        candidates.sort(key=lambda item: (-item[0][0], item[0][1]))
        _score, chunk, start = candidates[0]
        evidence.update(
            {
                "quote": quote,
                "chunk_id": chunk["chunk_id"],
                "section": chunk["section"],
                "page": None,
                "start_char": start,
                "end_char": start + len(quote),
                "source_uri": chunk.get("source_ref") or source_uri,
            }
        )
        aligned += 1

    audit = {
        "profile_id": output["profile_id"],
        "pmcid": pmcid,
        "doi": doi,
        "document_id": document_id,
        "document_version": document_version,
        "evidence_count": len(output.get("evidence", [])),
        "aligned_scientific_evidence_count": aligned,
    }
    GraphBuilder._validate_profile(output, require_explicit_evidence=True)
    return output, audit


def align_profiles(
    profiles_dir: Path,
    parsed_dir: Path,
    fulltext_manifest_path: Path,
    output_dir: Path,
    eligibility_decisions_path: Path | None = None,
) -> dict[str, Any]:
    parsed_manifest = _read_json(parsed_dir / "manifest.json")
    fulltext_manifest = _read_json(fulltext_manifest_path)
    chunks = _read_jsonl(parsed_dir / str(parsed_manifest["chunks_file"]))
    chunks_by_document: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(str(chunk["document_id"]), []).append(chunk)

    candidates = sorted(profiles_dir.glob("PMC*.json"))
    if not candidates:
        raise ValueError(f"{profiles_dir}: no profile JSON files")
    eligibility_sha256: str | None = None
    if eligibility_decisions_path is not None:
        eligibility_raw = eligibility_decisions_path.read_bytes()
        eligibility = json.loads(eligibility_raw.decode("utf-8-sig"))
        if not isinstance(eligibility, dict) or eligibility.get("schema_version") != "document-eligibility/1.0.0":
            raise ValueError("unsupported document eligibility registry")
        included_pmcids = {
            str(item.get("pmcid") or "").strip().upper()
            for item in eligibility.get("decisions", [])
            if isinstance(item, dict) and item.get("decision") == "include"
        }
        if not included_pmcids or "" in included_pmcids:
            raise ValueError("eligibility registry has no complete include PMCID set")
        candidate_by_pmcid = {path.stem.upper(): path for path in candidates}
        missing = sorted(included_pmcids - set(candidate_by_pmcid))
        if missing:
            raise ValueError(f"publishable profiles are missing for {missing}")
        candidates = [candidate_by_pmcid[pmcid] for pmcid in sorted(included_pmcids)]
        eligibility_sha256 = _sha256_bytes(eligibility_raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    audits: list[dict[str, Any]] = []
    for path in candidates:
        profile, audit = _align_one(
            _read_json(path),
            parsed_manifest=parsed_manifest,
            fulltext_manifest=fulltext_manifest,
            parsed_dir=parsed_dir,
            chunks_by_document=chunks_by_document,
        )
        target = output_dir / path.name
        target.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        audits.append(audit)
    manifest = {
        "schema_version": "paper-profile-alignment/1.0.0",
        "release_id": parsed_manifest["release_id"],
        "parsed_manifest_sha256": _sha256_bytes((parsed_dir / "manifest.json").read_bytes()),
        "chunks_sha256": parsed_manifest["chunks_sha256"],
        "eligibility_decisions_sha256": eligibility_sha256,
        "profile_count": len(audits),
        "profiles": audits,
    }
    (output_dir / "alignment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles-dir", type=Path, required=True)
    parser.add_argument("--parsed-dir", type=Path, required=True)
    parser.add_argument("--fulltext-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--eligibility-decisions",
        type=Path,
        help="optional document-eligibility/1.0.0 registry; only decision=include profiles are released",
    )
    args = parser.parse_args()
    try:
        manifest = align_profiles(
            args.profiles_dir,
            args.parsed_dir,
            args.fulltext_manifest,
            args.output_dir,
            args.eligibility_decisions,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        f"WROTE: {args.output_dir} ({manifest['profile_count']} profiles, "
        f"release {manifest['release_id']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
