from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import EXPECTED_REVISION, engine_for
from app.jobs import (
    IdempotencyConflict,
    Job,
    claim_next_job,
    complete_job,
    enqueue_job,
    fail_job,
)
from app.main import create_app
from app.settings import Settings
from app.worker import Worker


pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def clean_jobs(postgres_sessions: sessionmaker[Session]):
    with postgres_sessions.begin() as session:
        session.execute(delete(Job))
    yield
    with postgres_sessions.begin() as session:
        session.execute(delete(Job))


def test_migration_creates_expected_job_schema(
    migrated_postgres_url: str,
) -> None:
    engine = engine_for(migrated_postgres_url)
    database_inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in database_inspector.get_columns("jobs")
    }
    constraints = database_inspector.get_unique_constraints("jobs")
    check_constraints = {
        constraint["name"]
        for constraint in database_inspector.get_check_constraints("jobs")
    }
    indexes = {
        index["name"] for index in database_inspector.get_indexes("jobs")
    }

    assert {
        "id",
        "job_type",
        "payload",
        "status",
        "idempotency_key",
        "request_fingerprint",
        "attempt_count",
        "maximum_attempts",
        "next_available_at",
        "lease_expires_at",
        "claimed_by",
        "claim_token",
        "created_at",
        "updated_at",
        "completed_at",
        "failure_details",
    } <= columns.keys()
    assert frozenset({"job_type", "idempotency_key"}) in {
        frozenset(item["column_names"]) for item in constraints
    }
    assert {
        "ix_jobs_claim_queued",
        "ix_jobs_claim_running_lease",
    } <= indexes
    assert {
        "ck_jobs_status",
        "ck_jobs_attempt_count",
        "ck_jobs_maximum_attempts",
    } <= check_constraints
    assert all(
        column["type"].__class__.__name__.upper()
        not in {"REAL", "DOUBLE", "FLOAT"}
        for column in columns.values()
    )

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == EXPECTED_REVISION


def test_readiness_succeeds_at_expected_revision(
    migrated_postgres_url: str,
) -> None:
    settings = Settings(
        database_url=migrated_postgres_url,
        ai_api_key=None,
        gmail_client_id=None,
        gmail_client_secret=None,
        exchange_api_key=None,
    )

    response = TestClient(create_app(settings)).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_idempotent_enqueue_and_conflict_leave_original_unchanged(
    postgres_sessions: sessionmaker[Session],
) -> None:
    key = str(uuid4())
    with postgres_sessions.begin() as session:
        original = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"version": "one"},
            idempotency_key=key,
            request_fingerprint="one",
        )

    with postgres_sessions.begin() as session:
        repeated = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"version": "ignored"},
            idempotency_key=key,
            request_fingerprint="one",
        )
        assert repeated.id == original.id

    with pytest.raises(IdempotencyConflict):
        with postgres_sessions.begin() as session:
            enqueue_job(
                session,
                job_type="foundation-test",
                payload={"version": "conflict"},
                idempotency_key=key,
                request_fingerprint="different",
            )

    with postgres_sessions() as session:
        jobs = session.scalars(
            select(Job).where(Job.idempotency_key == key)
        ).all()
        assert len(jobs) == 1
        assert jobs[0].payload == {"version": "one"}
        assert jobs[0].request_fingerprint == "one"


def test_concurrent_claim_only_returns_a_job_to_one_worker(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as session:
        job = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"kind": "claim"},
            idempotency_key=str(uuid4()),
            request_fingerprint="claim",
        )

    start_claim = Barrier(2)

    def claim(claimant_id: str) -> Job | None:
        start_claim.wait()
        with postgres_sessions() as session:
            return claim_next_job(
                session,
                claimant_id=claimant_id,
                lease_duration=timedelta(seconds=30),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-one", "worker-two")))

    claimed_ids = [claim.id for claim in claims if claim is not None]
    assert claimed_ids == [job.id]


@pytest.mark.parametrize("expired", [False, True])
def test_worker_recovers_queued_and_expired_jobs(
    postgres_sessions: sessionmaker[Session],
    expired: bool,
) -> None:
    base_time = datetime(2026, 8, 12, tzinfo=timezone.utc)
    with postgres_sessions.begin() as session:
        job = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"kind": "recovery"},
            idempotency_key=str(uuid4()),
            request_fingerprint="recovery",
            now=base_time,
        )

    if expired:
        with postgres_sessions() as session:
            claim_next_job(
                session,
                claimant_id="stopped-worker",
                lease_duration=timedelta(seconds=1),
                now=base_time,
            )

    recovered = []
    restart_time = base_time + timedelta(seconds=2)
    worker = Worker(
        postgres_sessions,
        claimant_name="restarted-worker",
        handler=lambda claimed: recovered.append(claimed.id),
        lease_duration=timedelta(seconds=30),
        retry_delay=timedelta(seconds=1),
        clock=lambda: restart_time,
    )

    assert worker.run_once() is True
    assert recovered == [job.id]

    with postgres_sessions() as session:
        persisted = session.get(Job, job.id)
        assert persisted is not None
        assert persisted.status == "succeeded"


