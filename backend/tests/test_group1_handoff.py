from __future__ import annotations

import hashlib
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx

import hypoweaver.api as api_module
from hypoweaver.engine import WorkflowEngine, WorkflowTransitionError
from hypoweaver.group1_handoff import (
    Group1HandoffError,
    import_group1_handoff,
    inspect_verified_group1_bundle,
    verified_group1_bundle_request,
)
from hypoweaver.models import CreateRunRequest, GateDecisionRequest
from hypoweaver.repository import RunRepository


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_test_root() -> Path:
    base = Path(os.getenv("HYPOWEAVER_TEST_TMP", Path.cwd() / ".test-tmp"))
    root = base / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def build_group1_package(root: Path) -> Path:
    handoff_dir = root / "I_group1_handoff"
    hypothesis_path = root / "H_discovery_release" / "hypothesis_cards" / "hypothesis_001.json"
    gap_path = root / "H_discovery_release" / "gap_cards" / "gap_001.json"
    handoff_path = handoff_dir / "handoff.json"
    readme_path = handoff_dir / "README_CN.md"

    handoff = {
        "schema_version": "1.0.0",
        "handoff_id": "group1-handoff:test-package",
        "generated_at": "2026-08-09T18:30:00+08:00",
        "status": "ready_for_group2_with_conditions",
        "final_hypothesis": {
            "hypothesis_id": "hypothesis:test",
            "gap_id": "research_gap:test",
            "title": "Predetermined capacity separates policy responses",
        },
        "scientific_constraints": [
            "Measure capacity before treatment.",
            "Use direct firm emissions.",
        ],
        "group2_scope": {
            "must_not_change_without_return_to_group1": [
                "Keep the conditional sign-switch hypothesis."
            ]
        },
        "unresolved_conditions": ["Recheck publication status before submission."],
    }
    hypothesis = {
        "hypothesis_id": "hypothesis:test",
        "hypothesis_statement": "Policy responses switch sign with predetermined capacity.",
        "falsifiable_form": "No sign switch falsifies the hypothesis.",
        "title": "Predetermined capacity separates policy responses",
        "graph_snapshot_id": "graph@test",
        "novelty_check_ref": "novelty:test",
        "boundary_conditions": ["Use one cohort definition for both outcomes."],
        "predictions": [
            {
                "prediction_id": "prediction:greenwashing_sign_switch",
                "statement": "Greenwashing falls only at high baseline capacity.",
                "observable_pattern": "The marginal effect crosses zero.",
                "would_falsify": "The effect has one sign over the full support.",
            }
        ],
        "variables": {
            "dependent": [
                {
                    "name": "ESG greenwashing gap",
                    "definition": "Substantive minus disclosed performance.",
                    "graph_node_id": "variable:greenwashing",
                },
                {
                    "name": "Firm emission intensity",
                    "definition": "Firm emissions divided by a frozen denominator.",
                    "graph_node_id": "variable:emissions",
                },
            ],
            "independent": [
                {
                    "name": "GFRIPZ exposure",
                    "definition": "Cohort-specific policy exposure.",
                    "graph_node_id": "variable:policy",
                }
            ],
            "mediators": [],
            "moderators": [
                {
                    "name": "Pre-policy regional digital/fintech capacity",
                    "definition": "Capacity frozen before treatment.",
                    "graph_node_id": "variable:capacity",
                }
            ],
            "controls": [],
        },
        "handoff": {
            "required_inputs": ["Firm-year policy exposure crosswalk"],
            "validation_acceptance_criteria": ["All cohorts pass pre-trend diagnostics."],
            "evidence_bundle_refs": ["ev:test"],
        },
        "feasibility": {
            "blocking_items": ["Acquire a linked firm-emissions panel."]
        },
        "recommended_design": {
            "baseline_specification": "Cohort-robust staggered DID with a baseline-capacity DDD.",
            "unit_of_analysis": "firm-year linked to region-year policy treatment",
        },
        "evidence_balance": {"supporting_finding_ids": ["finding:test"]},
    }
    gap = {
        "gap_id": "research_gap:test",
        "candidate_research_questions": [
            "Does predetermined capacity reverse the policy effect on greenwashing?"
        ],
    }
    _write_json(handoff_path, handoff)
    readme_path.write_text("test handoff", encoding="utf-8")
    _write_json(hypothesis_path, hypothesis)
    _write_json(gap_path, gap)
    manifest = {
        "schema_version": "1.0.0",
        "handoff_id": handoff["handoff_id"],
        "artifacts": [
            {"name": "handoff", "path": "handoff.json", "sha256": _digest(handoff_path)},
            {"name": "readme_cn", "path": "README_CN.md", "sha256": _digest(readme_path)},
        ],
        "source_artifacts": [
            {
                "name": "hypothesis_card",
                "path": "H_discovery_release/hypothesis_cards/hypothesis_001.json",
                "sha256": _digest(hypothesis_path),
            },
            {
                "name": "gap_card",
                "path": "H_discovery_release/gap_cards/gap_001.json",
                "sha256": _digest(gap_path),
            },
        ],
    }
    _write_json(handoff_dir / "manifest.json", manifest)
    return root


