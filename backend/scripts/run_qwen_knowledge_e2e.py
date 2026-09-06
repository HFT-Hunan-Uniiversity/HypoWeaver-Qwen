from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

import httpx


DEFAULT_QUESTION = "绿色金融政策如何影响企业绿色技术创新？"


def _checked(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} failed "
            f"with HTTP {response.status_code}: {response.text[:2000]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected response from {response.request.url.path}")
    return payload


def _evidence_references(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_chunk_ids":
                if not isinstance(item, list):
                    raise ValueError("plan evidence_chunk_ids must be a list")
                for chunk_id in item:
                    if not isinstance(chunk_id, str) or not chunk_id:
                        raise ValueError("plan contains an invalid evidence chunk reference")
                    yield chunk_id
            else:
                yield from _evidence_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _evidence_references(item)


def _validate_bundle(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    raw_hits = bundle.get("evidence_hits") or []
    if not isinstance(raw_hits, list) or not raw_hits:
        raise ValueError("real knowledge search returned no evidence hits")

    hits: list[dict[str, Any]] = []
    chunk_ids: set[str] = set()
    content_identities: set[tuple[str, str]] = set()
    for raw_hit in raw_hits:
        if not isinstance(raw_hit, dict):
            raise ValueError("knowledge search returned a malformed evidence hit")
        hit = raw_hit
        chunk_id = str(hit.get("chunk_id") or "")
        text = str(hit.get("text") or "")
        content_sha256 = str(hit.get("content_sha256") or "")
        if not chunk_id or chunk_id in chunk_ids:
            raise ValueError("knowledge search returned a missing or duplicate chunk id")
        if not hit.get("has_fulltext"):
            raise ValueError("metadata-only hit crossed the full-text boundary")
        if hit.get("evidence_status") not in {"fulltext_located", "fulltext_verified"}:
            raise ValueError("retrieved hit lacks a located full-text status")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != content_sha256:
            raise ValueError("retrieved evidence content hash mismatch")
        identity = (str(hit.get("document_version")), content_sha256)
        if identity in content_identities:
            raise ValueError("duplicate source-version/content hit crossed the API")
        chunk_ids.add(chunk_id)
        content_identities.add(identity)
        hits.append(hit)
    return hits, chunk_ids


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_label": plan.get("field_label"),
        "stream_label": plan.get("stream_label"),
        "gap_type": plan.get("gap_type"),
        "gap_title": plan.get("gap_title"),
        "gap_statement": plan.get("gap_statement"),
        "candidate_research_question": plan.get("candidate_research_question"),
        "hypothesis_title": plan.get("hypothesis_title"),
        "hypothesis_statement": plan.get("hypothesis_statement"),
        "falsifiable_form": plan.get("falsifiable_form"),
        "required_inputs": plan.get("required_inputs") or [],
        "blocking_questions": plan.get("blocking_questions") or [],
        "scores": plan.get("scores") or {},
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    headers = {"X-Hypoweaver-Token": args.workflow_token}
    with httpx.Client(
        base_url=args.workflow_url,
        headers=headers,
        timeout=args.timeout_seconds,
    ) as client:
        workflow_health = _checked(client.get("/api/v1/health"))
        knowledge_health = _checked(client.get("/api/v1/knowledge/health"))
        if args.generation_input is not None:
            generation = json.loads(args.generation_input.read_text(encoding="utf-8"))
            if not isinstance(generation, dict):
                raise ValueError("saved Qwen generation must be a JSON object")
            generation_source = "saved_authorized_output"
        else:
            generation = _checked(
                client.post(
                    "/api/v1/discovery/plans/generate",
                    json={
                        "search": {
                            "question": args.question,
                            "top_k": args.top_k,
                            "max_graph_edges": args.max_graph_edges,
                        },
                        "context": {
                            "goal": (
                                "Identify one corpus-bounded, falsifiable research gap and hypothesis."
                            ),
                            "unit_of_analysis": "firm-region-year",
                            "sample_period": "To be determined after H1 data review",
                            "constraints": [
                                "Do not claim global novelty beyond the delivered corpus.",
                                "Do not treat graph candidates as scientific evidence.",
                                (
                                    "Do not invent a dataset, coefficient, significance, or "
                                    "completed result."
                                ),
                            ],
                        },
                    },
                )
            )
            generation_source = "live_qwen_call"
        bundle = generation.get("evidence_bundle")
        plan = generation.get("plan")
        if not isinstance(bundle, dict) or not isinstance(plan, dict):
            raise ValueError("Qwen generation response is missing the evidence bundle or plan")
        hits, allowed_chunk_ids = _validate_bundle(bundle)
        referenced_chunk_ids = set(_evidence_references(plan))
        if not referenced_chunk_ids:
            raise ValueError("Qwen plan contains no evidence references")
        outside_bundle = sorted(referenced_chunk_ids - allowed_chunk_ids)
        if outside_bundle:
            raise ValueError(
                "Qwen plan cited evidence outside the returned bundle: "
                + ", ".join(outside_bundle)
            )

        args.full_output.parent.mkdir(parents=True, exist_ok=True)
        args.full_output.write_text(
            json.dumps(generation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        review_note = (
            "Technical E2E review only: every evidence reference was verified against the returned "
            "EvidenceBundle; this is not scientific approval."
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
                        "Technical integration launch only; stop at H1 until an authorized dataset "
                        "and scientific reviewer approve the design."
                    ),
                    "mode": "fixture",
                    "research_model_provider": "code_owned",
                },
            )
        )

    run_state = launched.get("run")
    case = launched.get("case_submission")
    if not isinstance(run_state, dict) or not isinstance(case, dict):
        raise ValueError("launch response is missing run or case-submission state")
    intake = case.get("intake_readiness")
    if not isinstance(intake, dict):
        raise ValueError("launch response is missing intake readiness")
    if run_state.get("current_gate") != "H1":
        raise ValueError(f"technical launch did not stop at H1: {run_state.get('current_gate')}")
    if run_state.get("status") != "waiting_human":
        raise ValueError(
            f"technical launch did not wait for human review: {run_state.get('status')}"
        )
    if intake.get("can_execute") is not False:
        raise ValueError("technical launch unexpectedly became executable without H1 data review")

    receipt = {
        "schema_version": "qwen-knowledge-e2e-receipt/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authorization_scope": (
            "User-authorized transmission of only the retrieved internal full-text excerpts in "
            "this EvidenceBundle to DashScope/Qwen."
        ),
        "workflow_health": workflow_health,
        "knowledge_health": knowledge_health,
        "search": {
            "question": bundle.get("question"),
            "bundle_id": bundle.get("bundle_id"),
            "corpus_snapshot_id": bundle.get("corpus_snapshot_id"),
            "evidence_hit_count": len(hits),
            "graph_candidate_count": len(bundle.get("graph_edges") or []),
            "all_hits_fulltext": True,
            "all_content_hashes_verified": True,
            "duplicate_content_identities": 0,
            "referenced_chunk_count": len(referenced_chunk_ids),
            "all_plan_references_inside_bundle": True,
            "top_hits": [
                {
                    "document_id": hit.get("document_id"),
                    "chunk_id": hit.get("chunk_id"),
                    "retrieval_score": hit.get("retrieval_score"),
                    "publication_year": hit.get("publication_year"),
                    "content_sha256": hit.get("content_sha256"),
                }
                for hit in hits
            ],
            "warnings": bundle.get("warnings") or [],
        },
        "qwen_generation": {
            "external_qwen_used": True,
            "generation_source": generation_source,
            "model_usage": generation.get("model_usage") or {},
            "warnings": generation.get("warnings") or [],
            "plan_summary": _plan_summary(plan),
        },
        "technical_launch": {
            "scientific_approval": False,
            "review_note": review_note,
            "reviewer": reviewed.get("reviewer"),
            "gap_cards": len(reviewed.get("gap_cards") or []),
            "hypothesis_cards": len(reviewed.get("hypothesis_cards") or []),
            "run_id": run_state.get("id"),
            "run_status": run_state.get("status"),
            "current_gate": run_state.get("current_gate"),
            "intake_can_execute": intake.get("can_execute"),
            "intake_blockers": intake.get("blockers") or [],
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an explicitly authorized Aug-23 EvidenceBundle through Qwen and stop at H1."
        )
    )
    parser.add_argument("--workflow-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--workflow-token",
        default=os.getenv("HYPOWEAVER_API_TOKEN", ""),
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--max-graph-edges", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument(
        "--generation-input",
        type=Path,
        help="Reuse a previously saved authorized Qwen generation without another model call.",
    )
    parser.add_argument("--full-output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.workflow_token:
        parser.error("--workflow-token or HYPOWEAVER_API_TOKEN is required")
    receipt = run(args)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
