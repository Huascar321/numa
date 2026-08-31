from __future__ import annotations

from fastapi import FastAPI, Response, status

from app.accounts.routes import router as accounts_router
from app.ai.routes import router as ai_router
from app.analytics.routes import router as analytics_router
from app.automation.routes import router as automation_router
from app.fx.routes import router as fx_router
from app.ledger.routes import router as ledger_router
from app.matching.routes import router as matching_router
from app.rules.routes import router as rules_router
from app.statements.routes import router as statements_router
from app.watchers.routes import router as watchers_router
from app.db import database_is_ready
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Numa API")
    application.state.settings = settings or Settings()
    application.include_router(accounts_router)
    application.include_router(ai_router)
    application.include_router(analytics_router)
    application.include_router(automation_router)
    application.include_router(fx_router)
    application.include_router(ledger_router)
    application.include_router(matching_router)
    application.include_router(rules_router)
    application.include_router(statements_router)
    application.include_router(watchers_router)

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
