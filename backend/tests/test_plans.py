import asyncio
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.llm.service import get_llm
from hypoweaver.literature.service import save_cards
from test_candidates import CandidateLLM


def plan_payload():
    return {
        "method_family": "policy_causal",
        "variables": [
            {"role": r, "name": n, "definition": d, "uncertain": False}
            for r, n, d in [
                ("outcome", "patents", "绿色发明专利"),
                ("treatment", "exposure", "行业同群暴露，并非真实处理分配"),
                ("unit", "firm", "企业代码"),
                ("time", "year", "年份"),
            ]
        ],
        "robustness": [
            {"id": str(i), "change": k, "kind": k, "args": a}
            for i, (k, a) in enumerate(
                [
                    ("drop_controls", {}),
                    ("exclude_years", {"years": [2021]}),
                    ("monotone_only", {}),
                    ("alt_outcome", {"outcome": "green_patent_all"}),
                ]
            )
        ],
        "claims_planned": [{"id": "main", "text": "同群暴露与创新存在关联", "type": "main"}],
        "boundary_notes": "最高报告关联，不能解释为因果",
        "treatment_is_real_assignment": True,
    }


class PlanLLM(CandidateLLM):
    async def generate(self, name, payload, schema, project_id=None):
        if name == "draft_plan":
            return schema.model_validate(plan_payload())
        return await super().generate(name, payload, schema, project_id)


def seed_selected(client, app, case=None):
    p = client.post("/api/projects", json={"title": "碳市场方案验收", "case": case}).json()["id"]
    with app.state.sessions() as db:
        save_cards(
            db,
            p,
            [
                {"title": "文献一", "source": "pdf", "sources": ["pdf"]},
                {"title": "文献二", "source": "pdf", "sources": ["pdf"]},
            ],
        )
    ids = [c["id"] for c in client.get(f"/api/projects/{p}/evidence").json()]
    fake = PlanLLM(ids)
    app.dependency_overrides[get_llm] = lambda: fake
    client.post(f"/api/projects/{p}/candidate-sets")
    drain(client, app)
    candidate = client.get(f"/api/projects/{p}/candidate-sets").json()[0]["candidates"][0]
    assert client.post("/api/candidates/" + candidate["id"] + ":select").status_code == 200
    return p, candidate


def drain(client, app):
    async def wait():
        await asyncio.gather(*list(app.state.tasks))

    client.portal.call(wait)


def test_plan_selection_lock_new_version_validation_and_stale(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        p, candidate = seed_selected(client, app, case="carbon")
        job = client.post(f"/api/projects/{p}/plans").json()["job_id"]
        drain(client, app)
        assert client.get("/api/jobs/" + job).json()["status"] == "succeeded"
        plan = client.get(f"/api/projects/{p}/plans").json()[0]
        assert plan["method_family"] == "policy_causal" and len(plan["robustness"]) == 4
        assert plan["decision_rules"]["robustness_share"] == 0.75
        assert plan["permutation"]["n"] == 499
        assert plan["treatment_is_real_assignment"] is False  # model cannot authorize causal assignment
        assert (
            client.patch("/api/plans/" + plan["id"], json={**plan, "robustness": plan["robustness"][:3]}).status_code
            == 422
        )
        invalid = {**plan, "method_family": "iv"}
        assert client.patch("/api/plans/" + plan["id"], json=invalid).status_code == 422
        assert client.post("/api/plans/" + plan["id"] + ":confirm").json()["status"] == "confirmed"
        changed = {**plan, "boundary_notes": "仍只报告关联，新增边界"}
        new = client.patch("/api/plans/" + plan["id"], json=changed).json()
        assert new["id"] != plan["id"] and new["version"] == 2 and new["status"] == "draft"
        old = client.get("/api/plans/" + plan["id"]).json()
        assert old["boundary_notes"] == plan["boundary_notes"] and old["status"] == "confirmed"
        assert client.post("/api/plans/" + new["id"] + ":confirm").json()["status"] == "confirmed"
        assert client.get("/api/plans/" + plan["id"]).json()["status"] == "superseded"
        edited = client.patch("/api/candidates/" + candidate["id"], json={**candidate, "hypothesis": "改为探索异质性"})
        assert edited.json()["user_edited"] is True
        assert all(x["stale"] for x in client.get(f"/api/projects/{p}/plans").json())
        assert client.post("/api/plans/" + new["id"] + ":confirm").status_code == 400
        client.patch(f"/api/projects/{p}", json={"direction": {"text": "新的方向"}})
        assert all(x["stale"] for x in client.get(f"/api/projects/{p}/candidate-sets").json())
        assert client.post(f"/api/projects/{p}/plans").status_code == 400
