"""Run a complete fixture workflow through H1-H4 using the public HTTP API."""

from __future__ import annotations

import argparse
import os
from typing import Any
from uuid import uuid4

import httpx


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("HYPOWEAVER_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--token",
        default=os.getenv("HYPOWEAVER_API_TOKEN", ""),
        help="Value sent as X-Hypoweaver-Token. Required for remote mutations.",
    )
    return parser.parse_args()


def gate_payload(run: dict[str, Any]) -> dict[str, Any]:
    gate = run.get("current_gate")
    common = {
        "expected_run_version": run["version"],
        "idempotency_key": str(uuid4()),
        "comment": "Fixture API example",
    }
    if gate in {"H1", "H2", "H4"}:
        return {**common, "action": "approve"}
    if gate == "H3":
        return {
            **common,
            "action": "generate_plan_only",
            "claims": [
                {
                    "claim_id": claim["claim_id"],
                    "decision": "hold",
                    "reason": "Fixture evidence cannot support an empirical claim.",
                }
                for claim in run.get("claims", [])
            ],
        }
    raise RuntimeError(f"unsupported gate: {gate}")


def main() -> None:
    args = arguments()
    headers = {"Accept": "application/json"}
    if args.token:
        headers["X-Hypoweaver-Token"] = args.token

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        headers=headers,
        timeout=60,
    ) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()
        print("health:", health.json())

        response = client.post(
            "/api/v1/runs",
            json={
                "preset_case_id": "green-finance-did",
                "mode": "fixture",
                "model_provider": "fixture",
                "execution_mode": "fixture",
            },
        )
        response.raise_for_status()
        run = response.json()
        print("created:", run["id"], run["status"], run.get("current_gate"))

        while run["status"] == "waiting_human":
            gate = run["current_gate"]
            response = client.post(
                f"/api/v1/runs/{run['id']}/gates/{gate}",
                json=gate_payload(run),
            )
            response.raise_for_status()
            run = response.json()
            print("after", gate, ":", run["status"], run.get("current_gate"))

        if run["status"] != "completed":
            raise RuntimeError(
                f"workflow stopped at status={run['status']}: {run.get('last_error')}"
            )
        print(
            "completed:",
            {
                "run_id": run["id"],
                "execution_status": run["execution_status"],
                "scientific_status": run["scientific_status"],
                "plan_only": run["plan_only"],
            },
        )


if __name__ == "__main__":
    main()
