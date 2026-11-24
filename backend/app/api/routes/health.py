"""GET /api/v1/health."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import get_engine
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger("zhero.health")


def database_status(settings: Settings) -> str:
    """Return ok / unavailable / not_configured; never claims ok without a successful query."""
    if not settings.database_url:
        return "not_configured"
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.warning("database_health_check_failed")
        return "unavailable"


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Report service and database status."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database=database_status(settings),  # type: ignore[arg-type]
    )
