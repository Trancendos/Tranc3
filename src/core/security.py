"""
TRANC3 — Security Configuration Module
Centralized security hardening for the Tranc3 ecosystem.

Implements:
  - Safe model loading (weights_only enforcement)
  - Input sanitization and validation
  - Rate limiting utilities
  - Secure default configurations
  - OWASP Top 10 mitigations

Updated: 2025-07 — CVE Remediation
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
# Secure Model Loading
# ---------------------------------------------------------------------------

SAFE_TORCH_LOAD_KWARGS = {
    "weights_only": True,
    "map_location": "cpu",
    "mmap": True,
}


def safe_torch_load(path: str, device: str = "cpu", **kwargs) -> Dict[str, Any]:
    """
    Secure wrapper around torch.load that enforces weights_only=True
    to prevent pickle-based RCE (CVE-2024-48063, CVE-2025-32434).

    Only loads model state_dicts, not arbitrary Python objects.
    """
    import torch

    safe_kwargs = {**SAFE_TORCH_LOAD_KWARGS, "map_location": device, **kwargs}

    # Force weights_only — never allow pickle deserialization
    safe_kwargs["weights_only"] = True

    try:
        checkpoint = torch.load(path, **safe_kwargs, weights_only=True)
        logger.info(f"Safe load successful: {path}")
        return checkpoint
    except Exception as e:
        logger.error(f"Safe load failed for {path}: {e}")
        raise


def verify_model_integrity(path: str, expected_sha256: Optional[str] = None) -> bool:
    """
    Verify model file integrity via SHA-256 hash.
    Prevents supply-chain attacks on model weights.
    """
    if not os.path.exists(path):
        logger.error(f"Model file not found: {path}")
        return False

    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    actual_hash = sha256_hash.hexdigest()

    if expected_sha256 and actual_hash != expected_sha256:
        logger.error(
            f"Integrity check FAILED for {path}. "
            f"Expected: {expected_sha256}, Got: {actual_hash}"
        )
        return False

    logger.info(f"Integrity check passed for {path} (sha256: {actual_hash[:16]}...)")
    return True


# ---------------------------------------------------------------------------
# Input Sanitization
# ---------------------------------------------------------------------------

# Patterns that indicate potential injection attacks
DANGEROUS_PATTERNS = [
    r"<script[^>]*>.*?</script>",  # XSS
    r"javascript:",                # JS protocol
    r"on\w+\s*=",                  # Event handlers
    r"eval\s*\(",                  # eval() calls
    r"exec\s*\(",                  # exec() calls
    r"__import__\s*\(",            # Python imports
    r"subprocess",                 # Subprocess calls
    r"os\.system",                 # System calls
    r"open\s*\(",                  # File operations
    r"\.\./",                      # Path traversal
]

MAX_INPUT_LENGTH = 8192  # Maximum input length in characters


@dataclass
class SanitizationResult:
    is_safe: bool
    sanitized: str
    threats_detected: List[str] = field(default_factory=list)
    original_length: int = 0
    sanitized_length: int = 0


def sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> SanitizationResult:
    """
    Sanitize user input to prevent injection attacks.
    Implements OWASP A03:2021 — Injection mitigation.
    """
    threats = []
    original_length = len(text)

    # Length check
    if len(text) > max_length:
        text = text[:max_length]
        threats.append(f"Input truncated from {original_length} to {max_length} chars")

    # Null byte removal
    if "\x00" in text:
        text = text.replace("\x00", "")
        threats.append("Null bytes removed")

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            threats.append(f"Potentially dangerous pattern detected: {pattern}")

    # HTML entity encoding for angle brackets (basic XSS prevention)
    sanitized = text
    sanitized = sanitized.replace("<", "&lt;")
    sanitized = sanitized.replace(">", "&gt;")

    return SanitizationResult(
        is_safe=len(threats) == 0,
        sanitized=sanitized,
        threats_detected=threats,
        original_length=original_length,
        sanitized_length=len(sanitized),
    )


def validate_path(path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
    """
    Validate file paths to prevent path traversal (CVE-2026-28684, etc.)
    """
    resolved = Path(path).resolve()

    # Check for path traversal
    if ".." in str(path):
        logger.warning(f"Path traversal detected: {path}")
        return False

    # Check against allowed directories
    if allowed_dirs:
        allowed_resolved = [Path(d).resolve() for d in allowed_dirs]
        if not any(str(resolved).startswith(str(d)) for d in allowed_resolved):
            logger.warning(f"Path outside allowed directories: {path}")
            return False

    return True


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

@dataclass
class RateLimitConfig:
    """Rate limiting configuration for API endpoints."""
    max_requests: int = 100
    window_seconds: int = 60
    burst_size: int = 10

    @property
    def requests_per_second(self) -> float:
        return self.max_requests / self.window_seconds


# ---------------------------------------------------------------------------
# Security Headers Configuration
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


# ---------------------------------------------------------------------------
# Secure Defaults
# ---------------------------------------------------------------------------

class SecureDefaults:
    """
    Enforces secure-by-default configuration across the Tranc3 ecosystem.
    Aligned with OWASP and Magna Carta Digital Rights Framework.
    """

    # CORS — restrictive by default
    CORS_ALLOW_ORIGINS = ["https://trancendos.ai"]
    CORS_ALLOW_METHODS = ["GET", "POST"]
    CORS_ALLOW_HEADERS = ["Content-Type", "Authorization"]
    CORS_MAX_AGE = 600

    # TLS — modern only
    TLS_MIN_VERSION = "TLSv1.3"
    TLS_CIPHERS = "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"

    # Authentication
    JWT_ALGORITHM = "RS256"
    JWT_EXPIRY_SECONDS = 3600
    JWT_REFRESH_EXPIRY_SECONDS = 86400

    # Session
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"

    # Logging — no PII
    LOG_PII_REDACTION = True
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    @classmethod
    def get_cors_config(cls) -> Dict[str, Any]:
        return {
            "allow_origins": cls.CORS_ALLOW_ORIGINS,
            "allow_methods": cls.CORS_ALLOW_METHODS,
            "allow_headers": cls.CORS_ALLOW_HEADERS,
            "max_age": cls.CORS_MAX_AGE,
        }
