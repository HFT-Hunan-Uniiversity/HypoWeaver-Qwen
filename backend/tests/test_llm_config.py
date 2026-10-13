import json
import sqlite3
import pytest
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
            "llm_model": "config-test-model",
            "base_url": "https://example.invalid/v1",
            "configured": True,
        }
        assert "offline-test-key" not in result.text
        result = client.put("/api/settings/llm", json={"llm_model": "changed-model"})
        assert result.json()["llm_model"] == "changed-model" and result.json()["configured"]
        assert original.model == "config-test-model" and app.state.llm.model == "changed-model"
        assert original.settings.llm_model == "config-test-model"
        assert (tmp_path / ".env.llm").stat().st_mode & 0o777 == 0o600
        assert (
            client.put("/api/settings/llm", json={"base_url": "https://user:secret@example.invalid"}).status_code == 422
        )
        assert client.put("/api/settings/llm", json={"llm_model": " "}).status_code == 422
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/settings/llm").json()["llm_model"] == "changed-model"
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
    legacy_interpretation = {"model": "legacy-model", "paragraphs": {"main": "原解读"}, "status": "generated"}
    with sqlite3.connect(path) as db:
        for table in ["projects", "candidate_sets", "study_plans", "proposals"]:
            db.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, value TEXT)")
            db.execute(f"INSERT INTO {table} VALUES (?, ?)", ("old", "preserved"))
        for table in ["candidate_sets", "proposals"]:
            db.execute(f"ALTER TABLE {table} ADD COLUMN model TEXT")
            db.execute(f"UPDATE {table} SET model = ?", ("legacy-model",))
            db.execute(f"INSERT INTO {table} (id, value, model) VALUES (?, ?, ?)", ("unknown", "retained", None))
        db.execute("ALTER TABLE proposals ADD COLUMN interpretation JSON")
        db.execute("UPDATE proposals SET interpretation = ? WHERE id = ?", (json.dumps(legacy_interpretation), "old"))
        db.execute("UPDATE proposals SET interpretation = ? WHERE id = ?", (json.dumps({"model": None}), "unknown"))
    engine = create_engine(f"sqlite:///{path}")
    migrate(engine)
    migrate(engine)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT value, "case" FROM projects').fetchone() == ("preserved", None)
        assert db.execute("SELECT value, llm_model FROM study_plans").fetchone() == ("preserved", None)
        for table in ["candidate_sets", "proposals"]:
            assert db.execute(f"SELECT model, llm_model FROM {table} WHERE id = ?", ("old",)).fetchone() == (
                "legacy-model",
                "legacy-model",
            )
            assert db.execute(f"SELECT model, llm_model FROM {table} WHERE id = ?", ("unknown",)).fetchone() == (
                None,
                None,
            )
        actual = json.loads(db.execute("SELECT interpretation FROM proposals WHERE id = ?", ("old",)).fetchone()[0])
        assert actual == {"llm_model": "legacy-model", "paragraphs": {"main": "原解读"}, "status": "generated"}
        unknown = json.loads(
            db.execute("SELECT interpretation FROM proposals WHERE id = ?", ("unknown",)).fetchone()[0]
        )
        assert unknown == {"llm_model": None}
        db.execute("UPDATE candidate_sets SET llm_model = ? WHERE id = ?", ("newer-model", "old"))
    migrate(engine)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT llm_model FROM candidate_sets WHERE id = ?", ("old",)).fetchone()[0] == "newer-model"
    engine.dispose()


def test_empty_environment_base_url_is_unconfigured(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, llm_api_key="offline", llm_base_url=""))
    with TestClient(app) as client:
        assert client.get("/api/settings/llm").json()["configured"] is False
        assert client.post("/api/settings/llm:test").status_code == 409


@pytest.mark.parametrize("unknown", ["model", "typo"])
def test_llm_settings_reject_unknown_fields_without_mutation(tmp_path, unknown):
    settings = Settings(_env_file=None, data_dir=tmp_path, llm_model="original", llm_api_key="")
    with TestClient(create_app(settings)) as client:
        before = client.put("/api/settings/llm", json={"llm_model": "saved"}).json()
        saved = (tmp_path / ".env.llm").read_bytes()
        response = client.put(
            "/api/settings/llm",
            json={"llm_model": "should-not-save", "api_key": "do-not-echo-this-key", unknown: "unexpected-value"},
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert unknown in message and "未知字段" in message
        assert "do-not-echo-this-key" not in response.text
        assert client.get("/api/settings/llm").json() == before
        assert (tmp_path / ".env.llm").read_bytes() == saved


def test_settings_status_uses_llm_model(tmp_path, monkeypatch):
    import hypoweaver.llm.router as llm_router

    async def offline_probe(url, params):
        return {"status": "ok"}

    monkeypatch.setattr(llm_router, "probe", offline_probe)
    settings = Settings(_env_file=None, data_dir=tmp_path, llm_model="status-test-model", llm_api_key="")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/settings/status")
        assert response.status_code == 200
        data = response.json()
        assert data["llm_model"] == "status-test-model" and "model" not in data
        assert data["configured"] is False
        assert set(data["sources"]) == {"openalex", "crossref"}
