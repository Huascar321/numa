from __future__ import annotations

import threading
from importlib import import_module
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.db import session_factory
from app.jobs.models import Job
from app.jobs.service import claim_next_job, complete_job, fail_job, utc_now
from app.settings import Settings


class RetryableJobError(Exception):
    pass


class TerminalJobError(Exception):
    pass


JobHandler = Callable[[Job], None]


class Worker:
    """Polling worker; PostgreSQL remains the durable source of job state."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        claimant_name: str,
        handler: JobHandler,
        lease_duration: timedelta,
        retry_delay: timedelta,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sessions = sessions
        self._claimant_id = new_worker_claimant_id(claimant_name)
        self._handler = handler
        self._lease_duration = lease_duration
        self._retry_delay = retry_delay
        self._clock = clock

    @property
    def claimant_id(self) -> str:
        return self._claimant_id

    def run_once(self) -> bool:
        with self._sessions() as session:
            job = claim_next_job(
                session,
                claimant_id=self._claimant_id,
                lease_duration=self._lease_duration,
                now=self._clock(),
            )
        if job is None:
            return False
        if job.claim_token is None:
            raise RuntimeError("Claimed job is missing its fencing token.")

        claim_token = job.claim_token

        try:
            self._handler(job)
        except RetryableJobError as exc:
            self._record_failure(job, claim_token, str(exc), retryable=True)
        except TerminalJobError as exc:
            self._record_failure(job, claim_token, str(exc), retryable=False)
        except Exception as exc:
            self._record_failure(
                job,
                claim_token,
                f"Unhandled job error: {exc}",
                retryable=False,
            )
        else:
            with self._sessions() as session:
                complete_job(
                    session,
                    job_id=job.id,
                    claimant_id=self._claimant_id,
                    claim_token=claim_token,
                    now=self._clock(),
                )
        return True

    def _record_failure(
        self,
        job: Job,
        claim_token: UUID,
        error: str,
        *,
        retryable: bool,
    ) -> None:
        with self._sessions() as session:
            fail_job(
                session,
                job_id=job.id,
                claimant_id=self._claimant_id,
                claim_token=claim_token,
                error=error,
                retryable=retryable,
                retry_delay=self._retry_delay,
                now=self._clock(),
            )

    def run_forever(self, *, database_url: str, poll_seconds: int) -> NoReturn:
        if poll_seconds <= 0:
            raise ValueError("poll seconds must be positive")
        while True:
            if self.run_once():
                continue
            _wait_for_notification(database_url, poll_seconds)


def _wait_for_notification(database_url: str, timeout_seconds: int) -> None:
    """Use LISTEN/NOTIFY only as an optional wake-up for durable polling."""

    try:
        psycopg = import_module("psycopg")
        connection_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        with psycopg.connect(connection_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("LISTEN numa_jobs")
            for _notification in connection.notifies(
                timeout=timeout_seconds,
                stop_after=1,
            ):
                return
    except Exception:
        threading.Event().wait(timeout_seconds)


def _unconfigured_handler(_job: Job) -> None:
    raise TerminalJobError("No handler is configured for this job type.")


def new_worker_claimant_id(claimant_name: str) -> str:
    if not claimant_name:
        raise ValueError("claimant name is required")
    return f"{claimant_name}-{uuid4()}"


def main() -> None:
    settings = Settings()
    database_url = settings.require_database_url()
    worker = Worker(
        session_factory(settings),
        claimant_name="numa-worker",
        handler=_unconfigured_handler,
        lease_duration=timedelta(seconds=settings.worker_lease_seconds),
        retry_delay=timedelta(seconds=settings.worker_poll_seconds),
    )
    worker.run_forever(
        database_url=database_url,
        poll_seconds=settings.worker_poll_seconds,
    )
