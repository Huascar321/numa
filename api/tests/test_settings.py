from datetime import timedelta

from fastapi.testclient import TestClient
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
        database_url="postgresql+psycopg://numa:example@localhost:5432/numa",
    )

    assert settings.ai_api_key is None
    assert settings.gmail_client_id is None
    assert settings.gmail_client_secret is None
    assert settings.exchange_api_key is None

    response = TestClient(create_app(settings)).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
