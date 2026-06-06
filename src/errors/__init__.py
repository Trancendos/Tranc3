"""Error management — catalog, typed response model, and helpers."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .error_catalog import (
    CATALOG,
    ERROR_DEFINITIONS,
    ErrorCode,
    ErrorDefinition,
    format_error_response,
    get_error,
)


class ErrorDetail(BaseModel):
    """Typed body of every API error response."""

    code: str = Field(description="TRANC3-{DOMAIN}-{SEQ} error code")
    title: str = Field(description="Short human-readable title")
    message: str = Field(description="Descriptive message; may include dynamic context")
    guidance: str = Field(description="How to resolve this error")
    docs_url: str = Field(description="Link to knowledge base article")
    retryable: bool = Field(description="True if the caller may safely retry")
    severity: str = Field(description="debug | info | warning | error | critical")
    request_id: Optional[str] = Field(default=None, description="X-Request-ID for log correlation")


class ErrorResponse(BaseModel):
    """Top-level API error envelope — all 4xx/5xx responses use this shape."""

    error: ErrorDetail


def make_error_response(
    code: ErrorCode,
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
) -> ErrorResponse:
    """Build a typed ErrorResponse from an ErrorCode."""
    defn = get_error(code)
    return ErrorResponse(
        error=ErrorDetail(
            code=code.value,
            title=defn.title,
            message=detail or defn.message,
            guidance=defn.guidance,
            docs_url=defn.docs_url,
            retryable=defn.retryable,
            severity=defn.severity,
            request_id=request_id,
        )
    )


__all__ = [
    "CATALOG",
    "ERROR_DEFINITIONS",
    "ErrorCode",
    "ErrorDefinition",
    "ErrorDetail",
    "ErrorResponse",
    "format_error_response",
    "get_error",
    "make_error_response",
]
