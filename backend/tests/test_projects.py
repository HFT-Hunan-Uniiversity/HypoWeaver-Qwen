from fastapi.testclient import TestClient
from hypoweaver.app import create_app
from hypoweaver.config import Settings


def test_project_crud_and_persistence(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.post("/api/projects", json={"title": " "}).status_code == 422
        response = client.post("/api/projects", json={"title": "碳市场与企业绿色创新"})
        assert response.status_code == 201
        project = response.json()
        project_id = project["id"]
        path = f"/api/projects/{project_id}"
        assert len(client.get("/api/projects").json()) == 1
        assert client.get(path).json()["title"] == project["title"]
        assert all(s["status"] == "not_started" for s in client.get(path + "/overview").json()["stages"])
        update = client.patch(path, json={"direction": {"text": "行业同群暴露", "constraints": ["条件关联"]}})
        assert update.status_code == 200
    with TestClient(create_app(settings)) as client:
        assert client.get(path).json()["direction"]["text"] == "行业同群暴露"
        assert client.delete(path).status_code == 204
        assert client.get("/api/projects").json() == []
        assert client.get(path).status_code == 404
        assert client.get(path).json()["error"]["code"] == "project_not_found"
