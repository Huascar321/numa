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
        assert scripts.get_revision(EXPECTED_REVISION).down_revision == "009_watcher_runs"

        command.upgrade(config, "head")

        database_inspector = inspect(engine)
        assert {
            "jobs",
            "currencies",
            "plans",
            "accounts",
            "category_groups",
            "categories",
            "tags",
            "transactions",
            "transaction_tags",
            "posted_account_movements",
            "transaction_corrections",
            "monthly_budget_assignments",
            "transfers",
            "transfer_legs",
            "reconciliation_sessions",
        } <= set(
            database_inspector.get_table_names()
        )
        assert _current_revision(database_url) == EXPECTED_REVISION

        correction_columns = {
            column["name"]
            for column in database_inspector.get_columns("transaction_corrections")
        }
        movement_columns = {
            column["name"]
            for column in database_inspector.get_columns("posted_account_movements")
        }
        assert "correction_sequence" in correction_columns
        assert "correction_sequence" in movement_columns
        correction_constraints = {
            constraint["name"]
            for constraint in database_inspector.get_unique_constraints(
                "transaction_corrections"
            )
        }
        assert "uq_transaction_corrections_transaction_sequence" in correction_constraints

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
            "budget_timezone",
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
        assert plan_columns["budget_timezone"]["nullable"] is False
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


def test_upgrade_from_accounts_backfills_timezone_and_pending_then_is_no_op(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "002_accounts")
        plan_id = uuid4()
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO plans "
                    "(id, name, reporting_currency_code, creation_fingerprint) "
                    "VALUES (:id, 'Existing', 'BOB', 'legacy')"
                ),
                {"id": plan_id},
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT budget_timezone, count(*) FROM plans p "
                    "JOIN categories c ON c.plan_id = p.id "
                    "WHERE p.id = :id AND c.is_pending GROUP BY budget_timezone"
                ),
                {"id": plan_id},
            ).one() == ("America/La_Paz", 1)
            assert _current_revision(database_url) == EXPECTED_REVISION
        engine.dispose()


def test_upgrade_from_ledger_core_then_repeated_head_and_readiness(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "003_ledger_core")
        assert _current_revision(database_url) == "003_ledger_core"
        assert TestClient(create_app(Settings(database_url=database_url))).get("/health/ready").status_code == 503
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        before = (_current_revision(database_url), tuple(sorted(inspect(engine).get_table_names())))
        command.upgrade(config, "head")
        after = (_current_revision(database_url), tuple(sorted(inspect(engine).get_table_names())))
        assert before == after
        assert before[0] == EXPECTED_REVISION
        assert {"transfers", "transfer_legs"} <= set(before[1])
        assert TestClient(create_app(Settings(database_url=database_url))).get("/health/ready").status_code == 200
        engine.dispose()


def test_upgrade_from_budget_engine_then_repeated_head_and_readiness(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "005_budget_engine")
        assert _current_revision(database_url) == "005_budget_engine"
        assert TestClient(
            create_app(Settings(database_url=database_url))
        ).get("/health/ready").status_code == 503

        command.upgrade(config, "head")
        engine = create_engine(database_url)
        before = (
            _current_revision(database_url),
            tuple(sorted(inspect(engine).get_table_names())),
        )
        command.upgrade(config, "head")
        after = (
            _current_revision(database_url),
            tuple(sorted(inspect(engine).get_table_names())),
        )

        assert before == after
        assert after[0] == EXPECTED_REVISION
        assert "reconciliation_sessions" in after[1]
        assert TestClient(
            create_app(Settings(database_url=database_url))
        ).get("/health/ready").status_code == 200
        engine.dispose()


