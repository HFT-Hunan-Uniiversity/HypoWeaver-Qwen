from __future__ import annotations

import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

import hypoweaver.api as api_module
if __package__:
    from .test_discovery_pipeline import _online_build_request
else:
    from test_discovery_pipeline import _online_build_request
from hypoweaver.discovery_handoff import discovery_release_to_case
from hypoweaver.discovery_pipeline import build_discovery_release_preview
from hypoweaver.engine import WorkflowEngine
from hypoweaver.repository import RunRepository


def _test_root() -> Path:
    root = Path(os.getenv("HYPOWEAVER_TEST_TMP", Path.cwd() / ".test-tmp")) / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


class DiscoveryHandoffTests(unittest.TestCase):
    def test_h0_approval_creates_plan_only_h1_case(self) -> None:
        release = build_discovery_release_preview(
            _online_build_request(),
            reviewer="graph-reviewer",
        )
        hypothesis_id = release.hypothesis_cards[0]["hypothesis_id"]
        case = discovery_release_to_case(
            release,
            hypothesis_id=hypothesis_id,
            approver="h0-reviewer",
            approval_reason="The cited evidence and falsifiable form are adequate for H1 design review.",
        )

        self.assertEqual(case.hypotheses[0].hypothesis_id, hypothesis_id)
        self.assertTrue(case.intake_readiness.can_approve_h1)
        self.assertFalse(case.intake_readiness.can_execute)
        self.assertEqual(case.upstream_provenance.status, "h0_approved_for_h1")
        self.assertEqual(
            case.upstream_provenance.graph_snapshot_id,
            release.final_research_graph["snapshot_id"],
        )
        self.assertTrue(any(item.role == "outcome" for item in case.variables))


class DiscoveryLaunchApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.root = _test_root()
        self.engine = WorkflowEngine(RunRepository(self.root / "runs.db"))

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    async def test_approved_hypothesis_launches_at_existing_h1_gate(self) -> None:
        build = _online_build_request()
        payload = {
            "build": build.model_dump(mode="json"),
            "hypothesis_id": "hypothesis:digital_mechanism",
            "approve_h0": True,
            "approval_reason": (
                "The evidence references and falsifiable prediction are sufficient "
                "to enter H1 design review."
            ),
            "mode": "fixture",
        }
        transport = httpx.ASGITransport(
            app=api_module.app,
            client=("127.0.0.1", 12345),
        )
        with (
            patch.object(api_module, "engine", self.engine),
            patch.dict(
                os.environ,
                {
                    "HYPOWEAVER_API_TOKEN": "workflow-secret",
                    "HYPOWEAVER_ACTOR": "h0-reviewer",
                },
                clear=True,
            ),
        ):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                response = await client.post(
                    "/api/v1/discovery/releases/launch",
                    headers={"X-Hypoweaver-Token": "workflow-secret"},
                    json=payload,
                )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["run"]["current_gate"], "H1")
        self.assertEqual(body["run"]["status"], "waiting_human")
        self.assertEqual(
            body["case_submission"]["upstream_provenance"]["status"],
            "h0_approved_for_h1",
        )
        self.assertFalse(
            body["case_submission"]["intake_readiness"]["can_execute"]
        )


if __name__ == "__main__":
    unittest.main()
