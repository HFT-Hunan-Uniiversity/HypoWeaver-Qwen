from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.datasets.service import register
from hypoweaver.plans import service as plans
from hypoweaver.plans.models import PlanDraft, CarbonPlanDraft
from hypoweaver.projects.service import get as get_project
from hypoweaver.cases.carbon import DOI
from test_plans import seed_selected, drain
from test_stats import synthetic


def test_carbon_constraints_use_case_or_bound_doi_not_title(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project, _ = seed_selected(client, app, case=None)
        # This title contains 碳市场, but an explicit case/dataset is still required.
        client.post(f"/api/projects/{project}/plans")
        drain(client, app)
        plan = client.get(f"/api/projects/{project}/plans").json()[0]
        base = "/api/plans/" + plan["id"]
        plan["robustness"][-1]["args"] = {"outcome": "y"}
        assert client.patch(base, json=plan).status_code == 200
        limited = {**plan, "robustness": plan["robustness"][:3]}
        assert client.patch(base, json=limited).status_code == 200
        assert client.post(base + ":confirm").status_code == 200
        with app.state.sessions() as db:
            asset = register(app.state.settings, db, synthetic(n_units=12), "测试 DOI 绑定", {"doi": DOI})
            dataset_id = asset.id
            assert plans.schema_for(db, get_project(db, project)) is PlanDraft
        bindings = {
            "dataset_id": dataset_id,
            "confirmed": True,
            "bindings": {
                name: {"field": field}
                for name, field in [("patents", "y"), ("exposure", "d"), ("firm", "firm"), ("year", "year")]
            },
        }
        assert client.put(base + "/bindings", json=bindings).status_code == 422
        restored = client.patch(base, json=plan).json()
        base = "/api/plans/" + restored["id"]
        assert client.post(base + ":confirm").status_code == 200
        assert client.put(base + "/bindings", json=bindings).status_code == 200
        assert client.patch(base, json=limited).status_code == 422
        with app.state.sessions() as db:
            assert plans.schema_for(db, get_project(db, project)) is CarbonPlanDraft
        # A title without carbon words also gets constraints when explicitly tagged.
        explicit = client.post("/api/projects", json={"title": "一般企业研究", "case": "carbon"}).json()
        assert explicit["case"] == "carbon"
        with app.state.sessions() as db:
            assert plans.schema_for(db, get_project(db, explicit["id"])) is CarbonPlanDraft
        changed = client.patch("/api/projects/" + explicit["id"], json={"case": None}).json()
        assert changed["project"]["case"] is None
        with app.state.sessions() as db:
            assert plans.schema_for(db, get_project(db, explicit["id"])) is PlanDraft
