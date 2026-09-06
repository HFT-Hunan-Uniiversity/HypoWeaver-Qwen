from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from pydantic import ValidationError

import hypoweaver.api as api_module
from hypoweaver.adapters import (
    _safe_schema_error_details,
    _safe_schema_repair_guidance,
)
from hypoweaver.discovery_planner import DiscoveryPlanGeneration
from hypoweaver.discovery_pipeline import build_discovery_release_preview
from hypoweaver.discovery_planner import (
    DiscoveryResearcherContext,
    DiscoveryPlanGenerationRequest,
    compile_execution_readiness,
    compile_discovery_plan,
    generate_discovery_plan,
    generate_reviewed_discovery_plan,
    validate_plan_evidence,
)
from hypoweaver.knowledge_models import (
    EvidenceBundle,
    EvidenceHit,
    KnowledgeSearchRequest,
    SourceLocator,
)
from hypoweaver.models import (
    DiscoveryDatasetField,
    DiscoveryDatasetResource,
    DiscoveryPlan,
    QuestionPlanConsistencyReview,
)
from hypoweaver.engine import WorkflowEngine
from hypoweaver.repository import RunRepository


def _bundle() -> EvidenceBundle:
    hits = []
    for number, (document_id, title, text, year) in enumerate(
        (
            (
                "paper-current",
                "Current evidence",
                "Current studies associate the exposure with the outcome through a mechanism.",
                2025,
            ),
            (
                "paper-baseline",
                "Challenging evidence",
                "Earlier studies report mixed effects and identify measurement limitations.",
                2021,
            ),
        ),
        1,
    ):
        hits.append(
            EvidenceHit(
                document_id=document_id,
                document_version="fixture-v1",
                chunk_id=f"chunk-{number}",
                text=text,
                title=title,
                source_type="paper",
                source_locator=SourceLocator(section="Synthetic evidence"),
                source_url=f"https://example.test/{number}",
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                retrieval_score=1.0 - number / 10,
                has_fulltext=True,
                evidence_status="fulltext_verified",
                publication_year=year,
            )
        )
    return EvidenceBundle.build(
        request=KnowledgeSearchRequest(
            question="How does the exposure affect the outcome?",
            as_of=date(2026, 8, 25),
        ),
        corpus_snapshot_id="corpus:planner-test",
        evidence_hits=hits,
        generated_at=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc),
    )


