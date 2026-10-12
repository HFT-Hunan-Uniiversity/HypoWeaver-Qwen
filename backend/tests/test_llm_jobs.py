import asyncio
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import select
from hypoweaver.app import create_app
from hypoweaver.config import Settings
from hypoweaver import jobs
from hypoweaver.llm.models import LLMCall
from hypoweaver.llm.service import LLM, get_llm
from hypoweaver.errors import AppError


class FakeLLM:
    """SDK-shaped client exercising the real structured output repair seam."""

    def __init__(self):
        self.chat = SimpleNamespace(completions=self)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        text = "invalid JSON" if len(self.requests) == 1 else '{"message":"连接成功"}'
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def test_llm_repairs_once_and_logs_usage(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_api_key="test-only", llm_model="test-model")
    app = create_app(settings)
    fake = FakeLLM()
    with TestClient(app) as client:
        app.dependency_overrides[get_llm] = lambda: LLM(settings, app.state.sessions, fake)
        response = client.post("/api/settings/llm:test")
        assert response.status_code == 200
        assert response.json()["message"] == "连接成功"
        assert len(fake.requests) == 2
        assert fake.requests[0]["response_format"] == {"type": "json_object"}
        with app.state.sessions() as db:
            calls = db.scalars(select(LLMCall).order_by(LLMCall.created_at)).all()
            assert [call.status for call in calls] == ["invalid_output", "succeeded"]
            assert sum(call.input_tokens for call in calls) == 20
            assert all(call.model == "test-model" and call.latency_ms >= 0 for call in calls)


def test_unconfigured_model_is_explicit(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, llm_api_key=""))) as client:
        response = client.post("/api/settings/llm:test")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "llm_not_configured"


def test_background_job_success_failure_and_recovery(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)

    @app.post("/test/jobs/{project_id}/{mode}")
    async def submit(project_id: str, mode: str):
        async def work(progress):
            progress("正在验证后台运行")
            if mode == "fail":
                raise AppError("input", "字段缺失")
            return {"answer": 42}

        return {"job_id": jobs.submit(app, "test", project_id, work)}

    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"title": "后台验收"}).json()["id"]
        for mode, expected in [("ok", "succeeded"), ("fail", "failed")]:
            job_id = client.post(f"/test/jobs/{project_id}/{mode}").json()["job_id"]

            async def drain():
                await asyncio.gather(*list(app.state.tasks))

            client.portal.call(drain)
            response = client.get(f"/api/jobs/{job_id}").json()
            assert response["status"] == expected
            assert response["finished_at"]
            if mode == "fail":
                assert response["error"] == "字段缺失"
            else:
                assert response["result"] == {"answer": 42}
        with app.state.sessions() as db:
            interrupted = jobs.Job(project_id=project_id, kind="test", status="running")
            db.add(interrupted)
            db.commit()
            interrupted_id = interrupted.id
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "failed"
        recovered = client.get(f"/api/jobs/{interrupted_id}").json()
        assert recovered["status"] == "failed"
        assert "重启" in recovered["error"]
