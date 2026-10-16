import subprocess, sys
from pathlib import Path
from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_import_legacy_cases(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post("/api/projects", json={"title": "现有项目"})
    for _ in range(2):  # 可重复执行
        subprocess.run([sys.executable, str(ROOT / "scripts/import_legacy_cases.py"), "--db", str(tmp_path / "hypoweaver.sqlite")], check=True)
    with TestClient(create_app(settings)) as client:
        projects = client.get("/api/projects").json()
        legacy = [p for p in projects if (p["case"] or "").startswith("legacy:")]
        assert len(projects) == 3 and len(legacy) == 2
        for p in legacy:
            stages = client.get(f"/api/projects/{p['id']}/overview").json()["stages"]
            assert all(s["status"] == "completed" for s in stages)
            proposals = client.get(f"/api/projects/{p['id']}/proposals").json()
            assert [s["key"] for s in proposals[0]["sections"]] == [
                "problem", "rationale", "techniques", "datasets", "title",
                "abstract", "methods", "experiments", "results", "references"]
            assert client.post(f"/api/projects/{p['id']}/proposals").status_code == 409
        carbon = next(p for p in legacy if p["case"] == "legacy:carbon")
        md = client.get(f"/api/projects/{carbon['id']}/proposals").json()[0]["markdown"]
        assert "0.0717" in md and "p=0.494" in md and "/cases/carbon/figure_2_event_study.png" in md
        pid = carbon["id"]
        proposal = client.get(f"/api/projects/{pid}/proposals").json()[0]
        assert not carbon["completed"]
        assert client.post(f"/api/proposals/{proposal['id']}/confirm").status_code == 200
        assert next(p for p in client.get("/api/projects").json() if p["id"] == pid)["completed"] is True
        stages = client.get(f"/api/projects/{pid}/overview").json()["stages"]
        assert stages[-1]["status"] == "confirmed"