def build_verified_execution_bundle(root: Path) -> dict[str, Path]:
    panel = root / "execution" / "group1_paired_stacked_panel.csv"
    panel.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "stack_cohort_year",
        "stack_entity_id",
        "stack_time_id",
        "firm_id",
        "year",
        "treated",
        "gfripz_exposure",
        "treatment_cohort_year",
        "region_id",
        "assignment_boundary_precision",
        "prepolicy_digital_fintech_capacity",
        "capacity_year_count",
        "capacity_source_end_year",
        "greenwashing_gap",
        "firm_emission_intensity",
        "firm_size",
        "leverage",
        "return_on_assets",
        "sales_growth",
        "cash_ratio",
        "state_owned",
    ]
    panel.write_text(
        ",".join(fields) + "\n" + ",".join("1" for _ in fields) + "\n",
        encoding="utf-8",
    )
    source_config = root / "execution" / "group1_execution_sources.json"
    _write_json(source_config, {"schema_version": "test-source-config-v1"})
    manifest = panel.with_suffix(".manifest.json")
    _write_json(
        manifest,
        {
            "schema_version": "group1-stacked-panel-manifest-v1",
            "source_config_sha256": _digest(source_config),
            "scientific_release_blockers": ["Keep scientific release conditional."],
            "output": {
                "filename": panel.name,
                "sha256": _digest(panel),
                "size_bytes": panel.stat().st_size,
                "rows": 1,
                "columns": len(fields),
                "stack_firm_year_key_unique": True,
                "paired_outcome_complete": True,
            },
        },
    )
    receipt = root / "execution" / "acceptance-latest.json"
    _write_json(
        receipt,
        {
            "schema_version": "group1-group2-acceptance-receipt-v1",
            "workflow_run_id": "accepted-test-run",
            "status": "completed",
            "execution_status": "succeeded",
            "scientific_status": "limited",
            "data_hashes": [_digest(panel)],
            "reproduction": {
                "status": "matched",
                "independence_scope": "estimator_only",
            },
            "sealed_output": {"seal_sha256": "a" * 64},
        },
    )
    return {
        "panel": panel,
        "manifest": manifest,
        "source_config": source_config,
        "receipt": receipt,
    }


def verified_bundle_environment(handoff: Path, assets: dict[str, Path]) -> dict[str, str]:
    return {
        "HYPOWEAVER_GROUP1_HANDOFF_PATH": str(handoff),
        "HYPOWEAVER_GROUP1_EXECUTION_PANEL_PATH": str(assets["panel"]),
        "HYPOWEAVER_GROUP1_EXECUTION_MANIFEST_PATH": str(assets["manifest"]),
        "HYPOWEAVER_GROUP1_SOURCE_CONFIG_PATH": str(assets["source_config"]),
        "HYPOWEAVER_GROUP1_ACCEPTANCE_RECEIPT_PATH": str(assets["receipt"]),
    }


