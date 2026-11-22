"""Run pytest on a disposable database in the project's local PostgreSQL 18 service."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

API_ROOT = Path(__file__).resolve().parents[1]


class LocalTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT.parent / ".env.numa-test", extra="ignore"
    )
    password: SecretStr = Field(validation_alias="POSTGRES_PASSWORD")


def main() -> int:
    try:
        settings = LocalTestSettings()
    except ValidationError:
        print("Configure POSTGRES_PASSWORD in .env.numa-test before running tests.")
        return 1

    # Never target DATABASE_URL/TEST_DATABASE_URL: tests truncate tables.
    admin_url = URL.create(
        "postgresql+psycopg",
        username="numa_test",
        password=settings.password.get_secret_value(),
        host="127.0.0.1",
        port=29746,
        database="postgres",
    )
    database_name = f"numa_verify_{uuid4().hex}"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    created = False
    try:
        with engine.connect() as connection:
            version = int(connection.scalar(text("SHOW server_version_num")))
            if version // 10000 != 18:
                print("Expected the local PostgreSQL 18 test service; no database created.")
                return 1
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            created = True

        env = os.environ.copy()
        env["TEST_DATABASE_URL"] = admin_url.set(database=database_name).render_as_string(
            hide_password=False
        )
        print("Running pytest in a new disposable PostgreSQL 18 database.", flush=True)
        return subprocess.run(
            [sys.executable, "-m", "pytest", *(sys.argv[1:] or ["-q"])],
            cwd=API_ROOT,
            env=env,
            check=False,
        ).returncode
    except SQLAlchemyError:
        print("Local test database operation failed; check the Docker service/configuration.")
        return 1
    finally:
        try:
            if created:
                with engine.connect() as connection:
                    # Only the randomly named database created by this run is removed.
                    connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
                print("Disposable test database removed.", flush=True)
        finally:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
