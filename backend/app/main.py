"""FastAPI application entry point."""

import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import chat, documents, equipment, health, search, simulation
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import DatabaseNotConfiguredError
from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger("zhero.api")

API_PREFIX = "/api/v1"


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    error = ErrorBody(code=code, message=message, request_id=_request_id(request))
    body = ErrorResponse(error=error)
    return JSONResponse(status_code=status_code, content=body.model_dump())


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Zhero: software-based medical equipment digital twin and "
            "evidence-verified AI assistant. All twin data is SIMULATED."
        ),
        # OpenAPI docs only in development (blueprint: Sprint 1 definition of done).
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(DatabaseNotConfiguredError)
    async def db_not_configured_handler(
        request: Request, exc: DatabaseNotConfiguredError
    ) -> JSONResponse:
        return _error(request, 503, "database_unavailable", "Database is not configured.")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _error(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error(request, 422, "validation_error", "Request validation failed.")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log details server-side; never return stack traces or paths to the client.
        logger.exception("unhandled_error", extra={"request_id": _request_id(request)})
        return _error(request, 500, "internal_error", "An unexpected error occurred.")

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(equipment.router, prefix=API_PREFIX)
    app.include_router(simulation.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(search.router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    return app


app = create_app()
