from __future__ import annotations

from fastapi import FastAPI, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.accounts.routes import router as accounts_router
from app.ledger.routes import router as ledger_router
from app.reconciliation.routes import router as reconciliation_router
from app.db import database_is_ready
from app.settings import Settings
from app.gmail.routes import router as gmail_router
from app.gmail.client import GmailConfigurationError, GmailError
from app.binance_card.routes import router as binance_review_router


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Numa API")
    application.state.settings = settings or Settings()
    application.include_router(accounts_router)
    application.include_router(ledger_router)
    application.include_router(reconciliation_router)
    application.include_router(gmail_router)
    application.include_router(binance_review_router)

    @application.exception_handler(GmailConfigurationError)
    def gmail_configuration_error(
        _request: Request, _exc: GmailConfigurationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Gmail is not configured on the server."},
        )

    @application.exception_handler(GmailError)
    def gmail_error(_request: Request, exc: GmailError) -> JSONResponse:
        code = (
            503
            if exc.retryable
            else 409
            if exc.code in {"mailbox_already_connected", "mailbox_mismatch"}
            else 400
        )
        return JSONResponse(
            status_code=code,
            content={"detail": exc.code},
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts = request.url.path.strip("/").split("/")
        if parts[0] == "gmail" or (
            len(parts) >= 3 and parts[0] == "plans" and parts[2] == "gmail"
        ):
            return JSONResponse(
                status_code=422, content={"detail": "Invalid Gmail request."}
            )
        return await request_validation_exception_handler(request, exc)

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
