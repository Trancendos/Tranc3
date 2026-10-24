"""Regression tests for the Observatory provider-neutral telemetry contract."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workers" / "observatory"))
from ai_telemetry_contract import AIExecutionEvent  # noqa: E402


def valid_event():
    return {
        "schema_version": "trancendos.telemetry.ai.v1",
        "event_id": str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "service_id": "SRV-OBS-001",
        "operation": "model.invoke",
        "provider": "openrouter",
        "model": "example:model-1",
        "duration_ms": 12.5,
        "tokens": {"input": 12, "output": 3},
        "status": "ok",
        "error_code": None,
    }


def test_accepts_valid_envelope():
    assert AIExecutionEvent.model_validate(valid_event()).service_id == "SRV-OBS-001"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unsupported"),
        ("trace_id", "invalid"),
        ("span_id", "ZZ" * 8),
        ("duration_ms", -1),
        ("duration_ms", float("inf")),
        ("operation", "unknown"),
        ("provider", "../unsafe"),
        ("occurred_at", "2026-10-24T22:00:00"),
    ],
)
def test_rejects_invalid_fields(field, value):
    payload = valid_event()
    payload[field] = value
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["prompt", "completion", "api_key", "user_id", "metadata", "tenant_id"]
)
def test_rejects_sensitive_and_untrusted_extra_fields(field):
    payload = valid_event()
    payload[field] = "secret"
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)


def test_rejects_negative_tokens_and_extra_token_fields():
    payload = valid_event()
    payload["tokens"]["input"] = -1
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)
    payload = valid_event()
    payload["tokens"]["secret"] = "leak"
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)


def test_error_requires_code_and_success_forbids_code():
    payload = valid_event()
    payload["status"] = "error"
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)
    payload["error_code"] = "provider_timeout"
    assert AIExecutionEvent.model_validate(payload).status == "error"
    payload["status"] = "ok"
    with pytest.raises(ValidationError):
        AIExecutionEvent.model_validate(payload)
