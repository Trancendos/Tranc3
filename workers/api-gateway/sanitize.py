# workers/api-gateway/sanitize.py
# Vendored copy of Dimensional/sanitize.py — this worker's Docker build context
# is ./workers/api-gateway only, isolated from the repo-root Dimensional
# package worker.py used to import unconditionally. Keep in sync with
# Dimensional/sanitize.py.
#
# Log sanitization and input cleaning utilities.
#
# Prevents log injection (CWE-117, CWE-93) by stripping control characters
# and normalising line breaks in data before it is written to log files.
# An attacker who can inject newline characters into log messages can forge
# log entries, potentially covering their tracks or creating false audit trails.
#
# Usage:
#   from Dimensional.sanitize import sanitize_for_log, SafeLogger
#
#   # Quick sanitization:
#   logger.info("User %s logged in", sanitize_for_log(username))
#
#   # Or use SafeLogger wrapper:
#   safe_log = SafeLogger(logger)
#   safe_log.info("User %s logged in", username)  # auto-sanitized

from __future__ import annotations

import logging
import re
from typing import Any, Optional

# Control characters that enable log injection (newlines, CR, tabs, etc.)
# We keep printable ASCII + safe whitespace, removing everything else.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Newline sequences that can break log lines
_NEWLINE_RE = re.compile(r"[\r\n]+")

# Maximum length for a single log field to prevent log flooding
_MAX_LOG_FIELD_LENGTH = 1024


def sanitize_for_log(
    value: Any,
    *,
    max_length: int = _MAX_LOG_FIELD_LENGTH,
    replacement: str = "_",
) -> str:
    """Sanitize a value for safe inclusion in log messages.

    Removes control characters and replaces newlines with a safe
    replacement character, preventing log injection attacks where
    an attacker could forge log entries by injecting newline characters.

    Args:
        value: The value to sanitize. Will be converted to string.
        max_length: Maximum length for the sanitized output.
        replacement: Character to replace newlines with (default: "_").

    Returns:
        A sanitized string safe for inclusion in log messages.
    """
    text = str(value)

    # Remove null bytes and control characters (except common whitespace)
    text = _CONTROL_CHAR_RE.sub("", text)

    # Replace newlines and carriage returns with the replacement character
    text = _NEWLINE_RE.sub(replacement, text)

    # Truncate if necessary
    if len(text) > max_length:
        text = text[:max_length] + "...[truncated]"

    return text


def sanitize_dict_for_log(
    data: dict,
    *,
    sensitive_keys: Optional[set] = None,
    max_length: int = _MAX_LOG_FIELD_LENGTH,
) -> dict:
    """Sanitize a dictionary for safe logging, redacting sensitive keys.

    Args:
        data: The dictionary to sanitize.
        sensitive_keys: Set of key names whose values should be redacted.
            Defaults to common sensitive field names.
        max_length: Maximum length for individual values.

    Returns:
        A sanitized copy of the dictionary.
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "password",
            "secret",
            "token",
            "api_key",
            "private_key",
            "authorization",
            "cookie",
            "session_id",
            "credit_card",
            "ssn",
            "social_security",
            "bank_account",
        }

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower() if isinstance(key, str) else str(key).lower()
        if any(s in key_lower for s in sensitive_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str):
            sanitized[key] = sanitize_for_log(value, max_length=max_length)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_for_log(
                value, sensitive_keys=sensitive_keys, max_length=max_length
            )
        else:
            sanitized[key] = value

    return sanitized


class SafeLogger:
    """Logging wrapper that automatically sanitizes all arguments.

    Drop-in replacement for a standard logger that sanitizes all
    interpolated arguments before passing them to the underlying
    logger. This prevents log injection without requiring manual
    sanitization at every call site.

    Usage:
        import logging
        from Dimensional.sanitize import SafeLogger

        raw_logger = logging.getLogger(__name__)
        logger = SafeLogger(raw_logger)

        # All arguments are automatically sanitized
        logger.info("User %s performed action %s", username, action)
        logger.warning("Failed request from %s: %s", ip_address, error)
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _sanitize_msg(self, msg: str) -> str:
        """Sanitize the message format string itself to prevent log injection."""
        return sanitize_for_log(msg, max_length=4096)

    def _sanitize_args(self, args: tuple) -> tuple:
        """Sanitize all positional arguments for safe logging."""
        return tuple(sanitize_for_log(a) for a in args)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug-level message with automatic sanitization."""
        self._logger.debug(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info-level message with automatic sanitization."""
        self._logger.info(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning-level message with automatic sanitization."""
        self._logger.warning(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error-level message with automatic sanitization."""
        self._logger.error(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical-level message with automatic sanitization."""
        self._logger.critical(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an exception-level message with automatic sanitization."""
        self._logger.exception(self._sanitize_msg(msg), *self._sanitize_args(args), **kwargs)

    # Pass-through for logger attributes
    @property
    def level(self) -> int:
        """Return the underlying logger's effective level."""
        return self._logger.level

    @property
    def name(self) -> str:
        """Return the underlying logger's name."""
        return self._logger.name
