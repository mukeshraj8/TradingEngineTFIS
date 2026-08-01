from __future__ import annotations

from types import TracebackType

from .database import PersistenceDatabase
from .migrations import apply_migrations
from .repositories import PersistenceRepositories


class UnitOfWork:
    def __init__(self, database: PersistenceDatabase) -> None:
        self.database = database
        self.connection = None
        self.repositories: PersistenceRepositories | None = None

    def __enter__(self) -> "UnitOfWork":
        self.connection = self.database.connect()
        apply_migrations(self.connection)
        self.connection.commit()
        self.connection.execute("BEGIN")
        self.repositories = PersistenceRepositories(self.connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self.connection is None:
            return False
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
        return False

    @property
    def repo(self) -> PersistenceRepositories:
        if self.repositories is None:
            raise RuntimeError("UnitOfWork is not active.")
        return self.repositories
