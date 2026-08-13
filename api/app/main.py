from __future__ import annotations

from fastapi import FastAPI, Response, status

from app.accounts.routes import router as accounts_router
from app.ledger.routes import router as ledger_router
from app.db import database_is_ready
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Numa API")
    application.state.settings = settings or Settings()
    application.include_router(accounts_router)
    application.include_router(ledger_router)

    @application.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    def ready(response: Response) -> dict[str, str]:
        if database_is_ready(application.state.settings):
            return {"status": "ok"}

        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}

    return application


app = create_app()
