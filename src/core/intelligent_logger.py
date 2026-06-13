"""
Structured logger with context propagation, severity classification,
and anomaly detection — stdlib only.
"""

from __future__ import annotations

import collections
import contextvars
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class LogContext:
    trace_id: str = ""
    user_id: str = ""
    service_name: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


_context_var: contextvars.ContextVar[Optional[LogContext]] = contextvars.ContextVar(
    "log_context", default=None
)


def set_context(
    trace_id: str = "",
    user_id: str = "",
    service_name: str = "",
    **extra: Any,
) -> None:
    ctx = LogContext(trace_id=trace_id, user_id=user_id, service_name=service_name, extra=extra)
    _context_var.set(ctx)


def get_context() -> LogContext:
    ctx = _context_var.get()
    return ctx if ctx is not None else LogContext()


# ---------------------------------------------------------------------------
# Severity classifier
# ---------------------------------------------------------------------------

_CRITICAL_PATTERNS = re.compile(
    r"\b(critical|fatal|panic|crash|unrecoverable|catastroph)\b", re.IGNORECASE
)
_ERROR_PATTERNS = re.compile(
    r"\b(error|exception|fail(ed|ure)?|traceback|errno|raise|abort)\b", re.IGNORECASE
)
_WARNING_PATTERNS = re.compile(
    r"\b(warn(ing)?|deprecat|caution|slow|timeout|retry|retrying|high\s+latency)\b",
    re.IGNORECASE,
)
_DEBUG_PATTERNS = re.compile(r"\b(debug|trace|verbose|dump|inspect)\b", re.IGNORECASE)


class SeverityClassifier:
    @staticmethod
    def classify(message: str) -> int:
        """Return a stdlib logging level integer."""
        if _CRITICAL_PATTERNS.search(message):
            return logging.CRITICAL
        if _ERROR_PATTERNS.search(message):
            return logging.ERROR
        if _WARNING_PATTERNS.search(message):
            return logging.WARNING
        if _DEBUG_PATTERNS.search(message):
            return logging.DEBUG
        return logging.INFO


# ---------------------------------------------------------------------------
# Anomaly detector (burst detection)
# ---------------------------------------------------------------------------


class AnomalyDetector:
    def __init__(self, window_secs: float = 60.0, burst_threshold: int = 10) -> None:
        self._window = window_secs
        self._threshold = burst_threshold
        self._timestamps: Deque[float] = collections.deque()
        self._lock = threading.Lock()
        self._alert_cb: Optional[Any] = None  # callable(count) -> None

    def set_alert_callback(self, cb: Any) -> None:
        self._alert_cb = cb

    def record_error(self) -> bool:
        """Record an error event. Returns True if burst alert triggered."""
        now = time.monotonic()
        with self._lock:
            # Purge old timestamps
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            self._timestamps.append(now)
            count = len(self._timestamps)

        if count > self._threshold:
            if self._alert_cb:
                try:
                    self._alert_cb(count)
                except Exception:
                    pass
            return True
        return False

    @property
    def current_error_count(self) -> int:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            return len(self._timestamps)


# ---------------------------------------------------------------------------
# JSON formatter for Loki ingestion
# ---------------------------------------------------------------------------


class _LokiJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = get_context()
        payload: Dict[str, Any] = {
            "timestamp": record.created,
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "trace_id": ctx.trace_id,
            "user_id": ctx.user_id,
            "service_name": ctx.service_name or record.name,
        }
        # Merge extra context fields
        payload.update(ctx.extra)

        # Propagate anomaly_alert if set by the logger
        if hasattr(record, "anomaly_alert"):
            payload["anomaly_alert"] = record.anomaly_alert

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# IntelligentLogger
# ---------------------------------------------------------------------------


class IntelligentLogger:
    def __init__(
        self,
        name: str,
        service_name: str = "",
        anomaly_window_secs: float = 60.0,
        anomaly_burst_threshold: int = 10,
    ) -> None:
        self._name = name
        self._service_name = service_name
        self._classifier = SeverityClassifier()
        self._anomaly = AnomalyDetector(anomaly_window_secs, anomaly_burst_threshold)
        self._logger = logging.getLogger(name)

        # Attach JSON handler if none present
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(_LokiJsonFormatter())
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.DEBUG)
            self._logger.propagate = False

    # ------------------------------------------------------------------
    # Core log methods
    # ------------------------------------------------------------------

    def _emit(self, level: int, message: str, **kwargs: Any) -> None:
        extra: Dict[str, Any] = {}
        is_error = level >= logging.ERROR
        if is_error:
            alert_fired = self._anomaly.record_error()
            if alert_fired:
                extra["anomaly_alert"] = True

        record = self._logger.makeRecord(
            self._name,
            level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
            extra=extra,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        self._logger.handle(record)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, message, **kwargs)

    def auto_log(self, message: str, **kwargs: Any) -> None:
        """Classify severity automatically and emit."""
        level = self._classifier.classify(message)
        self._emit(level, message, **kwargs)

    # ------------------------------------------------------------------
    # Anomaly detector access
    # ------------------------------------------------------------------

    @property
    def anomaly_detector(self) -> AnomalyDetector:
        return self._anomaly


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_logger(name: str, service_name: str = "") -> IntelligentLogger:
    return IntelligentLogger(name=name, service_name=service_name)