def _plan() -> DiscoveryPlan:
    return DiscoveryPlan.model_validate(
        {
            "field_label": "Synthetic policy research",
            "stream_label": "Exposure, mechanism, and outcome",
            "stream_description": (
                "A bounded synthesis of exposure effects, mechanisms, and measurement limits."
            ),
            "findings": [
                {
                    "key": "supporting_effect",
                    "statement": "Current evidence links the exposure to the outcome through the mechanism.",
                    "direction": "positive",
                    "role": "support",
                    "evidence_chunk_ids": ["chunk-1"],
                },
                {
                    "key": "mixed_measurement",
                    "statement": "Earlier evidence reports mixed effects under limited measurement strategies.",
                    "direction": "mixed",
                    "role": "challenge",
                    "evidence_chunk_ids": ["chunk-2"],
                },
            ],
            "constructs": [
                {
                    "key": "exposure",
                    "label": "Exposure",
                    "definition": "The policy-relevant exposure assigned to observational units.",
                    "granularity": "unit-year",
                    "role": "predictor",
                    "expected_direction": "positive",
                    "evidence_chunk_ids": ["chunk-1"],
                },
                {
                    "key": "outcome",
                    "label": "Outcome",
                    "definition": "The observed outcome expected to respond to the exposure.",
                    "granularity": "unit-year",
                    "role": "outcome",
                    "expected_direction": "positive",
                    "evidence_chunk_ids": ["chunk-1", "chunk-2"],
                },
            ],
            "mechanisms": [
                {
                    "key": "resource_channel",
                    "label": "Resource channel",
                    "description": "The exposure changes resources that are available for the outcome.",
                    "evidence_chunk_ids": ["chunk-1"],
                }
            ],
            "datasets": [
                {
                    "key": "panel_dataset",
                    "label": "Candidate panel dataset",
                    "description": "A candidate unit-year panel described by the retrieved evidence.",
                    "evidence_chunk_ids": ["chunk-2"],
                }
            ],
            "methods": [
                {
                    "key": "panel_method",
                    "label": "Panel comparison",
                    "description": "A panel comparison method requiring design review before execution.",
                    "evidence_chunk_ids": ["chunk-2"],
                }
            ],
            "models": [],
            "identification_strategies": [],
            "gap_type": "mechanism",
            "gap_title": "Mechanism evidence remains incomplete",
            "gap_statement": (
                "Within this corpus, evidence does not resolve how the resource channel transmits the effect."
            ),
            "current_state": "Retrieved studies report an overall association and mixed measurement choices.",
            "missing_piece": "A direct, falsifiable assessment of the proposed resource channel is missing.",
            "why_important": "Resolving the channel would distinguish the proposed explanation from alternatives.",
            "candidate_research_question": "Does the exposure affect the outcome through the resource channel?",
            "hypothesis_title": "Resource-channel hypothesis",
            "hypothesis_statement": "The exposure increases the outcome through the resource channel.",
            "falsifiable_form": (
                "The hypothesis is rejected if the exposure does not predict the mechanism or the mechanism does not predict the outcome."
            ),
            "rationale": "The current evidence supports an association but leaves the transmission channel unresolved.",
            "mechanism_chain": [
                {
                    "source_key": "exposure",
                    "relation": "ACTIVATES",
                    "target_key": "resource_channel",
                    "statement": "The exposure is expected to activate the resource channel.",
                    "evidence_chunk_ids": ["chunk-1"],
                },
                {
                    "source_key": "resource_channel",
                    "relation": "INCREASES",
                    "target_key": "outcome",
                    "statement": "The resource channel is expected to increase the outcome.",
                    "evidence_chunk_ids": ["chunk-1"],
                },
            ],
            "predictions": [
                {
                    "key": "prediction_one",
                    "statement": "Higher exposure should predict stronger mechanism values and outcomes.",
                    "observable_pattern": "Exposure, mechanism, and outcome move in the predicted order.",
                    "would_falsify": "Either link is null, reversed, or unstable under the approved design.",
                }
            ],
            "boundary_conditions": ["Only the populations represented in the bounded corpus."],
            "unresolved_conflicts": ["Measurement choices differ across retrieved studies."],
            "unit_of_analysis": "unit-year",
            "baseline_specification": "Estimate the approved exposure-outcome relation with unit and year controls.",
            "major_threats": ["Confounding", "Measurement error"],
            "required_inputs": ["A verified unit-year dataset", "A frozen variable dictionary"],
            "blocking_questions": ["Is the candidate panel accessible and licensed?"],
            "validation_acceptance_criteria": ["All variables pass provenance and coverage checks."],
            "novelty_queries": [
                "exposure resource channel outcome",
                "exposure mechanism outcome panel",
                "resource channel measurement limits",
            ],
            "novelty_remaining_difference": (
                "Within the retrieved corpus, no source directly tests both links of the proposed chain."
            ),
            "scores": {
                "novelty": 3,
                "theory": 4,
                "evidence": 3,
                "data": 2,
                "method": 3,
                "policy_value": 4,
            },
        }
    )


def _pass_review() -> QuestionPlanConsistencyReview:
    return QuestionPlanConsistencyReview(
        decision="pass",
        exposure_preserved=True,
        outcome_preserved=True,
        qualifiers_preserved=True,
        rationale="The exposure, outcome, and stated mechanism qualifier are preserved.",
    )


class _Budget:
    @staticmethod
    def snapshot() -> dict:
        return {"total_attempts": 1}


class _Gateway:
    budget = _Budget()

    async def generate(self, prompt_key, payload, output_model):
        assert prompt_key == "discovery_planning"
        assert payload["evidence_hits"][0]["chunk_id"] == "chunk-1"
        assert output_model is DiscoveryPlan
        return _plan()


class _RepairGateway:
    budget = _Budget()

    def __init__(self) -> None:
        self.planning_calls = 0
        self.review_calls = 0
        self.planning_payloads: list[dict] = []

    async def generate(self, prompt_key, payload, output_model):
        if prompt_key == "discovery_planning":
            self.planning_calls += 1
            self.planning_payloads.append(payload)
            return _plan()
        if prompt_key == "discovery_consistency_review":
            self.review_calls += 1
            if self.review_calls == 1:
                return QuestionPlanConsistencyReview(
                    decision="requery",
                    exposure_preserved=True,
                    outcome_preserved=False,
                    qualifiers_preserved=False,
                    missing_concepts=["specified outcome"],
                    requery_terms=["specified outcome", "resource channel"],
                    rationale="The first candidate did not preserve the specified outcome qualifier.",
                )
            return _pass_review()
        raise AssertionError(prompt_key)


