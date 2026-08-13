from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_liveness_does_not_require_database_configuration() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_unavailable_database_without_exposing_configuration() -> None:
    settings = Settings(
        database_url=(
            "postgresql+psycopg://private-user:private-password@127.0.0.1:1/"
            "private-db"
        )
    )
    client = TestClient(create_app(settings))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "private-user" not in response.text
    assert "private-password" not in response.text
    assert "private-db" not in response.text
