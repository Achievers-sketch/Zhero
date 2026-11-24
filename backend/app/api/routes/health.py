"""GET /api/v1/health."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Report service status.

    The database field reports ``not_configured`` until a database is wired in;
    it never claims ``ok`` without having checked.
    """
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="not_configured",
    )
