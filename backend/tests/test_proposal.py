from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.llm.service import get_llm
from hypoweaver.proposal.rendering import NARRATIVE
from test_plans import seed_selected, drain, PlanLLM


class ProposalLLM(PlanLLM):
    def __init__(self, ids, invalid=False):
        super().__init__(ids)
        self.invalid = invalid
        self.calls = []

    async def generate(self, name, payload, schema, project_id=None):
        self.calls.append(name)
        if name == "write_proposal_sections":
            return schema.model_validate(
                {
                    "sections": [
                        {
                            "key": k,
                            "markdown": "样本约为一百家企业，约占百分之五十。"
                            if self.invalid
                            else "结合已纳入文献与变量定义开展后续研究。",
                            "evidence_ids": [self.ids[0], "not-real"],
                        }
                        for k in NARRATIVE
                    ]
                }
            )
        if name == "interpret_results":
            return schema.model_validate(
                {
                    "paragraphs": [
                        {
                            "claim_id": c["claim_id"],
                            "text": "主模型系数为{{num:main.coef}}，p 值为{{num:main.p}}；当前样本呈现条件关联。",
                        }
                        for c in payload["claims"]
                    ]
                }
            )
        return await super().generate(name, payload, schema, project_id)


def test_plan_only_proposal_edit_download_and_fallback(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        p, candidate = seed_selected(client, app)
        fake = ProposalLLM(candidate["evidence_ids"])
        app.dependency_overrides[get_llm] = lambda: fake
        client.post(f"/api/projects/{p}/plans")
        drain(client, app)
        response = client.post(f"/api/projects/{p}/proposals")
        drain(client, app)
        assert client.get("/api/jobs/" + response.json()["job_id"]).json()["status"] == "succeeded"
        proposal = client.get(f"/api/projects/{p}/proposals").json()[0]
        assert proposal["kind"] == "plan_only" and proposal["removed_references"] == 8
        assert len(proposal["sections"]) == 11
        identifier = proposal["id"]
        md = client.get("/api/proposals/" + identifier + ".md")
        assert "计划型提案" in md.text and "文献一" in md.text
        assert (
            client.patch(
                f"/api/proposals/{identifier}/sections/overview", json={"markdown": "人工补充研究问题与限制。"}
            ).status_code
            == 200
        )
        assert (
            client.patch(f"/api/proposals/{identifier}/sections/results", json={"markdown": "结果123"}).status_code
            == 400
        )
        assert (
            client.patch(f"/api/proposals/{identifier}/sections/overview", json={"markdown": "促进了创新"}).status_code
            == 400
        )
        assert (
            client.patch(f"/api/proposals/{identifier}/sections/overview", json={"markdown": "样本99"}).status_code
            == 400
        )
        assert (
            client.patch(
                f"/api/proposals/{identifier}/sections/overview",
                json={"markdown": "样本约为一百家企业，约占百分之五十。"},
            ).status_code
            == 400
        )
        fake.invalid = True
        client.post(f"/api/projects/{p}/proposals")
        drain(client, app)
        newest = client.get(f"/api/projects/{p}/proposals").json()[0]
        assert newest["version"] == 2 and "一百" not in newest["markdown"]
        assert fake.calls.count("write_proposal_sections") == 3


def test_empirical_numbers_claim_decisions_and_traceability(tmp_path):
    import pandas as pd
    from hypoweaver.datasets.service import register
    from test_stats import synthetic

    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        p, candidate = seed_selected(client, app)
        fake = ProposalLLM(candidate["evidence_ids"])
        app.dependency_overrides[get_llm] = lambda: fake
        client.post(f"/api/projects/{p}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{p}/plans").json()[0]
        plan["robustness"][-1]["args"] = {"outcome": "y_alt"}
        plan = client.patch("/api/plans/" + plan["id"], json=plan).json()
        client.post("/api/plans/" + plan["id"] + ":confirm")
        with app.state.sessions() as db:
            dataset = register(
                app.state.settings, db, synthetic(n_units=60), "合成面板", {}, project_id=p, unit="firm", time="year"
            )
            dataset_id = dataset.id
        binding = {
            "dataset_id": dataset_id,
            "confirmed": True,
            "bindings": {
                name: {"field": field}
                for name, field in [("patents", "y"), ("exposure", "d"), ("firm", "firm"), ("year", "year")]
            },
        }
        assert client.put("/api/plans/" + plan["id"] + "/bindings", json=binding).status_code == 200
        job = client.post("/api/plans/" + plan["id"] + "/runs").json()["job_id"]
        drain(client, app)
        status = client.get("/api/jobs/" + job).json()
        assert status["status"] == "succeeded", status
        run = client.get("/api/runs/" + status["result"]["run_id"]).json()
        claim = client.get("/api/runs/" + run["id"] + "/claims").json()[0]
        assert (
            client.patch(
                "/api/claims/" + run["id"] + "/" + claim["claim_id"],
                json={"user_decision": "accepted", "chosen_strength": "causal_cautious", "final_text": "促进了创新"},
            ).status_code
            == 400
        )
        job = client.post(f"/api/projects/{p}/proposals").json()["job_id"]
        drain(client, app)
        status = client.get("/api/jobs/" + job).json()
        assert status["status"] == "succeeded", status
        proposal = client.get("/api/proposals/" + status["result"]["proposal_id"]).json()
        assert proposal["kind"] == "empirical"
        result = next(s for s in proposal["sections"] if s["key"] == "results")
        assert result["injected_numbers_ref"]["main.coef"] == run["result"]["main"]["coef"]
        assert result["injected_numbers_ref"]["main.p"] == run["result"]["main"]["p"]
        assert result["source_ref"] == run["id"]
        assert result["injected_numbers_ref"]["permutation.observed"] == run["result"]["permutation"]["observed"]
        assert "无控制变量模型，观测系数" in proposal["markdown"]
        assert format(run["result"]["permutation"]["observed"], ".6g") in proposal["markdown"]
        assert "{{num:" not in proposal["markdown"]
        assert "促进" not in proposal["markdown"]
        assert format(run["result"]["main"]["coef"], ".6g") in proposal["markdown"]


def test_numerical_words_cannot_bypass_injection():
    from hypoweaver.proposal.rendering import issues

    for text in [
        "样本一百家企业",
        "增长百分之五十",
        "几十次置换",
        "数百条观测",
        "变化为零点七个百分点",
        "样本 two hundred firms",
        "约半数企业",
        "三分之一的企业",
        "几分之几",
        "二〇二一年",
        "结果翻倍",
    ]:
        assert issues(text, {}, "associational"), text
    assert not issues("两者存在条件关联，进一步核对文献。", {}, "associational")