def test_upgrade_from_reconciliation_preserves_existing_plan_and_reaches_gmail(
    postgres_url: str,
) -> None:
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "006_reconciliation")
        client = TestClient(create_app(Settings(database_url=database_url)))
        plan_id = uuid4()
        _seed_legacy_plan(database_url, plan_id, "Existing plan")
        assert client.get("/health/ready").status_code == 503
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert _current_revision(database_url) == EXPECTED_REVISION
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/plans/{plan_id}").json()["name"] == "Existing plan"
        assert client.get(f"/plans/{plan_id}/gmail").json()["sources"] == []
        engine = create_engine(database_url)
        assert {"gmail_sources", "gmail_oauth_states", "gmail_messages"} <= set(inspect(engine).get_table_names())
        engine.dispose()


def test_gmail_filter_migration_fences_legacy_connection_without_erasing_evidence(postgres_url):
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "007_gmail")
        client = TestClient(create_app(Settings(_env_file=None, database_url=database_url)))
        plan_id, source_id, pending_id = uuid4(), uuid4(), uuid4()
        _seed_legacy_plan(database_url, plan_id, "Legacy Gmail")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO gmail_sources
                    (id, plan_id, email, status, refresh_token_ciphertext,
                     sync_mode, pending_job_id, next_poll_at)
                VALUES (:id, :plan, 'me@example.com', 'active', 'encrypted-legacy',
                        'full', :pending, CURRENT_TIMESTAMP)
            """), {"id": source_id, "plan": plan_id, "pending": pending_id})
            connection.execute(text("""
                INSERT INTO gmail_messages
                    (source_id, gmail_id, raw_mime, provider_metadata, decoded, status)
                VALUES (:source, 'legacy', :raw, '{}', '{}', 'decoded')
            """), {"source": source_id, "raw": b"retained evidence"})
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(text("""
                SELECT status, allowed_senders, pending_job_id, next_poll_at,
                       refresh_token_ciphertext FROM gmail_sources WHERE id = :id
            """), {"id": source_id}).one()
            assert row == ("needs_authorization", [], None, None, "encrypted-legacy")
            assert connection.scalar(text("SELECT raw_mime FROM gmail_messages")) == b"retained evidence"
        assert client.get("/health/ready").status_code == 200
        engine.dispose()


def _seed_legacy_plan(database_url, plan_id, name):
    # A legacy schema must be seeded with its own contract, not the current ORM.
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO plans
            (id, name, reporting_currency_code, budget_timezone, creation_fingerprint)
            VALUES (:id, :name, 'BOB', 'America/La_Paz', :fp)"""),
            {"id":plan_id,"name":name,"fp":"a"*64})
        connection.execute(text("""INSERT INTO categories
            (id, plan_id, name, is_pending, creation_fingerprint)
            VALUES (:id, :plan, 'Pendientes', true, :fp)"""),
            {"id":uuid4(),"plan":plan_id,"fp":"b"*64})
    engine.dispose()


def test_ynab_upgrade_backfills_existing_card_without_rewriting_rows(postgres_url):
    with _temporary_database(postgres_url) as database_url:
        config = _alembic_config(database_url)
        command.upgrade(config, "009_watcher_runs")
        plan, card, foreign = uuid4(), uuid4(), uuid4()
        _seed_legacy_plan(database_url, plan, "Preserved Plan")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            for identity, currency in [(card,"BOB"),(foreign,"USDT")]:
                connection.execute(text("""INSERT INTO accounts
                  (id,plan_id,name,account_type,currency_code,creation_fingerprint)
                  VALUES (:id,:plan,:name,'Credit Card',:currency,:fp)"""),
                  dict(id=identity,plan=plan,name=str(identity),currency=currency,fp="c"*64))
            before = connection.execute(text("SELECT * FROM accounts ORDER BY id")).all()
            original = connection.execute(text("SELECT id,name,creation_fingerprint,created_at,updated_at FROM categories")).all()
        command.upgrade(config,"head")
        command.upgrade(config,"head")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM accounts ORDER BY id")).all() == before
            assert connection.execute(text("SELECT id,name,creation_fingerprint,created_at,updated_at FROM categories WHERE payment_account_id IS NULL")).all() == original
            assert connection.execute(text("SELECT payment_account_id FROM categories WHERE payment_account_id IS NOT NULL")).scalars().all() == [card]
        engine.dispose()