class _ReferenceRepairGateway:
    budget = _Budget()

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, prompt_key, payload, output_model):
        self.calls += 1
        if self.calls == 1:
            plan = _plan().model_copy(deep=True)
            plan.findings[0].evidence_chunk_ids = ["invented-adjacent-chunk"]
            return plan
        self_allowed = payload["reference_validation_failure"]["allowed_chunk_ids"]
        assert "invented-adjacent-chunk" not in self_allowed
        assert set(self_allowed) == {"chunk-1", "chunk-2"}
        return _plan()


class _KnowledgeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, request: KnowledgeSearchRequest) -> EvidenceBundle:
        self.queries.append(request.question)
        base = _bundle()
        return EvidenceBundle.build(
            request=request,
            corpus_snapshot_id=base.corpus_snapshot_id,
            evidence_hits=base.evidence_hits,
            generated_at=base.generated_at,
        )


class DiscoveryPlannerTests(unittest.IsolatedAsyncioTestCase):
    def test_model_validator_error_becomes_actionable_without_raw_message(self) -> None:
        payload = _plan().model_dump(mode="json")
        payload["constructs"][1]["role"] = "predictor"
        with self.assertRaises(ValidationError) as caught:
            DiscoveryPlan.model_validate(payload)

        details, count = _safe_schema_error_details(
            caught.exception,
            output_schema=DiscoveryPlan.model_json_schema(),
        )

        self.assertEqual(count, 1)
        self.assertEqual(details[0].loc, ())
        self.assertEqual(details[0].type, "discovery_role_cardinality")
        guidance = _safe_schema_repair_guidance(details)
        self.assertIn("恰好有一个 predictor 和一个 outcome", guidance)
        self.assertNotIn("discovery plan requires", guidance)

    async def test_qwen_plan_is_evidence_bounded(self) -> None:
        generated = await generate_discovery_plan(
            _bundle(),
            DiscoveryResearcherContext(goal="Build one falsifiable candidate."),
            gateway=_Gateway(),
        )
        self.assertEqual(generated.plan.hypothesis_title, "Resource-channel hypothesis")
        self.assertEqual(generated.model_usage["total_attempts"], 1)

    async def test_invalid_chunk_reference_gets_one_bounded_repair(self) -> None:
        gateway = _ReferenceRepairGateway()
        generated = await generate_discovery_plan(
            _bundle(),
            DiscoveryResearcherContext(goal="Build one falsifiable candidate."),
            gateway=gateway,
        )
        self.assertEqual(gateway.calls, 2)
        self.assertTrue(
            any("evidence-reference repair" in item for item in generated.warnings)
        )
        validate_plan_evidence(generated.plan, generated.evidence_bundle)

    async def test_reviewed_plan_compiles_to_group1_release(self) -> None:
        build = compile_discovery_plan(
            _bundle(),
            _plan(),
            reviewer="reviewer-chen",
            review_note="Reviewed every evidence reference and accepted this bounded draft.",
        )
        release = build_discovery_release_preview(build, reviewer="reviewer-chen")

        self.assertEqual(len(release.gap_cards), 1)
        self.assertEqual(len(release.hypothesis_cards), 1)
        self.assertEqual(release.hypothesis_cards[0]["hypothesis_id"], "hypothesis:online_candidate")
        self.assertEqual(release.reviewer, "reviewer-chen")

    async def test_unspecified_construct_direction_compiles_as_unknown(self) -> None:
        plan = _plan().model_copy(deep=True)
        for construct in plan.constructs:
            construct.expected_direction = "unspecified"
        build = compile_discovery_plan(
            _bundle(),
            plan,
            reviewer="reviewer-chen",
            review_note="Reviewed the unspecified directions as unresolved rather than directional.",
        )
        release = build_discovery_release_preview(build, reviewer="reviewer-chen")

        variables = release.hypothesis_cards[0]["variables"]
        self.assertEqual(variables["independent"][0]["expected_direction"], "unknown")
        self.assertEqual(variables["dependent"][0]["expected_direction"], "unknown")

    async def test_heterogeneous_finding_direction_matches_graph_contract(self) -> None:
        plan = _plan().model_copy(deep=True)
        plan.findings[0].direction = "heterogeneous"
        build = compile_discovery_plan(
            _bundle(),
            plan,
            reviewer="reviewer-chen",
            review_note="Reviewed heterogeneous evidence as a valid graph direction.",
        )
        release = build_discovery_release_preview(build, reviewer="reviewer-chen")
        finding = next(
            item
            for item in release.final_research_graph["nodes"]
            if item["id"] == "finding:supporting_effect"
        )
        self.assertEqual(finding["properties"]["effect_direction"], "heterogeneous")

    async def test_plan_without_dataset_or_method_compiles_as_unknown(self) -> None:
        plan = _plan().model_copy(deep=True)
        plan.datasets = []
        plan.methods = []
        plan.identification_strategies = []
        build = compile_discovery_plan(
            _bundle(),
            plan,
            reviewer="reviewer-chen",
            review_note="No dataset or method was established, so feasibility remains unknown.",
        )
        release = build_discovery_release_preview(build, reviewer="reviewer-chen")

        self.assertEqual(release.gap_cards[0]["data_feasibility"]["status"], "unknown")
        feasibility = release.hypothesis_cards[0]["feasibility"]
        self.assertEqual(feasibility["data_status"], "unknown")
        self.assertEqual(feasibility["method_status"], "unknown")

    async def test_plan_cannot_reference_another_bundle(self) -> None:
        plan = _plan().model_copy(deep=True)
        plan.findings[0].evidence_chunk_ids = ["outside-bundle"]
        with self.assertRaisesRegex(ValueError, "outside the EvidenceBundle"):
            validate_plan_evidence(plan, _bundle())

    async def test_execution_readiness_fails_closed_without_bound_assets(self) -> None:
        readiness = compile_execution_readiness(
            _plan(),
            DiscoveryResearcherContext(unit_of_analysis="unit-year"),
            consistency_review=_pass_review(),
        )
        self.assertFalse(readiness.can_execute)
        self.assertTrue(readiness.dataset_candidates)
        self.assertTrue(any("不可变哈希" in item for item in readiness.blockers))

    async def test_execution_readiness_compiles_complete_dataset_and_strategy(self) -> None:
        plan = _plan().model_copy(deep=True)
        plan.identification_strategies = [
            {
                "key": "panel_identification",
                "label": "Reviewed panel identification",
                "description": "A reviewed panel identification candidate for H1 diagnostics.",
                "evidence_chunk_ids": ["chunk-2"],
            }
        ]
        resource = DiscoveryDatasetResource(
            resource_id="asset-panel-v1",
            label="Immutable unit-year panel",
            filename="panel.csv",
            sha256="a" * 64,
            size_bytes=1024,
            license_status="verified_open",
            license_id="CC-BY-4.0",
            granularity="unit-year",
            time_key="year",
            join_keys=["unit_id"],
            fields=[
                DiscoveryDatasetField(name="unit_id", label="Unit ID", role="id"),
                DiscoveryDatasetField(name="year", label="Year", role="time"),
                DiscoveryDatasetField(name="exposure", label="Exposure", role="predictor"),
                DiscoveryDatasetField(name="outcome", label="Outcome", role="outcome"),
            ],
        )
        context = DiscoveryResearcherContext(
            unit_of_analysis="unit-year",
            dataset_resources=[resource],
        )
        readiness = compile_execution_readiness(
            plan,
            context,
            consistency_review=_pass_review(),
        )
        self.assertTrue(readiness.can_execute)
        self.assertEqual(readiness.status, "ready")
        self.assertTrue(all(item.status == "bound" for item in readiness.variable_dictionary))

    async def test_failed_consistency_review_blocks_h0_compilation(self) -> None:
        failed = QuestionPlanConsistencyReview(
            decision="requery",
            exposure_preserved=True,
            outcome_preserved=False,
            qualifiers_preserved=False,
            missing_concepts=["real outcome"],
            requery_terms=["real outcome"],
            rationale="The candidate substituted a neighboring outcome and lost the qualifier.",
        )
        with self.assertRaisesRegex(ValueError, "repeat retrieval"):
            compile_discovery_plan(
                _bundle(),
                _plan(),
                reviewer="reviewer-chen",
                review_note="The automated consistency gate did not pass this draft.",
                consistency_review=failed,
            )

    async def test_failed_consistency_review_triggers_one_retrieval_repair(self) -> None:
        client = _KnowledgeClient()
        gateway = _RepairGateway()
        generated = await generate_reviewed_discovery_plan(
            DiscoveryPlanGenerationRequest(
                search=KnowledgeSearchRequest(
                    question="How does the exposure affect the specified outcome?",
                    top_k=2,
                    min_unique_documents=2,
                ),
                context=DiscoveryResearcherContext(
                    goal="Preserve the specified outcome and build a falsifiable plan."
                ),
            ),
            knowledge_client=client,
            gateway=gateway,
        )

        self.assertEqual(generated.repair_count, 1)
        self.assertTrue(generated.final_consistency_passed)
        self.assertEqual(len(generated.retrieval_rounds), 2)
        self.assertEqual(gateway.planning_calls, 2)
        self.assertEqual(gateway.review_calls, 2)
        self.assertIn("specified outcome", client.queries[1])
        self.assertNotIn("consistency_repair", gateway.planning_payloads[0])
        repair = gateway.planning_payloads[1]["consistency_repair"]
        self.assertEqual(
            repair["original_question"],
            "How does the exposure affect the specified outcome?",
        )
        self.assertEqual(repair["missing_concepts"], ["specified outcome"])
        self.assertEqual(
            repair["instruction"],
            "rewrite_primary_plan_preserving_original_exposure_outcome_and_qualifiers",
        )
        self.assertTrue(generated.retrieval_rounds[1].repair_feedback_applied)
        self.assertEqual(
            len(generated.retrieval_rounds[1].repair_directive_sha256 or ""),
            64,
        )

    async def test_consistency_repair_can_be_disabled_for_component_ablation(self) -> None:
        client = _KnowledgeClient()
        gateway = _RepairGateway()
        generated = await generate_reviewed_discovery_plan(
            DiscoveryPlanGenerationRequest(
                search=KnowledgeSearchRequest(
                    question="How does the exposure affect the specified outcome?",
                    top_k=2,
                    min_unique_documents=2,
                ),
                context=DiscoveryResearcherContext(
                    goal="Preserve the specified outcome and build a falsifiable plan."
                ),
            ),
            knowledge_client=client,
            gateway=gateway,
            max_consistency_repairs=0,
        )

        self.assertEqual(generated.repair_count, 0)
        self.assertFalse(generated.final_consistency_passed)
        self.assertEqual(len(generated.retrieval_rounds), 1)
        self.assertEqual(gateway.planning_calls, 1)
        self.assertEqual(gateway.review_calls, 1)
        self.assertEqual(client.queries, ["How does the exposure affect the specified outcome?"])


class DiscoveryPlannerApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        base = Path(os.getenv("HYPOWEAVER_TEST_TMP", Path.cwd() / ".test-tmp"))
        self.root = base / uuid4().hex
        self.root.mkdir(parents=True, exist_ok=False)
        self.engine = WorkflowEngine(RunRepository(self.root / "runs.db"))
        self.transport = httpx.ASGITransport(
            app=api_module.app,
            client=("127.0.0.1", 12345),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    async def test_generate_review_and_launch_reach_h1(self) -> None:
        bundle = _bundle()
        generation = DiscoveryPlanGeneration(
            evidence_bundle=bundle,
            plan=_plan(),
            model_usage={"total_attempts": 1},
        )
        headers = {"X-Hypoweaver-Token": "workflow-secret"}
        environment = {
            "HYPOWEAVER_API_TOKEN": "workflow-secret",
            "HYPOWEAVER_ACTOR": "h0-reviewer",
            "KNOWLEDGE_SERVICE_URL": "http://knowledge.test",
        }
        with (
            patch.object(api_module, "engine", self.engine),
            patch.object(
                api_module,
                "generate_reviewed_discovery_plan",
                new=AsyncMock(return_value=generation),
            ),
            patch.dict(os.environ, environment, clear=True),
        ):
            async with httpx.AsyncClient(
                transport=self.transport,
                base_url="http://testserver",
            ) as client:
                generated = await client.post(
                    "/api/v1/discovery/plans/generate",
                    headers=headers,
                    json={
                        "search": {
                            "question": bundle.question,
                            "top_k": 12,
                            "max_graph_edges": 20,
                        },
                        "context": {"goal": "Build one falsifiable candidate."},
                    },
                )
                self.assertEqual(generated.status_code, 200, generated.text)
                review_payload = {
                    "evidence_bundle": generated.json()["evidence_bundle"],
                    "plan": generated.json()["plan"],
                    "consistency_review": _pass_review().model_dump(mode="json"),
                    "execution_readiness": generated.json()["execution_readiness"],
                    "review_note": (
                        "I checked every cited chunk and accept this corpus-bounded draft."
                    ),
                }
                reviewed = await client.post(
                    "/api/v1/discovery/plans/review",
                    headers=headers,
                    json=review_payload,
                )
                self.assertEqual(reviewed.status_code, 200, reviewed.text)
                launched = await client.post(
                    "/api/v1/discovery/plans/launch",
                    headers=headers,
                    json={
                        **review_payload,
                        "approve_h0": True,
                        "approval_reason": (
                            "The source locations, gap boundary, and falsifiable form were reviewed."
                        ),
                        "mode": "fixture",
                    },
                )

        self.assertEqual(launched.status_code, 201, launched.text)
        body = launched.json()
        self.assertEqual(body["run"]["current_gate"], "H1")
        self.assertEqual(body["run"]["status"], "waiting_human")
        self.assertFalse(body["case_submission"]["intake_readiness"]["can_execute"])


if __name__ == "__main__":
    unittest.main()
