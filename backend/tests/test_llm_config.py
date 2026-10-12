import sqlite3
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.jobs import Job
from hypoweaver.migrations import migrate


def test_llm_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "offline-test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "config-test-model")
    settings = Settings(_env_file=None, data_dir=tmp_path)
    assert (settings.llm_api_key, settings.llm_base_url, settings.llm_model) == (
        "offline-test-key",
        "https://example.invalid/v1",
        "config-test-model",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        original = app.state.llm
        result = client.get("/api/settings/llm")
        assert result.json() == {
            "model": "config-test-model",
            "base_url": "https://example.invalid/v1",
            "configured": True,
        }
        assert "offline-test-key" not in result.text
        result = client.put("/api/settings/llm", json={"model": "changed-model"})
        assert result.json()["model"] == "changed-model" and result.json()["configured"]
        assert original.model == "config-test-model" and app.state.llm.model == "changed-model"
        assert original.settings.llm_model == "config-test-model"
        assert (tmp_path / ".env.llm").stat().st_mode & 0o777 == 0o600
        assert (
            client.put("/api/settings/llm", json={"base_url": "https://user:secret@example.invalid"}).status_code == 422
        )
        assert client.put("/api/settings/llm", json={"model": " "}).status_code == 422
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/settings/llm").json()["model"] == "changed-model"
        assert client.put("/api/settings/llm", json={"api_key": ""}).json()["configured"] is False
        project = client.post("/api/projects", json={"title": "未配置时应立即拒绝"}).json()["id"]
        for url, payload in [
            ("/api/settings/llm:test", {}),
            (f"/api/projects/{project}/candidate-sets", {}),
            (f"/api/projects/{project}/plans", {}),
            (f"/api/projects/{project}/queries:suggest", {}),
            (f"/api/projects/{project}/proposals", {}),
            ("/api/plans/nonexistent/bindings:suggest", {"dataset_id": "unused"}),
        ]:
            response = client.post(url, json=payload)
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "llm_not_configured"
        with app.state.sessions() as db:
            assert db.scalar(select(Job)) is None


def test_additive_model_migration_preserves_old_rows(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        for table in ["projects", "candidate_sets", "study_plans", "proposals"]:
            db.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, value TEXT)")
            db.execute(f"INSERT INTO {table} VALUES (?, ?)", ("old", "preserved"))
    engine = create_engine(f"sqlite:///{path}")
    migrate(engine)
    migrate(engine)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT value, "case" FROM projects').fetchone() == ("preserved", None)
        assert db.execute("SELECT value, llm_model FROM study_plans").fetchone() == ("preserved", None)
        assert db.execute("SELECT value, model, interpretation FROM proposals").fetchone() == ("preserved", None, None)
    engine.dispose()


def test_empty_environment_base_url_is_unconfigured(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, llm_api_key="offline", llm_base_url=""))
    with TestClient(app) as client:
        assert client.get("/api/settings/llm").json()["configured"] is False
        assert client.post("/api/settings/llm:test").status_code == 409
