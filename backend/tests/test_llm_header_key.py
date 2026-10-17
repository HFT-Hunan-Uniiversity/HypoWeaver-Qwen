"""Per-browser model key: sent as X-LLM-API-Key, used for that request only, never persisted."""

from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver.llm import service as llm_service
from hypoweaver.llm.models import ConnectionCheck

KEY = "sk-browser-only-test-key-1234567890"


def _app(tmp_path, **kw):
    return create_app(Settings(_env_file=None, data_dir=tmp_path, llm_api_key="", **kw))


def _all_bytes(tmp_path):
    return b"".join(p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_no_header_no_server_key_is_unconfigured(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/settings/llm").json()["configured"] is False
        response = client.post("/api/settings/llm:test")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "llm_not_configured"


def test_header_key_used_per_request_and_never_persisted(tmp_path, monkeypatch):
    seen = []

    async def fake_generate(self, prompt_name, payload, OutputModel, project_id=None, timeout=None):
        seen.append((self.settings.llm_api_key, self.settings.llm_model))
        return ConnectionCheck.model_validate({"message": "连接成功"}) if OutputModel is ConnectionCheck else None

    monkeypatch.setattr(llm_service.LLM, "generate", fake_generate)
    app = _app(tmp_path, allow_settings_write=False)
    with TestClient(app) as client:
        headers = {"X-LLM-API-Key": KEY, "X-LLM-Model": "qwen-turbo"}
        info = client.get("/api/settings/llm", headers=headers).json()
        assert info["configured"] is True and info["server_key"] is False and info["llm_model"] == "qwen-turbo"
        assert KEY not in client.get("/api/settings/llm", headers=headers).text
        assert client.post("/api/settings/llm:test", headers=headers).status_code == 200
        assert seen == [(KEY, "qwen-turbo")]
        # The server-wide settings are untouched and the next header-less request is unconfigured again.
        assert app.state.settings.llm_api_key == "" and app.state.llm.settings.llm_api_key == ""
        assert client.post("/api/settings/llm:test").status_code == 409
        # Public deployment: global settings are read-only.
        assert client.put("/api/settings/llm", json={"llm_model": "x"}).status_code == 403
    assert KEY.encode() not in _all_bytes(tmp_path)


def test_put_never_stores_a_key(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.put("/api/settings/llm", json={"api_key": KEY})
        assert response.status_code == 400 and KEY not in response.text
        assert client.get("/api/settings/llm").json()["configured"] is False
    assert KEY.encode() not in _all_bytes(tmp_path)


def test_bad_header_rejected(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        assert client.post("/api/settings/llm:test", headers={"X-LLM-Model": "bad model!"}).status_code == 400


def test_server_key_still_works_without_header(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, llm_api_key="server-env-key"))
    with TestClient(app) as client:
        info = client.get("/api/settings/llm").json()
        assert info["configured"] is True and info["server_key"] is True
