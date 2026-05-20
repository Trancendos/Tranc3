"""
src/core/security.py
Centralised security utilities — safe model loading, input sanitisation,
path validation, security headers, and secure defaults.

Extracted from PR #3 CVE remediation (bot PR) — adapted for Tranc3 stack.
"""

import os
import re
import hashlib
import logging
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger("tranc3.security")


# ---------------------------------------------------------------------------
# Safe Model Loading (fixes CVE-2024-48063, CVE-2025-32434)
# ---------------------------------------------------------------------------

def safe_torch_load(path: str, device: str = "cpu", **kwargs) -> Dict[str, Any]:
    """Load torch checkpoint with weights_only=True to block pickle RCE."""
    import torch
    safe_kwargs = {"weights_only": True, "map_location": device, **kwargs}
    safe_kwargs["weights_only"] = True  # always enforce
    try:
        checkpoint = torch.load(path, **safe_kwargs)
        logger.info("Safe model load OK: %s", path)
        return checkpoint
    except Exception as exc:
        logger.error("Safe model load failed for %s: %s", path, exc)
        raise


def verify_model_integrity(path: str, expected_sha256: Optional[str] = None) -> bool:
    """SHA-256 integrity check on model files to prevent supply-chain attacks."""
    if not os.path.exists(path):
        logger.error("Model file not found: %s", path)
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if expected_sha256 and actual != expected_sha256:
        logger.error("Integrity FAILED for %s — expected %s got %s", path, expected_sha256[:8], actual[:8])
        return False
    logger.info("Integrity OK: %s (%s…)", path, actual[:16])
    return True


# ---------------------------------------------------------------------------
# Input Sanitisation (OWASP A03:2021)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"on\w+\s*=",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"subprocess",
    r"os\.system",
    r"open\s*\(",
    r"\.\./",
]

MAX_INPUT_LENGTH = 8192


@dataclass
class SanitisationResult:
    is_safe: bool
    sanitised: str
    threats: List[str] = field(default_factory=list)
    original_length: int = 0


def sanitise_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> SanitisationResult:
    threats: List[str] = []
    original_length = len(text)
    if len(text) > max_length:
        text = text[:max_length]
        threats.append(f"Truncated {original_length}→{max_length}")
    if "\x00" in text:
        text = text.replace("\x00", "")
        threats.append("Null bytes removed")
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, text, re.IGNORECASE | re.DOTALL):
            threats.append(f"Dangerous pattern: {pat}")
    sanitised = text.replace("<", "&lt;").replace(">", "&gt;")
    return SanitisationResult(
        is_safe=len(threats) == 0,
        sanitised=sanitised,
        threats=threats,
        original_length=original_length,
    )


def validate_path(path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
    """Prevent path traversal (OWASP A01, CVE-2026-28684)."""
    if ".." in str(path):
        logger.warning("Path traversal attempt: %s", path)
        return False
    resolved = Path(path).resolve()
    if allowed_dirs:
        allowed = [Path(d).resolve() for d in allowed_dirs]
        if not any(str(resolved).startswith(str(d)) for d in allowed):
            logger.warning("Path outside allowed dirs: %s", path)
            return False
    return True


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
}


# ---------------------------------------------------------------------------
# Secure Defaults
# ---------------------------------------------------------------------------

class SecureDefaults:
    CORS_ALLOW_ORIGINS = [
        "https://trancendos.com",
        "https://arcadia.trancendos.com",
        "https://api.trancendos.com",
    ]
    CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization", "X-Request-ID"]
    CORS_MAX_AGE = 600
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_SECONDS = 3600
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    LOG_PII_REDACTION = True

    @classmethod
    def cors_config(cls) -> Dict[str, Any]:
        return {
            "allow_origins": cls.CORS_ALLOW_ORIGINS,
            "allow_methods": cls.CORS_ALLOW_METHODS,
            "allow_headers": cls.CORS_ALLOW_HEADERS,
            "max_age": cls.CORS_MAX_AGE,
        }
