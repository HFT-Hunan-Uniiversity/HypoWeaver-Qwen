from __future__ import annotations

from pathlib import Path


LOCAL_VAR_QUOTA_BYTES = 5 * 1024 * 1024 * 1024
MAX_LOCAL_RUNS = 100
MAX_UPLOAD_DIRECTORIES = 50


class LocalStorageLimitError(RuntimeError):
    def __init__(self, resource: str, current: int, limit: int) -> None:
        self.resource = resource
        self.current = current
        self.limit = limit
        super().__init__(
            f"local storage limit reached: {resource}={current}, limit={limit}; "
            "run the storage audit before adding more local data"
        )

    def detail(self) -> dict[str, int | str]:
        return {
            "code": "local_storage_limit",
            "resource": self.resource,
            "current": self.current,
            "limit": self.limit,
        }


def directory_size_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in current.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                pending.append(entry)
            elif entry.is_file():
                total += entry.stat().st_size
    return total


def ensure_local_storage_capacity(root: Path, *, additional_bytes: int = 0) -> None:
    current = directory_size_bytes(root)
    projected = current + max(0, additional_bytes)
    if projected > LOCAL_VAR_QUOTA_BYTES:
        raise LocalStorageLimitError("backend_var_bytes", projected, LOCAL_VAR_QUOTA_BYTES)
