import asyncio
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.llm.service import get_llm
from hypoweaver.literature.service import save_cards


class CandidateLLM:
    def __init__(self, ids):
        self.ids = ids
        self.calls = []

    async def generate(self, name, payload, schema, project_id=None):
        self.calls.append(name)
        if name == "review_candidates":
            return schema.model_validate(
                {
                    "decision": "revise",
                    "issues": [
                        {
                            "candidate_id": payload["candidates"][0]["id"],
                            "problem": "可行性需说明",
                            "suggestion": "区分数据需求",
                        }
                    ],
                }
            )
        return schema.model_validate(
            {
                "candidates": [
                    {
                        "title": f"选题{i}",
                        "gap": "证据不足",
                        "hypothesis": "正向关联",
                        "mechanism": ["融资约束"],
                        "required_data": ["面板数据"],
                        "identification": "双向固定效应",
                        "risks": ["非真实分配"],
                        "positioning": "balanced",
                        "evidence_ids": self.ids + ["ev_missing"],
                    }
                    for i in range(2)
                ],
                "recommendation_text": "按数据可得性比较，不作数值排名",
            }
        )


def test_candidates_filter_review_version_and_stale(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        p = client.post("/api/projects", json={"title": "候选验证"}).json()["id"]
        path = f"/api/projects/{p}"
        app.dependency_overrides[get_llm] = lambda: CandidateLLM([])
        assert client.post(path + "/candidate-sets").status_code == 400
        with app.state.sessions() as db:
            save_cards(
                db,
                p,
                [
                    {"title": "文献一", "source": "pdf", "sources": ["pdf"]},
                    {"title": "文献二", "source": "pdf", "sources": ["pdf"]},
                ],
            )
        ids = [c["id"] for c in client.get(path + "/evidence").json()]
        fake = CandidateLLM(ids)
        app.dependency_overrides[get_llm] = lambda: fake

        async def drain():
            await asyncio.gather(*list(app.state.tasks))

        for version in [1, 2]:
            job = client.post(path + "/candidate-sets").json()["job_id"]
            client.portal.call(drain)
            assert client.get("/api/jobs/" + job).json()["status"] == "succeeded"
            result = client.get(path + "/candidate-sets").json()[0]
            assert result["version"] == version and result["status"] == "ready"
            assert result["removed_references"] == 4
            assert result["review"]["revised"] is True
            assert all(c["evidence_ids"] == ids for c in result["candidates"])
        assert fake.calls == ["generate_candidates", "review_candidates", "generate_candidates"] * 2
        client.patch("/api/evidence/" + ids[0], json={"included": False})
        assert all(s["stale"] for s in client.get(path + "/candidate-sets").json())
        fake.ids = []
        client.patch("/api/evidence/" + ids[0], json={"included": True})
        fake.ids = ["ev_invalid"]
        job = client.post(path + "/candidate-sets").json()["job_id"]
        client.portal.call(drain)
        assert client.get("/api/jobs/" + job).json()["status"] == "failed"
        assert client.get(path + "/candidate-sets").json()[0]["candidates"] == []
