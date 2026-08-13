from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.jobs.models import Job


class IdempotencyConflict(Exception):
    """An idempotency key was reused with a different request fingerprint."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    request_fingerprint: str,
    maximum_attempts: int = 3,
    now: datetime | None = None,
) -> Job:
    """Persist an idempotent job before its transactional wake signal."""

    if not job_type or not idempotency_key or not request_fingerprint:
        raise ValueError(
            "job type, idempotency key, and request fingerprint are required"
        )
    if (
        isinstance(maximum_attempts, bool)
        or not isinstance(maximum_attempts, int)
        or maximum_attempts <= 0
    ):
        raise ValueError("maximum attempts must be a positive integer")

    statement = (
        insert(Job)
        .values(
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            maximum_attempts=maximum_attempts,
            next_available_at=now or utc_now(),
        )
        .on_conflict_do_nothing(
            index_elements=("job_type", "idempotency_key")
        )
        .returning(Job.id)
    )
    job_id = session.scalar(statement)

    if job_id is not None:
        job = session.get(Job, job_id)
        if job is None:
            raise RuntimeError("inserted job could not be loaded")
        session.execute(
            text("SELECT pg_notify('numa_jobs', :job_id)"),
            {"job_id": str(job.id)},
        )
        return job

    job = session.scalar(
        select(Job).where(
            Job.job_type == job_type,
            Job.idempotency_key == idempotency_key,
        )
    )
    if job is None:
        raise RuntimeError("existing job could not be loaded")
    if job.request_fingerprint != request_fingerprint:
        raise IdempotencyConflict(
            "idempotency key is already associated with a different request"
        )
    return job


def claim_next_job(
    session: Session,
    *,
    claimant_id: str,
    lease_duration: timedelta,
    now: datetime | None = None,
) -> Job | None:
    """Claim one queued job or expired lease in a committed transaction."""

    if not claimant_id:
        raise ValueError("claimant id is required")
    if lease_duration <= timedelta(0):
        raise ValueError("lease duration must be positive")

    claim_time = now or utc_now()
    eligible = or_(
        and_(Job.status == "queued", Job.next_available_at <= claim_time),
        and_(
            Job.status == "running",
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at <= claim_time,
        ),
    )

    with session.begin():
        job = session.scalar(
            select(Job)
            .where(eligible)
            .order_by(Job.next_available_at, Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None

        if job.attempt_count >= job.maximum_attempts:
            _append_failure(
                job,
                "Lease expired after the maximum number of attempts.",
                claim_time,
            )
            job.status = "failed"
            job.completed_at = claim_time
            job.lease_expires_at = None
            job.claim_token = None
            job.updated_at = claim_time
            return None

        if job.status == "running":
            _append_failure(job, "Lease expired before job completion.", claim_time)

        job.status = "running"
        job.claimed_by = claimant_id
        job.claim_token = uuid4()
        job.lease_expires_at = claim_time + lease_duration
        job.attempt_count += 1
        job.updated_at = claim_time
        return job


def complete_job(
    session: Session,
    *,
    job_id: UUID,
    claimant_id: str,
    claim_token: UUID,
    now: datetime | None = None,
) -> bool:
    completed_at = now or utc_now()
    with session.begin():
        job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if (
            job is None
            or job.status != "running"
            or job.claimed_by != claimant_id
            or job.claim_token != claim_token
        ):
            return False
        job.status = "succeeded"
        job.completed_at = completed_at
        job.lease_expires_at = None
        job.claim_token = None
        job.updated_at = completed_at
        return True


def fail_job(
    session: Session,
    *,
    job_id: UUID,
    claimant_id: str,
    claim_token: UUID,
    error: str,
    retryable: bool,
    retry_delay: timedelta,
    now: datetime | None = None,
) -> bool:
    """Retain failure details and either requeue or terminally fail a job."""

    failure_time = now or utc_now()
    if retry_delay < timedelta(0):
        raise ValueError("retry delay must not be negative")

    with session.begin():
        job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if (
            job is None
            or job.status != "running"
            or job.claimed_by != claimant_id
            or job.claim_token != claim_token
        ):
            return False

        _append_failure(job, error, failure_time)
        job.lease_expires_at = None
        job.updated_at = failure_time

        if retryable and job.attempt_count < job.maximum_attempts:
            job.status = "queued"
            job.claimed_by = None
            job.claim_token = None
            job.next_available_at = failure_time + retry_delay
            return True

        job.status = "failed"
        job.completed_at = failure_time
        job.claim_token = None
        return True


def _append_failure(job: Job, message: str, occurred_at: datetime) -> None:
    details = list(job.failure_details or [])
    details.append({"message": message, "occurred_at": occurred_at.isoformat()})
    job.failure_details = details
