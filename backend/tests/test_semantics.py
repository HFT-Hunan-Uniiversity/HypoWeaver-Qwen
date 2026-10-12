import pandas as pd
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.claims.service import assess
from hypoweaver.datasets.service import register
from test_plans import seed_selected, drain


def test_peer_exposure_caps_at_association(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project, _ = seed_selected(client, app)
        client.post(f"/api/projects/{project}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{project}/plans").json()[0]
        base = "/api/plans/" + plan["id"]
        client.post(base + ":confirm")
        plan = client.post(base + ":new-version").json()
        base = "/api/plans/" + plan["id"]
        plan = client.patch(base, json={**plan, "treatment_is_real_assignment": True}).json()
        assert client.post(base + ":confirm").status_code == 200
        frame = pd.DataFrame(
            [{"u": u, "t": t, "y": u + t, "d": int(u < 3 and t >= 3)} for u in range(6) for t in range(8)]
        )
        with app.state.sessions() as db:
            asset = register(app.state.settings, db, frame, "合成语义测试", {}, project_id=project)
            dataset_id = asset.id
        url = f"/api/datasets/{dataset_id}/fields/d"
        assert client.patch(url, json={"semantics": "peer_exposure", "level": "industry"}).status_code == 200
        bindings = {
            "firm": {"field": "u"},
            "year": {"field": "t"},
            "patents": {"field": "y"},
            "exposure": {"formula": "d * 1"},
        }
        assert (
            client.put(
                base + "/bindings", json={"dataset_id": dataset_id, "bindings": bindings, "confirmed": True}
            ).status_code
            == 200
        )
        result = {
            "main": {"coef": 0.3, "p": 0.01},
            "event": {"pretrend_wald": {"p": 0.4}},
            "robustness": [{"coef": 0.2, "status": "succeeded"}] * 4,
            "permutation": {"p": 0.01},
        }
        plan = client.get(base).json()
        assert plan["treatment_semantics"] == "peer_exposure"
        claim = assess(plan, result, {"consistent": True})[0]
        assert claim["max_strength"] == "associational"
        assert "处理变量为同群/暴露变量，非真实分配" in claim["blockers"]
        assert client.patch(url, json={"semantics": "made_up"}).status_code == 422
        assert client.patch(url + "missing", json={"level": "firm"}).status_code == 404
        client.post(base + "/runs")
        drain(client, app)
        assert client.patch(url, json={"semantics": "real_assignment", "level": "firm"}).status_code == 200
        plan = client.get(base).json()
        assert plan["treatment_semantics"] == "real_assignment"
        assert assess(plan, result, {"consistent": True})[0]["max_strength"] == "causal_cautious"
        assert (
            assess({**plan, "treatment_is_real_assignment": False}, result, {"consistent": True})[0]["max_strength"]
            == "associational"
        )
        assert all(r["stale"] for r in client.get(base + "/runs").json())
