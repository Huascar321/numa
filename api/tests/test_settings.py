from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.settings import Settings
from app.worker import Worker


def test_optional_provider_configuration_can_be_absent(monkeypatch) -> None:
    for name in (
        "AI_API_KEY",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "EXCHANGE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://numa:example@localhost:5432/numa",
    )

    assert settings.ai_api_key is None
    assert settings.gmail_client_id is None
    assert settings.gmail_client_secret is None
    assert settings.exchange_api_key is None

    response = TestClient(create_app(settings)).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_gmail_sender_scope_defaults_normalization_and_environment(monkeypatch) -> None:
    monkeypatch.delenv("GMAIL_ALLOWED_SENDERS", raising=False)
    assert Settings(_env_file=None).gmail_allowed_senders == []
    monkeypatch.setenv("GMAIL_ALLOWED_SENDERS", '["Notice@EXAMPLE.com"," notice@example.com "]')
    assert Settings(_env_file=None).gmail_allowed_senders == ["notice@example.com"]


@pytest.mark.parametrize("sender", ["*", "@example.com", "from:x@example.com", "User <x@example.com>", "a@example.com OR in:anywhere", "a@example.com\n", "a..b@example.com"])
def test_gmail_sender_scope_rejects_broad_or_invalid_inputs(sender, monkeypatch) -> None:
    monkeypatch.delenv("GMAIL_ALLOWED_SENDERS", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gmail_allowed_senders=[sender])

def test_worker_construction_does_not_require_optional_providers() -> None:
    first_worker = Worker(
        sessionmaker(),
        claimant_name="configuration-test",
        handler=lambda _job: None,
        lease_duration=timedelta(seconds=1),
        retry_delay=timedelta(seconds=1),
    )
    second_worker = Worker(
        sessionmaker(),
        claimant_name="configuration-test",
        handler=lambda _job: None,
        lease_duration=timedelta(seconds=1),
        retry_delay=timedelta(seconds=1),
    )

    assert first_worker.claimant_id.startswith("configuration-test-")
    assert second_worker.claimant_id.startswith("configuration-test-")
    assert first_worker.claimant_id != second_worker.claimant_id


def test_reconciliation_configuration_has_safe_exact_defaults_and_validation() -> None:
    settings = Settings()
    assert settings.reconciliation_policy == "block"
    assert settings.reconciliation_tolerance_atoms == 0

    assert Settings(
        reconciliation_policy="warn",
        reconciliation_tolerance_atoms=25,
    ).reconciliation_tolerance_atoms == 25
    with pytest.raises(ValidationError):
        Settings.model_validate({"reconciliation_policy": "allow"})
    with pytest.raises(ValidationError):
        Settings(reconciliation_tolerance_atoms=-1)
