"""Strict, provider-neutral AI execution telemetry envelope.

No prompt/completion bodies, arbitrary metadata, user identifiers, or credentials
are accepted. This module validates data; it does not persist or route events.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$"
TRACE_PATTERN = r"^[0-9a-f]{32}$"
SPAN_PATTERN = r"^[0-9a-f]{16}$"


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: int = Field(strict=True, ge=0, le=1_000_000_000)
    output: int = Field(strict=True, ge=0, le=1_000_000_000)


class AIExecutionEvent(BaseModel):
    """Content-free telemetry: no secrets, prompts, PII or freeform payloads."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["trancendos.telemetry.ai.v1"]
    event_id: UUID
    occurred_at: datetime
    trace_id: str = Field(pattern=TRACE_PATTERN)
    span_id: str = Field(pattern=SPAN_PATTERN)
    parent_span_id: str | None = Field(default=None, pattern=SPAN_PATTERN)
    service_id: str = Field(pattern=ID_PATTERN)
    operation: Literal["model.invoke", "agent.step", "tool.invoke", "workflow.step"]
    provider: str = Field(pattern=ID_PATTERN)
    model: str = Field(pattern=ID_PATTERN)
    duration_ms: float = Field(strict=True, ge=0, le=86_400_000, allow_inf_nan=False)
    tokens: TokenUsage
    status: Literal["ok", "error", "cancelled"]
    error_code: str | None = Field(default=None, pattern=ID_PATTERN)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must contain a timezone")
        return value

    @model_validator(mode="after")
    def validate_error_code(self):
        if self.status == "error" and self.error_code is None:
            raise ValueError("error_code is required for error status")
        if self.status != "error" and self.error_code is not None:
            raise ValueError("error_code is valid only for error status")
        return self
