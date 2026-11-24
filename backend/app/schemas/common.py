"""Schemas shared across the API."""

from pydantic import BaseModel


class ErrorBody(BaseModel):
    """Consistent error object: code, message and request ID (blueprint section 10)."""

    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