def test_reclaim_fences_stale_completion_and_failure(
    postgres_sessions: sessionmaker[Session],
) -> None:
    started_at = datetime(2026, 8, 12, tzinfo=timezone.utc)
    reclaimed_at = started_at + timedelta(seconds=2)
    shared_claimant_id = "reused-claimant"

    with postgres_sessions.begin() as session:
        job = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"kind": "fencing"},
            idempotency_key=str(uuid4()),
            request_fingerprint="fencing",
            now=started_at,
        )

    with postgres_sessions() as session:
        first_claim = claim_next_job(
            session,
            claimant_id=shared_claimant_id,
            lease_duration=timedelta(seconds=1),
            now=started_at,
        )
        assert first_claim is not None
        first_token = first_claim.claim_token
        assert first_token is not None

    with postgres_sessions() as session:
        second_claim = claim_next_job(
            session,
            claimant_id=shared_claimant_id,
            lease_duration=timedelta(seconds=30),
            now=reclaimed_at,
        )
        assert second_claim is not None
        second_token = second_claim.claim_token
        assert second_token is not None
        assert second_token != first_token

    with postgres_sessions() as session:
        current = session.get(Job, job.id)
        assert current is not None
        current_state = (
            current.status,
            current.lease_expires_at,
            current.claimed_by,
            current.attempt_count,
            current.claim_token,
            list(current.failure_details),
            current.completed_at,
            current.updated_at,
        )

    with postgres_sessions() as session:
        assert complete_job(
            session,
            job_id=job.id,
            claimant_id=shared_claimant_id,
            claim_token=first_token,
            now=reclaimed_at + timedelta(seconds=1),
        ) is False

    with postgres_sessions() as session:
        assert fail_job(
            session,
            job_id=job.id,
            claimant_id=shared_claimant_id,
            claim_token=first_token,
            error="stale failure",
            retryable=False,
            retry_delay=timedelta(seconds=1),
            now=reclaimed_at + timedelta(seconds=1),
        ) is False

    with postgres_sessions() as session:
        unchanged = session.get(Job, job.id)
        assert unchanged is not None
        assert (
            unchanged.status,
            unchanged.lease_expires_at,
            unchanged.claimed_by,
            unchanged.attempt_count,
            unchanged.claim_token,
            list(unchanged.failure_details),
            unchanged.completed_at,
            unchanged.updated_at,
        ) == current_state

    with postgres_sessions() as session:
        assert complete_job(
            session,
            job_id=job.id,
            claimant_id=shared_claimant_id,
            claim_token=second_token,
            now=reclaimed_at + timedelta(seconds=2),
        ) is True

    with postgres_sessions() as session:
        completed = session.get(Job, job.id)
        assert completed is not None
        assert completed.status == "succeeded"
        assert completed.attempt_count == 2
        assert completed.claim_token is None


def test_retry_and_terminal_failure_retain_details(
    postgres_sessions: sessionmaker[Session],
) -> None:
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    with postgres_sessions.begin() as session:
        job = enqueue_job(
            session,
            job_type="foundation-test",
            payload={"kind": "retry"},
            idempotency_key=str(uuid4()),
            request_fingerprint="retry",
            maximum_attempts=2,
            now=now,
        )

    with postgres_sessions() as session:
        first_claim = claim_next_job(
            session,
            claimant_id="retry-worker",
            lease_duration=timedelta(seconds=30),
            now=now,
        )
        assert first_claim is not None
        first_token = first_claim.claim_token
        assert first_token is not None
    with postgres_sessions() as session:
        assert fail_job(
            session,
            job_id=job.id,
            claimant_id="retry-worker",
            claim_token=first_token,
            error="temporary",
            retryable=True,
            retry_delay=timedelta(seconds=1),
            now=now,
        )

    retry_time = now + timedelta(seconds=1)
    with postgres_sessions() as session:
        second_claim = claim_next_job(
            session,
            claimant_id="retry-worker",
            lease_duration=timedelta(seconds=30),
            now=retry_time,
        )
        assert second_claim is not None
        second_token = second_claim.claim_token
        assert second_token is not None
    with postgres_sessions() as session:
        assert fail_job(
            session,
            job_id=job.id,
            claimant_id="retry-worker",
            claim_token=second_token,
            error="terminal",
            retryable=True,
            retry_delay=timedelta(seconds=1),
            now=retry_time,
        )

    with postgres_sessions() as session:
        persisted = session.get(Job, job.id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert [item["message"] for item in persisted.failure_details] == [
            "temporary",
            "terminal",
        ]