class Group1HandoffBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = _local_test_root()
        self.root = build_group1_package(self.test_root / "pilot")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_verified_package_maps_to_conditional_group2_design_handoff(self) -> None:
        result = import_group1_handoff(self.root)

        self.assertEqual(result.integrity.status, "passed")
        self.assertEqual(result.integrity.verified_artifact_count, 4)
        self.assertEqual(result.case_submission.case_id, "group1-handoff:test-package")
        self.assertEqual(len(result.case_submission.hypotheses), 2)
        self.assertEqual(
            {item.name for item in result.case_submission.variables if item.role == "outcome"},
            {"greenwashing_gap", "firm_emission_intensity"},
        )
        self.assertEqual(result.feasibility.status, "conditional")
        self.assertTrue(result.feasibility.can_approve_h1)
        self.assertFalse(result.feasibility.can_execute)
        self.assertIn("staggered DID", " ".join(result.feasibility.method_requirements))
        self.assertEqual(
            result.group2_feasibility_package.go_no_go_decision,
            "conditional_go_for_design",
        )
        self.assertEqual(len(result.group2_feasibility_package.scientific_ten), 10)
        self.assertEqual(
            result.case_submission.group2_feasibility_package.package_id,
            result.group2_feasibility_package.package_id,
        )
        self.assertEqual(
            result.case_submission.upstream_provenance.manifest_sha256,
            result.integrity.manifest_sha256,
        )
        self.assertEqual(result.case_submission.upstream_provenance.gap_id, "research_gap:test")
        self.assertEqual(result.case_submission.upstream_provenance.evidence_refs, ["ev:test", "finding:test"])

    def test_hash_tampering_is_rejected(self) -> None:
        hypothesis_path = self.root / "H_discovery_release" / "hypothesis_cards" / "hypothesis_001.json"
        hypothesis_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(Group1HandoffError, "hash mismatch"):
            import_group1_handoff(self.root)

    def test_verified_local_bundle_is_bound_to_the_acceptance_receipt(self) -> None:
        assets = build_verified_execution_bundle(self.test_root)
        with patch.dict(
            os.environ,
            verified_bundle_environment(self.root, assets),
            clear=False,
        ):
            status = inspect_verified_group1_bundle()
            request = verified_group1_bundle_request()

        self.assertEqual(status.status, "ready")
        self.assertEqual(status.acceptance_run_id, "accepted-test-run")
        self.assertEqual(status.reproduction_status, "matched")
        self.assertEqual(status.panel_rows, 1)
        self.assertEqual(status.panel_columns, 21)
        self.assertEqual(request.research_model_provider, "code_owned")
        self.assertEqual(request.execution_panel_path, str(assets["panel"]))

    def test_verified_local_bundle_rejects_a_receipt_for_another_panel(self) -> None:
        assets = build_verified_execution_bundle(self.test_root)
        receipt = json.loads(assets["receipt"].read_text(encoding="utf-8"))
        receipt["data_hashes"] = ["0" * 64]
        _write_json(assets["receipt"], receipt)
        with patch.dict(
            os.environ,
            verified_bundle_environment(self.root, assets),
            clear=False,
        ):
            status = inspect_verified_group1_bundle()

        self.assertEqual(status.status, "invalid")
        self.assertIn("not bound", status.message)


