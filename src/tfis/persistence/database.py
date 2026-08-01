from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator


class PersistenceError(RuntimeError):
    pass


class PersistenceDatabase:
    def __init__(self, path: str | Path, *, read_only: bool = False, wal: bool = True) -> None:
        self.path = Path(path)
        self.read_only = read_only
        self.wal = wal

    def connect(self) -> sqlite3.Connection:
        if self.read_only:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self.wal and not self.read_only:
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
