from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import Settings


INITIAL_REVISION = "001_foundation"
EXPECTED_REVISION = "003_ledger_core"


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=None)
def engine_for(database_url: str) -> Engine:
    if not database_url.startswith("postgresql"):
        raise ValueError("DATABASE_URL must use PostgreSQL.")
    return create_engine(database_url, pool_pre_ping=True)


def session_factory_for(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=engine_for(database_url), expire_on_commit=False)


def session_factory(settings: Settings) -> sessionmaker[Session]:
    return session_factory_for(settings.require_database_url())


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    session = session_factory(settings)()
    try:
        yield session
    finally:
        session.close()


def database_is_ready(settings: Settings) -> bool:
    """Check PostgreSQL connectivity and the current migration revision."""

    if not settings.database_url:
        return False

    try:
        with engine_for(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            return revision == EXPECTED_REVISION
    except Exception:
        return False