class Group1HandoffRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.test_root = _local_test_root()
        self.root = build_group1_package(self.test_root / "pilot")
        self.repository = RunRepository(self.test_root / "runs.db")
        self.engine = WorkflowEngine(self.repository)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    async def test_group1_handoff_can_continue_from_h1_to_h2_design(self) -> None:
        bridge = import_group1_handoff(self.root)
        run = await self.engine.create_run(
            CreateRunRequest(mode="fixture", case=bridge.case_submission)
        )

        self.assertEqual((run.status, run.current_gate), ("waiting_human", "H1"))
        self.assertEqual(run.model_provider, "fixture")
        self.assertEqual(run.execution_mode, "fixture")
        self.assertEqual(run.case_submission.upstream_provenance.package_id, bridge.integrity.handoff_id)
        self.assertTrue(
            any("上游可行性阻断" in warning for warning in run.artifacts["research_package"]["payload"]["missing_required_information"])
        )

        run = await self.engine.decide_gate(
            run.id,
            "H1",
            GateDecisionRequest(action="approve", expected_run_version=run.version),
        )

        self.assertEqual((run.status, run.current_gate), ("waiting_human", "H2"))
        self.assertIn("design_arena", run.artifacts)
        self.assertIn("analysis_plan", run.artifacts)
        self.assertIn("data_profile", run.artifacts)
        self.assertIn("method_route", run.artifacts)
        route = run.artifacts["method_route"]["payload"]
        plan = run.artifacts["analysis_plan"]["payload"]
        self.assertEqual(route["primary_route"], "policy_causal")
        self.assertEqual(route["research_goal"], "causal")
        self.assertEqual(plan["method_family"], "policy_causal")
        self.assertTrue(plan["design_only"])
        self.assertEqual(
            plan["check_registry_version"],
            "group1-staggered-ddd-design-v1",
        )
        self.assertEqual(
            {model["outcome"] for model in plan["baseline_models"]},
            {"greenwashing_gap", "firm_emission_intensity"},
        )
        self.assertTrue(
            all(
                "prepolicy_digital_fintech_capacity"
                in model["treatments_or_exposures"]
                for model in plan["baseline_models"]
            )
        )
        self.assertTrue(
            all(model["not_executable_reason"] for model in plan["baseline_models"])
        )
        self.assertIn("treatment_cohort_year", plan["required_data_fields"])

    async def test_group1_handoff_fails_closed_before_statistical_execution(self) -> None:
        bridge = import_group1_handoff(self.root)
        run = await self.engine.create_run(
            CreateRunRequest(mode="fixture", case=bridge.case_submission)
        )
        run = await self.engine.decide_gate(
            run.id,
            "H1",
            GateDecisionRequest(action="approve", expected_run_version=run.version),
        )

        with self.assertRaisesRegex(
            WorkflowTransitionError,
            "use generate_plan_only",
        ):
            await self.engine.decide_gate(
                run.id,
                "H2",
                GateDecisionRequest(
                    action="approve",
                    expected_run_version=run.version,
                ),
            )

        unchanged = self.engine.get_run(run.id)
        self.assertEqual((unchanged.status, unchanged.current_gate), ("waiting_human", "H2"))
        self.assertNotIn("formal_research_contract", unchanged.artifacts)
        self.assertEqual(unchanged.execution_status, "not_started")

    async def test_group1_handoff_completes_plan_only_from_h1_through_h4(self) -> None:
        bridge = import_group1_handoff(self.root)
        run = await self.engine.create_run(
            CreateRunRequest(mode="fixture", case=bridge.case_submission)
        )
        run = await self.engine.decide_gate(
            run.id,
            "H1",
            GateDecisionRequest(
                action="approve",
                idempotency_key="group1-e2e-h1",
                expected_run_version=run.version,
            ),
        )
        run = await self.engine.decide_gate(
            run.id,
            "H2",
            GateDecisionRequest(
                action="generate_plan_only",
                idempotency_key="group1-e2e-h2",
                expected_run_version=run.version,
            ),
        )

        self.assertEqual((run.status, run.current_gate), ("waiting_human", "H3"))
        self.assertTrue(run.plan_only)
        self.assertEqual(run.execution_status, "fixture_only")
        self.assertEqual(run.scientific_status, "not_evaluated")
        self.assertIn("formal_research_contract", run.artifacts)
        self.assertIn("research_run", run.artifacts)
        self.assertIn("claim_gate_report", run.artifacts)

        run = await self.engine.decide_gate(
            run.id,
            "H3",
            GateDecisionRequest(
                action="generate_plan_only",
                idempotency_key="group1-e2e-h3",
                expected_run_version=run.version,
                claims=[
                    {"claim_id": claim.claim_id, "decision": "hold"}
                    for claim in run.claims
                ],
            ),
        )
        self.assertEqual((run.status, run.current_gate), ("waiting_human", "H4"))
        self.assertIn("manuscript_package", run.artifacts)

        run = await self.engine.decide_gate(
            run.id,
            "H4",
            GateDecisionRequest(
                action="approve",
                idempotency_key="group1-e2e-h4",
                expected_run_version=run.version,
            ),
        )

        self.assertEqual(run.status, "completed")
        self.assertIsNone(run.current_gate)
        self.assertEqual(run.current_node_id, "complete")
        self.assertTrue(run.plan_only)
        self.assertEqual(run.execution_status, "fixture_only")
        self.assertEqual(run.scientific_status, "not_evaluated")
        self.assertIn("approved_claim_ledger", run.artifacts)
        self.assertIn("sealed_output", run.artifacts)

    async def test_local_api_launches_the_verified_group1_run(self) -> None:
        transport = httpx.ASGITransport(app=api_module.app, client=("127.0.0.1", 12345))
        with patch.object(api_module, "engine", self.engine):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/v1/group1-handoffs/local/runs",
                    json={"path": str(self.root), "mode": "fixture"},
                )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["bridge"]["integrity"]["status"], "passed")
        self.assertEqual(payload["run"]["current_gate"], "H1")
        self.assertEqual(payload["run"]["mode"], "fixture")
        self.assertEqual(payload["run"]["case_submission"]["intake_readiness"]["status"], "conditional")
        self.assertEqual(
            len(payload["run"]["case_submission"]["group2_feasibility_package"]["scientific_ten"]),
            10,
        )

    async def test_local_api_launches_the_recorded_verified_execution_bundle(self) -> None:
        assets = build_verified_execution_bundle(self.test_root)
        transport = httpx.ASGITransport(app=api_module.app, client=("127.0.0.1", 12345))
        with (
            patch.dict(
                os.environ,
                verified_bundle_environment(self.root, assets),
                clear=False,
            ),
            patch.object(api_module, "engine", self.engine),
        ):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                status_response = await client.get(
                    "/api/v1/group1-handoffs/local/verified-bundle"
                )
                launch_response = await client.post(
                    "/api/v1/group1-handoffs/local/verified-bundle/runs"
                )

        self.assertEqual(status_response.status_code, 200, status_response.text)
        self.assertEqual(status_response.json()["status"], "ready")
        self.assertEqual(launch_response.status_code, 201, launch_response.text)
        run = launch_response.json()["run"]
        self.assertEqual(run["model_provider"], "code_owned")
        self.assertEqual(run["execution_mode"], "external")
        self.assertTrue(run["case_submission"]["intake_readiness"]["can_execute"])
        self.assertIn(
            "frozen core sign-switch execution",
            run["case_submission"]["group2_feasibility_package"]["decision_rationale"],
        )


if __name__ == "__main__":
    unittest.main()
