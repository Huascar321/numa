from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.db import EXPECTED_REVISION, engine_for
from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.postgres


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@contextmanager
def _temporary_database(postgres_url: str) -> Iterator[str]:
    database_name = f"numa_accounts_{uuid4().hex}"
    base_url = make_url(postgres_url)
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    database_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        yield database_url
    finally:
        cached_engine = engine_for(database_url)
        cached_engine.dispose()
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


def _current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def test_clean_postgresql_18_database_reaches_accounts_head(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert int(connection.scalar(text("SHOW server_version_num"))) // 10000 == 18

        config = _alembic_config(database_url)
        scripts = ScriptDirectory.from_config(config)
        assert scripts.get_revision(EXPECTED_REVISION).down_revision == "001_foundation"

        command.upgrade(config, "head")

        database_inspector = inspect(engine)
        assert {"jobs", "currencies", "plans", "accounts"} <= set(
            database_inspector.get_table_names()
        )
        assert _current_revision(database_url) == EXPECTED_REVISION

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT code, decimal_places FROM currencies ORDER BY code")
            ).all() == [("BOB", 2), ("USDT", 6)]

        account_columns = {
            column["name"]: column
            for column in database_inspector.get_columns("accounts")
        }
        plan_columns = {
            column["name"]: column
            for column in database_inspector.get_columns("plans")
        }
        assert set(plan_columns) == {
            "id",
            "name",
            "reporting_currency_code",
            "creation_fingerprint",
            "created_at",
            "updated_at",
        }
        assert set(account_columns) == {
            "id",
            "plan_id",
            "name",
            "account_type",
            "currency_code",
            "status",
            "creation_fingerprint",
            "created_at",
            "updated_at",
        }
        assert "balance" not in plan_columns | account_columns
        assert "opening_balance" not in plan_columns | account_columns
        assert all(
            column["type"].__class__.__name__.upper()
            not in {"REAL", "DOUBLE", "FLOAT"}
            for column in [*plan_columns.values(), *account_columns.values()]
        )

        account_checks = {
            constraint["name"]: constraint["sqltext"]
            for constraint in database_inspector.get_check_constraints("accounts")
        }
        assert {
            "ck_accounts_name_nonempty",
            "ck_accounts_account_type",
            "ck_accounts_status",
        } <= set(account_checks)
        for account_type in (
            "Bank",
            "Cash",
            "Wallet",
            "Credit Card",
            "Crypto",
            "Other",
        ):
            assert account_type in account_checks["ck_accounts_account_type"]
        assert "active" in account_checks["ck_accounts_status"]
        assert "archived" in account_checks["ck_accounts_status"]

        foreign_keys = {
            foreign_key["name"]: foreign_key
            for foreign_key in database_inspector.get_foreign_keys("accounts")
        }
        assert foreign_keys["fk_accounts_plan_id_plans"]["referred_table"] == "plans"
        assert (
            foreign_keys["fk_accounts_currency_code_currencies"]["referred_table"]
            == "currencies"
        )
        assert all(
            foreign_key.get("options")
            == {"onupdate": "RESTRICT", "ondelete": "RESTRICT"}
            for foreign_key in foreign_keys.values()
        )
        assert {"ix_accounts_plan_id", "ix_accounts_plan_status"} <= {
            index["name"] for index in database_inspector.get_indexes("accounts")
        }

        response = TestClient(
            create_app(Settings(database_url=database_url))
        ).get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        engine.dispose()


def test_upgrade_from_foundation_then_repeated_head_is_no_op(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "001_foundation")
        assert _current_revision(database_url) == "001_foundation"
        assert TestClient(
            create_app(Settings(database_url=database_url))
        ).get("/health/ready").status_code == 503

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        database_inspector = inspect(engine)
        before_second_upgrade = (
            _current_revision(database_url),
            tuple(sorted(database_inspector.get_table_names())),
            tuple(
                sorted(
                    column["name"]
                    for table_name in ("currencies", "plans", "accounts")
                    for column in database_inspector.get_columns(table_name)
                )
            ),
        )

        command.upgrade(config, "head")

        database_inspector = inspect(engine)
        after_second_upgrade = (
            _current_revision(database_url),
            tuple(sorted(database_inspector.get_table_names())),
            tuple(
                sorted(
                    column["name"]
                    for table_name in ("currencies", "plans", "accounts")
                    for column in database_inspector.get_columns(table_name)
                )
            ),
        )
        assert before_second_upgrade == after_second_upgrade
        assert after_second_upgrade[0] == EXPECTED_REVISION
        engine.dispose()
