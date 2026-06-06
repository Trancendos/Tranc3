"""
src/core/output_safety.py
─────────────────────────────────────────────────────────────────────────────
AI output safety filtering layer.

Implements content-moderation gates on all AI-generated text before it
reaches the caller, satisfying REQ-SA-003 (DEF STAN 00-055).

Categories checked:
  - BLOCK  — response suppressed, safe fallback returned
  - WARN   — response returned but logged with elevated severity
  - PASS   — no action required

Usage:
    from src.core.output_safety import OutputSafetyFilter, SafetyVerdict

    filter = OutputSafetyFilter()
    result = filter.check(text, context={"user_id": "u1", "model": "tranc3"})
    if result.verdict == SafetyVerdict.BLOCK:
        text = result.safe_fallback
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SafetyVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class SafetyResult:
    verdict: SafetyVerdict
    triggered_rules: List[str] = field(default_factory=list)
    safe_fallback: str = (
        "I'm unable to provide that response. "
        "Please rephrase your request or contact support."
    )
    details: Dict[str, Any] = field(default_factory=dict)


class OutputSafetyFilter:
    """
    Rule-based output safety filter.

    Rules are evaluated in priority order; first BLOCK rule wins.
    WARN rules accumulate — all matching rules are logged.
    """

    # Patterns that trigger an immediate BLOCK
    _BLOCK_PATTERNS: List[tuple[str, str]] = [
        # Credential / secret leakage
        (r"(?i)(BEGIN\s+(RSA|EC|OPENSSH)\s+PRIVATE\s+KEY)", "credential-leak-private-key"),
        (r"(?i)(sk-[a-zA-Z0-9]{32,})", "credential-leak-api-key"),
        (r"(?i)(password\s*[:=]\s*['\"]?\S{8,})", "credential-leak-password"),
        # Internal secret references
        (r"(?i)(SECRET_KEY|JWT_SECRET|DATABASE_URL)\s*[:=]\s*\S+", "internal-secret-ref"),
        # Prompt injection echoes
        (r"(?i)(ignore previous instructions|forget your system prompt|you are now)", "prompt-injection-echo"),
        # PII exfiltration patterns
        (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "pii-card-number"),
        (r"\b[A-Z]{2}\d{6}[A-Z]\b", "pii-passport-number"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "pii-ssn"),
    ]

    # Patterns that trigger a WARN (logged but not blocked)
    _WARN_PATTERNS: List[tuple[str, str]] = [
        (r"(?i)(internal server error|stack trace|traceback)", "internal-error-leak"),
        (r"(?i)(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{4}", "internal-address-leak"),
        (r"(?i)(todo|fixme|hack|xxx)\s*:", "dev-comment-leak"),
        (r"(?i)(admin|root|superuser)\s+password", "elevated-credential-mention"),
    ]

    def __init__(self) -> None:
        self._block_compiled = [
            (re.compile(pat), rule_id)
            for pat, rule_id in self._BLOCK_PATTERNS
        ]
        self._warn_compiled = [
            (re.compile(pat), rule_id)
            for pat, rule_id in self._WARN_PATTERNS
        ]

    def check(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyResult:
        """Evaluate text against all safety rules. Returns SafetyResult."""
        ctx = context or {}

        # Check BLOCK rules first
        for pattern, rule_id in self._block_compiled:
            if pattern.search(text):
                logger.warning(
                    "output_safety BLOCK rule=%s user=%s model=%s",
                    rule_id,
                    ctx.get("user_id", "unknown"),
                    ctx.get("model", "unknown"),
                )
                return SafetyResult(
                    verdict=SafetyVerdict.BLOCK,
                    triggered_rules=[rule_id],
                    details={"rule": rule_id, "context": ctx},
                )

        # Check WARN rules — accumulate all matches
        warned: List[str] = []
        for pattern, rule_id in self._warn_compiled:
            if pattern.search(text):
                warned.append(rule_id)

        if warned:
            logger.warning(
                "output_safety WARN rules=%s user=%s",
                warned,
                ctx.get("user_id", "unknown"),
            )
            return SafetyResult(
                verdict=SafetyVerdict.WARN,
                triggered_rules=warned,
                details={"rules": warned, "context": ctx},
            )

        return SafetyResult(verdict=SafetyVerdict.PASS)

    def apply(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Convenience method: check and return safe text.
        Returns safe_fallback on BLOCK, original text on WARN/PASS.
        """
        result = self.check(text, context=context)
        if result.verdict == SafetyVerdict.BLOCK:
            return result.safe_fallback
        return text


# Module-level singleton
_default_filter = OutputSafetyFilter()


def check_output(text: str, context: Optional[Dict[str, Any]] = None) -> SafetyResult:
    """Check AI output using the module-level default filter."""
    return _default_filter.check(text, context=context)


def safe_output(text: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Return safe text, applying block fallback if needed."""
    return _default_filter.apply(text, context=context)
