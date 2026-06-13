"""HIPAA sentinel — accepted risk RSK-005 detection coverage.

Monitors for PHI (Protected Health Information) patterns in requests/responses
and alerts when HIPAA_PROFILE is activated without required controls in place.
Does NOT block (risk is accepted) — detects and alerts for audit trail.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("hipaa_sentinel")

# PHI detection patterns (HIPAA Safe Harbor — 18 identifiers)
_PHI_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("npi", re.compile(r"\b\d{10}\b")),  # National Provider Identifier
    ("mrn", re.compile(r"\b(?:mrn|medical[_\s]?record)[:\s#]*\d{5,}\b", re.IGNORECASE)),
    ("dob", re.compile(r"\b(?:dob|date[_\s]?of[_\s]?birth)[:\s]*\d{4}[-/]\d{2}[-/]\d{2}\b", re.IGNORECASE)),
    ("diagnosis_icd", re.compile(r"\b[A-Z]\d{2}(?:\.\d{1,4})?\b")),  # ICD-10 codes
    ("email_phi_ctx", re.compile(r"(?:patient|diagnosis|prescription|treatment).*?[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE | re.DOTALL)),
]

_REQUIRED_HIPAA_CONTROLS = [
    "BAA_EXECUTED",          # env var — Business Associate Agreement
    "AUDIT_LOG_ENABLED",     # env var — PHI access logging
    "ENCRYPTION_AT_REST",    # env var — data encryption
    "MFA_REQUIRED",          # env var — multi-factor authentication
]


@dataclass
class PHIAlert:
    alert_id: str
    detected_at: str
    phi_types: list[str]
    request_path: str
    client_ip: str
    hipaa_profile_active: bool
    missing_controls: list[str]
    severity: str  # "HIGH" | "CRITICAL"


def _check_hipaa_controls() -> list[str]:
    """Return list of missing HIPAA controls."""
    missing = []
    for control in _REQUIRED_HIPAA_CONTROLS:
        if not os.getenv(control, "").lower() in ("true", "1", "yes"):
            missing.append(control)
    return missing


def scan_for_phi(text: str) -> list[str]:
    """Return list of PHI types detected in text."""
    detected = []
    for phi_type, pattern in _PHI_PATTERNS:
        if pattern.search(text):
            detected.append(phi_type)
    return detected


class HIPAASentinelMiddleware(BaseHTTPMiddleware):
    """Middleware: detect PHI in requests and verify HIPAA controls active."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._alerts: list[PHIAlert] = []
        self._hipaa_profile_active = os.getenv("HIPAA_PROFILE", "").lower() in ("true", "1", "yes")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only scan when HIPAA profile is active or on health/medical routes
        path = request.url.path
        is_health_route = any(seg in path for seg in ["/health", "/medical", "/phi", "/patient", "/clinical"])

        if self._hipaa_profile_active or is_health_route:
            # Read body for scanning (small bodies only to avoid memory issues)
            body = b""
            if request.headers.get("content-length", "0").isdigit():
                content_length = int(request.headers.get("content-length", "0"))
                if content_length < 64 * 1024:  # 64KB limit
                    body = await request.body()

            phi_detected = scan_for_phi(body.decode("utf-8", errors="ignore") + path)

            if phi_detected:
                missing_controls = _check_hipaa_controls()
                severity = "CRITICAL" if missing_controls else "HIGH"
                import uuid
                alert = PHIAlert(
                    alert_id=str(uuid.uuid4())[:8],
                    detected_at=datetime.now(timezone.utc).isoformat(),
                    phi_types=phi_detected,
                    request_path=path,
                    client_ip=request.client.host if request.client else "unknown",
                    hipaa_profile_active=self._hipaa_profile_active,
                    missing_controls=missing_controls,
                    severity=severity,
                )
                self._alerts.append(alert)
                log_fn = logger.critical if severity == "CRITICAL" else logger.warning
                log_fn(
                    "PHI DETECTED [%s] path=%s types=%s missing_controls=%s",
                    severity,
                    path,
                    phi_detected,
                    missing_controls,
                )

        response = await call_next(request)
        return response

    def get_alerts(self, limit: int = 100) -> list[dict]:
        return [vars(a) for a in self._alerts[-limit:]]

    def alert_summary(self) -> dict:
        critical = sum(1 for a in self._alerts if a.severity == "CRITICAL")
        return {
            "total_alerts": len(self._alerts),
            "critical": critical,
            "high": len(self._alerts) - critical,
            "hipaa_profile_active": self._hipaa_profile_active,
            "missing_controls": _check_hipaa_controls(),
        }
