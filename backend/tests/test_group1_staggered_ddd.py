from __future__ import annotations

import hashlib
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from hypoweaver.case_import import DatasetRegistry
from hypoweaver.group1_staggered_ddd import (
    GROUP1_PRIMARY_IMPLEMENTATION_ID,
    GROUP1_REPRODUCTION_IMPLEMENTATION_ID,
    Group1StaggeredDDDEstimationError,
    estimate_group1_staggered_ddd,
    reproduce_group1_staggered_ddd,
)
from hypoweaver.models import (
    AnalysisPlan,
    ContractBudget,
    DatasetRef,
    FormalResearchContract,
    ModelSpec,
    PlannedStep,
    utc_now,
)
from hypoweaver.reproducer import ResearchReproducer, compare_panel_reproduction
from hypoweaver.research_engine import PanelResearchEngine
from hypoweaver.seal import canonical_sha256
from hypoweaver.test_dag import (
    GROUP1_STAGGERED_DDD_REGISTRY_VERSION,
    THREAT_GROUP1_EVENT_STUDY,
    THREAT_GROUP1_INDEPENDENT_REPLICATION,
    THREAT_GROUP1_SIGN_SWITCH,
    THREAT_GROUP1_SUPPORT,
    validate_group1_staggered_ddd_execution_plan,
)


