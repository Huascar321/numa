from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db import engine_for, session_factory_for


@pytest.fixture(scope="session")
def postgres_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration checks require TEST_DATABASE_URL.")
    if not url.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL.")
    return url


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> str:
    engine = engine_for(postgres_url)
    initial_tables = set(inspect(engine).get_table_names())
    if initial_tables:
        pytest.fail(
            "TEST_DATABASE_URL must reference a clean PostgreSQL database; "
            f"found tables: {sorted(initial_tables)}"
        )

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture(scope="session")
def postgres_sessions(
    migrated_postgres_url: str,
) -> sessionmaker[Session]:
    return session_factory_for(migrated_postgres_url)
