# src/core/logging_config.py
# Structured JSON logging for production deployments.
# Falls back to human-readable console output in development.

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional


class _StructuredFormatter(logging.Formatter):
    """
    Emits one JSON object per log line.
    Fields: ts, level, logger, msg, + any extra kwargs.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge any extra fields passed via logger.info(..., extra={...})
        if hasattr(record, "structured_extra"):
            payload.update(record.structured_extra)
        if record.exc_info and record.exc_info[1] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    """
    Human-readable coloured console output for development.
    """

    COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[35m", # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        # Build base message
        ts = self.formatTime(record, datefmt="%H:%M:%S")
        msg = f"{ts} {color}{record.levelname:8s}{self.RESET} [{record.name}] {record.getMessage()}"
        # Append extras if present
        if hasattr(record, "structured_extra") and record.structured_extra:
            extras = " ".join(f"{k}={v}" for k, v in record.structured_extra.items())
            msg += f"  {extras}"
        if record.exc_info and record.exc_info[1] is not None:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


class StructuredLogger:
    """
    Wrapper that makes it easy to attach structured fields to log messages.

    Usage:
        log = StructuredLogger("tranc3.chat")
        log.info("request completed", duration_ms=42, provider="groq", tokens=128)
    """

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra = {"structured_extra": kwargs} if kwargs else {}
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)


def setup_logging(
    level: str | None = None,
    json_output: bool | None = None,
) -> None:
    """
    Configure root logger for the application.
    Call once at startup before creating any loggers.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR). Falls back to LOG_LEVEL env var or INFO.
        json_output: If True, emit JSON. If None, auto-detect from LOG_FORMAT env var.
    """
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    json_output = json_output if json_output is not None else os.getenv("LOG_FORMAT", "console") == "json"

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(_StructuredFormatter())
    else:
        handler.setFormatter(_ConsoleFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("tranc3").info(
        "logging configured", extra={"structured_extra": {
            "level": level,
            "format": "json" if json_output else "console",
        }}
    )


# ─── Request-scoped timing helper ────────────────────────────────────────

class RequestTimer:
    """
    Context manager that logs the elapsed time of a code block.

    Usage:
        with RequestTimer("chat_request", provider="groq"):
            ...  # do work
        # logs: chat_request completed duration_ms=123.4 provider=groq
    """

    def __init__(self, operation: str, **tags: Any):
        self.operation = operation
        self.tags = tags
        self.log = StructuredLogger("tranc3.timer")

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *exc):
        elapsed_ms = (time.monotonic() - self.start) * 1000
        self.log.info(
            f"{self.operation} completed",
            duration_ms=round(elapsed_ms, 1),
            **self.tags,
        )
        return False
