from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3.Connection, then release the file handle."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


def connect(path: str | Path, *, timeout: float = 10) -> ClosingConnection:
    return sqlite3.connect(path, timeout=timeout, factory=ClosingConnection)
