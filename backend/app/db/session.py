"""Database engine and session dependency."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a DB-backed endpoint is used without DATABASE_URL."""


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not set.")
    return create_engine(url, pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session; commits are explicit in services."""
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