class Group1StaggeredDDDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[1]
            / "var"
            / "test-temp"
            / f"group1-{uuid4()}"
        )
        self.root.mkdir(parents=True)
        self.csv_path = self.root / "paired_stacks.csv"
        _write_panel(self.csv_path)
        self.models = (_model("greenwashing_gap"), _model("firm_emission_intensity"))
        self.plan = _plan(self.models)
        digest = hashlib.sha256(self.csv_path.read_bytes()).hexdigest()
        self.dataset_ref = DatasetRef(
            dataset_id=f"group1-{digest[:16]}",
            filename=self.csv_path.name,
            sha256=digest,
            size_bytes=self.csv_path.stat().st_size,
        )
        self.registry = DatasetRegistry(self.root / "datasets.json")
        self.registry.register(self.dataset_ref, self.csv_path)
        self.contract = FormalResearchContract(
            contract_id="contract-group1-test",
            case_id="case-group1-test",
            approved_at=utc_now(),
            approved_by="test",
            decision_record_id="decision-test",
            research_package_hash="a" * 64,
            data_hashes=[digest],
            dataset_refs=[self.dataset_ref],
            approved_plan_hash=canonical_sha256(self.plan.model_dump(mode="json")),
            approved_plan=self.plan,
            prohibited_deviations=["no outcome-driven redesign"],
            allowed_technical_repairs=["path repair"],
            unresolved_risks=[],
            budget=ContractBudget(
                max_executions=8,
                max_wall_time_seconds=300,
                max_end_to_end_wall_time_seconds=600,
            ),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_primary_and_independent_estimators_match(self) -> None:
        primary = estimate_group1_staggered_ddd(self.csv_path, self.models[0])
        replica = reproduce_group1_staggered_ddd(self.csv_path, self.models[0])

        self.assertEqual(primary["implementation_id"], GROUP1_PRIMARY_IMPLEMENTATION_ID)
        self.assertEqual(
            replica["implementation_id"], GROUP1_REPRODUCTION_IMPLEMENTATION_ID
        )
        left = {item["term"]: item for item in primary["estimates"]}
        right = {item["term"]: item for item in replica["estimates"]}
        self.assertEqual(set(left), set(right))
        for term in left:
            self.assertAlmostEqual(left[term]["coefficient"], right[term]["coefficient"], places=8)
            self.assertAlmostEqual(left[term]["standard_error"], right[term]["standard_error"], places=8)
        self.assertTrue(primary["diagnostics"]["capacity_timing_verified"])
        self.assertTrue(primary["diagnostics"]["scientific_release_ready"])

    def test_capacity_timing_leak_is_rejected(self) -> None:
        frame = pd.read_csv(self.csv_path)
        frame.loc[0, "capacity_source_end_year"] = 2017
        frame.to_csv(self.csv_path, index=False)

        with self.assertRaisesRegex(
            Group1StaggeredDDDEstimationError,
            "strictly before",
        ):
            estimate_group1_staggered_ddd(self.csv_path, self.models[0])

    def test_full_primary_reproduction_contract_matches(self) -> None:
        baselines = validate_group1_staggered_ddd_execution_plan(self.plan)
        self.assertEqual([item.outcome for item in baselines], ["greenwashing_gap", "firm_emission_intensity"])

        primary = PanelResearchEngine(self.registry).execute(self.contract)
        replica = ResearchReproducer(self.registry).execute(self.contract)
        audit = compare_panel_reproduction(primary, replica)

        self.assertEqual(primary.execution_status, "succeeded")
        self.assertEqual(replica.execution_status, "succeeded")
        self.assertEqual(audit.status, "matched", audit.differences)
        self.assertEqual(audit.independence_scope, "estimator_only")
        self.assertEqual(
            set(audit.covered_plan_step_ids),
            {
                "model-group1-greenwashing_gap",
                "model-group1-firm_emission_intensity",
                "check-group1-event-study",
                "check-group1-sign-switch",
            },
        )


def _design() -> dict[str, object]:
    return {
        "entity_field": "firm_id",
        "time_field": "year",
        "stack_cohort_field": "stack_cohort_year",
        "assigned_cohort_field": "treatment_cohort_year",
        "moderator_field": "prepolicy_digital_fintech_capacity",
        "moderator_source_end_field": "capacity_source_end_year",
        "capacity_source_count_field": "capacity_year_count",
        "paired_outcomes": ["greenwashing_gap", "firm_emission_intensity"],
        "treated_field": "treated",
        "exposure_field": "gfripz_exposure",
        "fixed_effects": ["stack_entity_id", "stack_time_id"],
        "cluster_field": "firm_id",
        "transition_year_mode": "exclude",
        "event_time_min": -3,
        "event_time_max": 3,
        "event_reference": -1,
        "policy_term": "policy_exposure",
        "capacity_time_term": "post_x_capacity",
        "policy_capacity_term": "policy_x_capacity",
        "boundary_precision_field": "assignment_boundary_precision",
        "engineering_minimum_treated_entities": 1,
        "scientific_minimum_treated_entities": 2,
    }


def _model(outcome: str) -> ModelSpec:
    return ModelSpec(
        step_id=f"model-group1-{outcome}",
        name=outcome,
        rationale="frozen paired test model",
        estimator="stacked-cohort-continuous-capacity-ddd",
        outcome=outcome,
        treatments_or_exposures=["policy_exposure", "policy_x_capacity"],
        controls=[],
        fixed_effects=["stack_entity_id", "stack_time_id"],
        standard_error_strategy="firm_clustered_debiased",
        parameters={"staggered_ddd_design": _design()},
    )


def _plan(models: tuple[ModelSpec, ModelSpec]) -> AnalysisPlan:
    claims = ["claim-H1"]
    return AnalysisPlan(
        plan_id="plan-group1-test",
        plan_version=1,
        method_family="policy_causal",
        design_only=False,
        estimands=[],
        sample_rules=[],
        variable_construction=[],
        baseline_models=list(models),
        diagnostics=[
            PlannedStep(
                step_id="check-group1-support",
                name="support",
                rationale="support",
                threat_id=THREAT_GROUP1_SUPPORT,
                target_claim_ids=claims,
                test_role="diagnostic",
                required_for_admission=True,
            )
        ],
        robustness_tests=[
            PlannedStep(
                step_id="check-group1-independent-replication",
                name="replication",
                rationale="replication",
                threat_id=THREAT_GROUP1_INDEPENDENT_REPLICATION,
                target_claim_ids=claims,
                test_role="replication",
                required_for_admission=True,
            )
        ],
        falsification_tests=[
            PlannedStep(
                step_id="check-group1-event-study",
                name="event",
                rationale="event",
                threat_id=THREAT_GROUP1_EVENT_STUDY,
                target_claim_ids=claims,
                test_role="falsification",
                required_for_admission=True,
            ),
            PlannedStep(
                step_id="check-group1-sign-switch",
                name="sign",
                rationale="sign",
                threat_id=THREAT_GROUP1_SIGN_SWITCH,
                target_claim_ids=claims,
                test_role="falsification",
                required_for_admission=True,
            ),
        ],
        mechanism_tests=[],
        heterogeneity_tests=[],
        identification_assumptions=[],
        alternative_explanations=[],
        failure_conditions=[],
        stop_conditions=[],
        required_data_fields=[],
        unsupported_requested_analyses=[],
        check_registry_version=GROUP1_STAGGERED_DDD_REGISTRY_VERSION,
    )


def _write_panel(path: Path) -> None:
    rows: list[dict[str, object]] = []
    capacities = np.asarray([80, 100, 120, 140, 160, 180, 200, 220], dtype=float)
    capacity_z = (capacities - capacities.mean()) / capacities.std(ddof=1)
    for firm_index in range(8):
        treated = firm_index < 3
        firm = f"F{firm_index:02d}"
        for year in range(2014, 2021):
            event_time = year - 2017
            exposure = int(treated and year > 2017)
            noise = ((firm_index * 17 + year * 11) % 19 - 9) * 0.01
            low_to_high_effect = 0.6 - 0.9 * capacity_z[firm_index]
            rows.append(
                {
                    "stack_cohort_year": 2017,
                    "stack_entity_id": f"2017:{firm}",
                    "stack_time_id": f"2017:{year}",
                    "firm_id": firm,
                    "year": year,
                    "treated": int(treated),
                    "gfripz_exposure": exposure,
                    "treatment_cohort_year": 2017 if treated else np.nan,
                    "prepolicy_digital_fintech_capacity": capacities[firm_index],
                    "capacity_year_count": 6,
                    "capacity_source_end_year": 2016,
                    "assignment_boundary_precision": "exact_prefecture" if treated else "control",
                    "greenwashing_gap": firm_index * 0.2 + event_time * 0.05 + exposure * low_to_high_effect + noise,
                    "firm_emission_intensity": firm_index * 0.1 + event_time * 0.03 + exposure * (0.4 - 0.7 * capacity_z[firm_index]) - noise,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)
