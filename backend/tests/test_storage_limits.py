from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from hypoweaver import api as api_module
from hypoweaver.case_import import CaseUploadStore
from hypoweaver.repository import RunRepository
from hypoweaver.storage_limits import (
    MAX_LOCAL_RUNS,
    MAX_UPLOAD_DIRECTORIES,
    LocalStorageLimitError,
)


class _FakeRun:
    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.version = 0
        self.created_at = "2026-08-09T00:00:00+00:00"
        self.updated_at = self.created_at

    def model_dump_json(self) -> str:
        return '{"id":"' + self.id + '"}'


class LocalStorageLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_run_api_returns_structured_conflict(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_module.app),
            base_url="http://127.0.0.1",
        )
        try:
            with patch.object(
                api_module.engine,
                "create_run",
                AsyncMock(side_effect=LocalStorageLimitError("runs", 100, 100)),
            ):
                response = await client.post(
                    "/api/v1/runs",
                    json={"preset_case_id": "green-finance-did"},
                )
        finally:
            await client.aclose()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "local_storage_limit",
                "resource": "runs",
                "current": 100,
                "limit": 100,
            },
        )

    async def test_run_repository_rejects_run_101_without_deleting_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = RunRepository(Path(temporary) / "runs.db")
            with repository._connect() as connection:
                connection.executemany(
                    "INSERT INTO runs (id, version, payload, created_at, updated_at) "
                    "VALUES (?, 1, '{}', 'now', 'now')",
                    [(f"run-{index}",) for index in range(MAX_LOCAL_RUNS)],
                )

            with self.assertRaises(LocalStorageLimitError) as raised:
                repository.create(_FakeRun("run-overflow"))  # type: ignore[arg-type]

            self.assertEqual(raised.exception.resource, "runs")
            with repository._connect() as connection:
                count = int(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
            self.assertEqual(count, MAX_LOCAL_RUNS)

    async def test_upload_store_rejects_directory_51(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "uploads"
            root.mkdir()
            for index in range(MAX_UPLOAD_DIRECTORIES):
                (root / f"upload-{index}").mkdir()
            store = CaseUploadStore(root)

            async def chunks():
                yield b"x,y\n1,2\n"

            with self.assertRaises(LocalStorageLimitError) as raised:
                await store.save("data.csv", chunks())

            self.assertEqual(raised.exception.resource, "upload_directories")
            self.assertEqual(sum(1 for path in root.iterdir() if path.is_dir()), MAX_UPLOAD_DIRECTORIES)

    async def test_upload_store_rejects_total_byte_quota(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "uploads"
            store = CaseUploadStore(root)

            async def chunks():
                yield b"x,y\n1,2\n"

            with patch("hypoweaver.storage_limits.LOCAL_VAR_QUOTA_BYTES", 1), patch(
                "hypoweaver.case_import.LOCAL_VAR_QUOTA_BYTES", 1
            ):
                with self.assertRaises(LocalStorageLimitError) as raised:
                    await store.save("data.csv", chunks())

            self.assertEqual(raised.exception.resource, "backend_var_bytes")
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
