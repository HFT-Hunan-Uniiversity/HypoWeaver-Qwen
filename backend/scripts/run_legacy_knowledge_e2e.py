from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx


DEFAULT_QUESTION = "绿色金融政策如何影响企业绿色技术创新？"


def _checked(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} failed "
            f"with HTTP {response.status_code}: {response.text[:1000]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected response from {response.request.url.path}")
    return payload


def _offline_fixture_plan(bundle: dict[str, Any]) -> dict[str, Any]:
    hits = bundle.get("evidence_hits") or []
    if not hits:
        raise ValueError("offline fixture requires at least one evidence hit")
    first = str(hits[0]["chunk_id"])
    second = str(hits[1]["chunk_id"]) if len(hits) > 1 else first
    shared = [first, second] if second != first else [first]
    return {
        "field_label": "Green finance and firm innovation",
        "stream_label": "Policy exposure, financing channel, and green innovation",
        "stream_description": (
            "A corpus-bounded technical fixture linking green-finance policy exposure, "
            "a financing-resource channel, and firm green-technology innovation."
        ),
        "findings": [
            {
                "key": "retrieved_policy_innovation_link",
                "statement": (
                    "The retrieved full-text evidence contains claims linking green-finance "
                    "policy exposure to firm green-technology innovation."
                ),
                "direction": "positive",
                "role": "support",
                "evidence_chunk_ids": [first],
            },
            {
                "key": "unresolved_channel_boundary",
                "statement": (
                    "The retrieved corpus does not by itself establish a single identified "
                    "financing mechanism for every represented population."
                ),
                "direction": "mixed",
                "role": "challenge",
                "evidence_chunk_ids": [second],
            },
        ],
        "constructs": [
            {
                "key": "green_finance_policy",
                "label": "Green-finance policy exposure",
                "definition": (
                    "Observed exposure of a firm or region to a specified green-finance policy."
                ),
                "granularity": "firm-region-year",
                "role": "predictor",
                "expected_direction": "positive",
                "evidence_chunk_ids": [first],
            },
            {
                "key": "green_technology_innovation",
                "label": "Firm green-technology innovation",
                "definition": (
                    "A pre-specified firm-level measure of green technological innovation output."
                ),
                "granularity": "firm-year",
                "role": "outcome",
                "expected_direction": "positive",
                "evidence_chunk_ids": shared,
            },
        ],
        "mechanisms": [
            {
                "key": "financing_resource_channel",
                "label": "Financing-resource channel",
                "description": (
                    "Policy exposure may alter financing constraints or resources available for "
                    "green research and development."
                ),
                "evidence_chunk_ids": [first],
            }
        ],
        "datasets": [
            {
                "key": "candidate_firm_panel",
                "label": "Candidate firm-region-year panel",
                "description": (
                    "A licensed panel would be required; this fixture does not assert that such "
                    "a dataset is currently available."
                ),
                "evidence_chunk_ids": [second],
            }
        ],
        "methods": [
            {
                "key": "panel_design_review",
                "label": "Panel identification design",
                "description": (
                    "A panel design whose treatment timing and identifying assumptions still "
                    "require H1 review."
                ),
                "evidence_chunk_ids": [second],
            }
        ],
        "models": [],
        "identification_strategies": [],
        "gap_type": "mechanism",
        "gap_title": "Financing-channel identification remains unresolved",
        "gap_statement": (
            "Within this delivered corpus, the financing-resource channel is not yet a frozen, "
            "dataset-bound causal estimand."
        ),
        "current_state": (
            "Retrieved full-text chunks describe policy, financing, and innovation associations."
        ),
        "missing_piece": (
            "A licensed dataset, frozen variables, and an approved identification design are missing."
        ),
        "why_important": (
            "Resolving the channel would separate a testable mechanism from a broad association."
        ),
        "candidate_research_question": (
            "Does green-finance policy exposure increase firm green-technology innovation through "
            "a financing-resource channel?"
        ),
        "hypothesis_title": "Financing-resource channel hypothesis",
        "hypothesis_statement": (
            "Green-finance policy exposure increases firm green-technology innovation by easing "
            "financing constraints or expanding resources for green research and development."
        ),
        "falsifiable_form": (
            "Reject the proposed channel if policy exposure does not predict the frozen financing "
            "measure, or if that measure does not predict the frozen innovation outcome under the "
            "approved design."
        ),
        "rationale": (
            "The fixture preserves the retrieved association while leaving mechanism and causality "
            "for later human review and data-bound testing."
        ),
        "mechanism_chain": [
            {
                "source_key": "green_finance_policy",
                "relation": "CHANGES",
                "target_key": "financing_resource_channel",
                "statement": "Policy exposure is expected to change financing resources.",
                "evidence_chunk_ids": [first],
            },
            {
                "source_key": "financing_resource_channel",
                "relation": "INCREASES",
                "target_key": "green_technology_innovation",
                "statement": "Financing resources are expected to increase green innovation.",
                "evidence_chunk_ids": [first],
            },
        ],
        "predictions": [
            {
                "key": "ordered_channel_prediction",
                "statement": (
                    "Approved policy exposure should predict the financing measure before the "
                    "innovation outcome changes."
                ),
                "observable_pattern": (
                    "Exposure, financing resources, and innovation follow the frozen temporal order."
                ),
                "would_falsify": (
                    "Either link is null, reversed, temporally inconsistent, or design-sensitive."
                ),
            }
        ],
        "boundary_conditions": [
            "Only populations and periods supported by the delivered corpus and a future licensed dataset."
        ],
        "unresolved_conflicts": [
            "The technical fixture has not adjudicated competing measures or identification strategies."
        ],
        "unit_of_analysis": "firm-region-year",
        "baseline_specification": (
            "Freeze policy exposure, innovation outcome, timing, fixed effects, and uncertainty "
            "estimation only after H1 data review."
        ),
        "major_threats": ["Selection and policy endogeneity", "Measurement error"],
        "required_inputs": ["Licensed firm panel", "Frozen data dictionary"],
        "blocking_questions": ["Which authorized dataset contains the required variables and timing?"],
        "validation_acceptance_criteria": [
            "Dataset provenance, variable coverage, treatment timing, and missingness pass H1 review."
        ],
        "novelty_queries": [
            "green finance financing channel green innovation",
            "green finance policy firm green patents mechanism",
            "financing constraints green technology innovation policy",
        ],
        "novelty_remaining_difference": (
            "Within the delivered corpus, a dataset-bound test of both channel links remains unresolved."
        ),
        "scores": {
            "novelty": 2,
            "theory": 3,
            "evidence": 3,
            "data": 1,
            "method": 1,
            "policy_value": 3,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    headers = {"X-Hypoweaver-Token": args.workflow_token}
    with httpx.Client(base_url=args.workflow_url, headers=headers, timeout=300) as client:
        workflow_health = _checked(client.get("/api/v1/health"))
        knowledge_health = _checked(client.get("/api/v1/knowledge/health"))
        bundle = _checked(
            client.post(
                "/api/v1/knowledge/search",
                json={
                    "question": args.question,
                    "top_k": args.top_k,
                    "max_graph_edges": args.max_graph_edges,
                },
            )
        )
        hits = bundle.get("evidence_hits") or []
        if not hits:
            raise ValueError("real knowledge search returned no evidence hits")
        content_identities: set[tuple[str, str]] = set()
        for hit in hits:
            text = str(hit.get("text") or "")
            if not hit.get("has_fulltext"):
                raise ValueError("metadata-only hit crossed the full-text boundary")
            if hit.get("evidence_status") not in {"fulltext_located", "fulltext_verified"}:
                raise ValueError("retrieved hit lacks a located full-text status")
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != hit.get("content_sha256"):
                raise ValueError("retrieved evidence content hash mismatch")
            identity = (str(hit.get("document_version")), str(hit.get("content_sha256")))
            if identity in content_identities:
                raise ValueError("duplicate source-version/content hit crossed the API")
            content_identities.add(identity)

        plan = _offline_fixture_plan(bundle)
        review_note = (
            "Technical fixture review only: evidence references and full-text boundaries were checked; "
            "this is not scientific approval."
        )
        review_payload = {
            "evidence_bundle": bundle,
            "plan": plan,
            "consistency_review": (
                (generation.get("consistency_reviews") or [None])[-1]
            ),
            "execution_readiness": generation.get("execution_readiness"),
            "review_note": review_note,
        }
        reviewed = _checked(
            client.post("/api/v1/discovery/plans/review", json=review_payload)
        )
        launched = _checked(
            client.post(
                "/api/v1/discovery/plans/launch",
                json={
                    **review_payload,
                    "approve_h0": True,
                    "approval_reason": (
                        "Technical fixture launch only; stop at H1 until an authorized dataset and "
                        "a scientific reviewer approve the research design."
                    ),
                    "mode": "fixture",
                    "research_model_provider": "code_owned",
                },
            )
        )

    run_state = launched["run"]
    case = launched["case_submission"]
    receipt = {
        "schema_version": "legacy-knowledge-e2e-receipt/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_health": workflow_health,
        "knowledge_health": knowledge_health,
        "search": {
            "question": bundle["question"],
            "bundle_id": bundle["bundle_id"],
            "corpus_snapshot_id": bundle["corpus_snapshot_id"],
            "evidence_hit_count": len(hits),
            "graph_candidate_count": len(bundle.get("graph_edges") or []),
            "all_hits_fulltext": True,
            "all_content_hashes_verified": True,
            "duplicate_content_identities": 0,
            "top_hits": [
                {
                    "document_id": hit["document_id"],
                    "chunk_id": hit["chunk_id"],
                    "retrieval_score": hit["retrieval_score"],
                    "publication_year": hit.get("publication_year"),
                    "content_sha256": hit["content_sha256"],
                }
                for hit in hits
            ],
            "warnings": bundle.get("warnings") or [],
        },
        "offline_fixture": {
            "external_qwen_used": False,
            "reason": (
                "Delivered full text is marked authenticated_internal_research_only; no explicit "
                "authorization was available to send excerpts to DashScope."
            ),
            "scientific_approval": False,
            "reviewer": reviewed.get("reviewer"),
            "gap_cards": len(reviewed.get("gap_cards") or []),
            "hypothesis_cards": len(reviewed.get("hypothesis_cards") or []),
            "run_id": run_state["id"],
            "run_status": run_state["status"],
            "current_gate": run_state["current_gate"],
            "intake_can_execute": case["intake_readiness"]["can_execute"],
            "intake_blockers": case["intake_readiness"]["blockers"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local Aug-23 knowledge boundary through a privacy-safe H1 fixture."
    )
    parser.add_argument("--workflow-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--workflow-token",
        default=os.getenv("HYPOWEAVER_API_TOKEN", ""),
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--max-graph-edges", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.workflow_token:
        parser.error("--workflow-token or HYPOWEAVER_API_TOKEN is required")
    receipt = run(args)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
