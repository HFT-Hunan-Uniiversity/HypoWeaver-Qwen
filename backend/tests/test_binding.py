import pandas as pd
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.datasets.service import register
from test_plans import seed_selected, drain


def test_binding_safe_formulas_readiness_and_missing_data_plan(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        p, _ = seed_selected(client, app)
        client.post(f"/api/projects/{p}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{p}/plans").json()[0]
        base = "/api/plans/" + plan["id"]
        plan["robustness"][-1]["args"] = {"outcome": "y"}
        assert client.patch(base, json=plan).status_code == 200
        assert client.get(base + "/readiness").json()["status"] == "not_ready"
        client.post(base + ":confirm")
        frame = pd.DataFrame(
            [
                {"firm_id": u, "year": 2010 + t, "y": float(u + t), "d": int(u < 3 and t >= 3), "assets": 100.0 + u}
                for u in range(6)
                for t in range(8)
            ]
        )
        with app.state.sessions() as db:
            asset = register(app.state.settings, db, frame, "绑定测试", {}, project_id=p)
            dataset_id = asset.id
        bindings = {
            "patents": {"formula": "log1p(y)"},
            "exposure": {"field": "d"},
            "firm": {"field": "firm_id"},
            "year": {"field": "year"},
        }
        for formula in ["__import__('os').getcwd()", "y.__class__", "y[0]", "log(y, 2)", "y ** 2"]:
            payload = {
                "dataset_id": dataset_id,
                "bindings": {**bindings, "patents": {"formula": formula}},
                "confirmed": True,
            }
            assert client.put(base + "/bindings", json=payload).status_code == 400
        response = client.put(
            base + "/bindings", json={"dataset_id": dataset_id, "bindings": bindings, "confirmed": False}
        )
        assert response.status_code == 200, response.text
        assert client.get(base + "/readiness").json()["status"] == "not_ready"
        client.put(base + "/bindings", json={"dataset_id": dataset_id, "bindings": bindings, "confirmed": True})
        ready = client.get(base + "/readiness").json()
        assert ready["status"] == "ready", ready
        assert ready["sample"]["n_valid"] == 48
        assert ready["sample"]["treated_units"] == 3 and ready["sample"]["control_units"] == 3
        assert ready["sample"]["monotone_units"] == 6
        assert ready["sample"]["first_exposure"] == [{"year": 2013.0, "count": 3}]
        client.put(
            base + "/bindings",
            json={
                "dataset_id": dataset_id,
                "bindings": {k: v for k, v in bindings.items() if k != "patents"},
                "confirmed": True,
            },
        )
        missing = client.get(base + "/readiness").json()
        assert missing["missing"] == ["patents"] and missing["data_plan"]
        bad_log = {**bindings, "patents": {"formula": "log(y - y)"}}
        client.put(base + "/bindings", json={"dataset_id": dataset_id, "bindings": bad_log, "confirmed": True})
        unavailable = client.get(base + "/readiness").json()
        assert unavailable["status"] == "not_ready" and unavailable["sample"]["n_valid"] == 0
