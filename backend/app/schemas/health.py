"""Health-check response schema."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    # "not_configured" until the database milestone wires up PostgreSQL.
    database: Literal["ok", "unavailable", "not_configured"]
