"""Log redaction middleware — RSK-009 (API key / secret exposure in logs).

Intercepts log records before they're emitted and redacts secrets,
API keys, passwords, JWTs, and PII patterns.
"""

from __future__ import annotations

import logging
import re

# Named so both _REDACT_PATTERNS (redact-and-continue, for logs) and
# _PII_PATTERNS (detect-only, for pre-forward gates — see contains_pii())
# share one definition of "what an email/credit-card number looks like"
# rather than two that could drift apart.
_EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# UK National Insurance number: 2 letters, 6 digits, 1 letter (e.g.
# QQ123456C) — a strong, low-false-positive PII signal.
_UK_NI_NUMBER_PATTERN = re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b")

# Patterns that should never appear in logs
_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # JWT tokens (header.payload.signature)
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"), "[JWT-REDACTED]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE), "Bearer [TOKEN-REDACTED]"),
    # API keys (generic — long alphanumeric strings after key= or api_key=)
    (
        re.compile(
            r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-\.]{20,})['\"]?"
        ),
        r"\1=[SECRET-REDACTED]",
    ),
    # AWS-style keys
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[AWS-KEY-REDACTED]"),
    # Hex secrets (32+ chars)
    (re.compile(r"(?<![a-zA-Z0-9])([0-9a-f]{64})(?![a-zA-Z0-9])"), "[HEX-SECRET-REDACTED]"),
    # Passwords in URLs
    (re.compile(r"://([^:@/]+):([^@/]+)@"), r"://\1:[PASSWORD-REDACTED]@"),
    # Email addresses (PII)
    (_EMAIL_PATTERN, "[EMAIL-REDACTED]"),
    # Credit card numbers (Luhn-like 13-19 digit sequences)
    (_CREDIT_CARD_PATTERN, "[CC-REDACTED]"),
    # UK National Insurance numbers (PII)
    (_UK_NI_NUMBER_PATTERN, "[NI-NUMBER-REDACTED]"),
    # Private keys (PEM)
    (
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL
        ),
        "[PRIVATE-KEY-REDACTED]",
    ),
    # Stripe keys
    (re.compile(r"sk_(?:live|test)_[a-zA-Z0-9]{24,}"), "[STRIPE-KEY-REDACTED]"),
]


def redact(text: str) -> str:
    """Apply all redaction patterns to a string."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# Detection-only subset for call sites that need a yes/no "does this text
# look like it carries personal data" answer (not a redact-and-continue),
# e.g. a pre-forward gate before content leaves a process boundary.
# Deliberately narrower than _REDACT_PATTERNS above: this omits credential/
# secret patterns (JWT, API keys, AWS keys, private keys, Stripe keys) since
# those are a different risk category (compromised credentials, not personal
# data).
_PII_PATTERNS: tuple[re.Pattern, ...] = (
    _EMAIL_PATTERN,
    _CREDIT_CARD_PATTERN,
    _UK_NI_NUMBER_PATTERN,
)


def contains_pii(text: str) -> bool:
    """Best-effort check for PII-shaped content (email address, credit-card-
    like digit run, UK National Insurance number).

    This is a fast heuristic for call sites deciding whether to forward
    content across a process/trust boundary — it is NOT a compliance-grade
    DLP scanner. A False result means "no strong signal found", not "this
    content contains no personal data" (e.g. a bare name or address with no
    email/card/NI-number won't trip it); a True result should be treated as
    "assume personal data until proven otherwise", not a confirmed positive.
    """
    return any(pattern.search(text) for pattern in _PII_PATTERNS)


class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets before output."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact(original)


class RedactingFilter(logging.Filter):
    """Log filter that redacts secrets from log record message and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg)) if record.msg else record.msg
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(redact(str(a)) for a in record.args)
        return True


def install_global_redactor() -> None:
    """Install RedactingFilter on the root logger — call once at startup."""
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(RedactingFilter())
    root.addFilter(RedactingFilter())
    logger = logging.getLogger(__name__)
    logger.info("Global log redactor installed (RSK-009 mitigation)")
