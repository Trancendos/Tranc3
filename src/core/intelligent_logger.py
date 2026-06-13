"""Structured intelligent logger with context propagation and anomaly detection — stdlib only."""
from __future__ import annotations

import collections
import contextvars
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ------------------------------------------------------------------ #
#  Context                                                              #
# ------------------------------------------------------------------ #

@dataclass
class LogContext:
    trace_id: str = ""
    user_id: str = ""
    service_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_context_var: contextvars.ContextVar[LogContext] = contextvars.ContextVar(
    "log_context", default=LogContext()
)


def set_context(
    trace_id: str = "",
    user_id: str = "",
    service_name: str = "",
    **extra: Any,
) -> None:
    _context_var.set(LogContext(trace_id=trace_id, user_id=user_id, service_name=service_name, extra=extra))


def get_context() -> LogContext:
    return _context_var.get()


# ------------------------------------------------------------------ #
#  Severity Classifier                                                  #
# ------------------------------------------------------------------ #

_CRITICAL_RE = re.compile(
    r"\b(critical|fatal|catastrophe|crash|corrupt|kernel panic)\b", re.IGNORECASE
)
_ERROR_RE = re.compile(
    r"\b(error|exception|fail(ed|ure)?|traceback|abort|panic|unhandled|unexpected)\b",
    re.IGNORECASE,
)
_WARNING_RE = re.compile(
    r"\b(warn(ing)?|deprecat|caution|unusual|slow|timeout|retry|degraded)\b",
    re.IGNORECASE,
)
_DEBUG_RE = re.compile(
    r"\b(debug|trace|verbose|dump|inspect)\b", re.IGNORECASE
)


class SeverityClassifier:
    """Classifies a message string into a logging level integer."""

    @staticmethod
    def classify(message: str) -> int:
        if _CRITICAL_RE.search(message):
            return logging.CRITICAL
        if _ERROR_RE.search(message):
            return logging.ERROR
        if _WARNING_RE.search(message):
            return logging.WARNING
        if _DEBUG_RE.search(message):
            return logging.DEBUG
        return logging.INFO


# ------------------------------------------------------------------ #
#  Anomaly Detector                                                     #
# ------------------------------------------------------------------ #

class AnomalyDetector:
    """Tracks error counts in a rolling time window and fires a callback on burst."""

    def __init__(
        self,
        window_secs: float = 60.0,
        burst_threshold: int = 10,
        on_alert: Optional[Any] = None,
    ) -> None:
        self._window = window_secs
        self._threshold = burst_threshold
        self._on_alert = on_alert  # callable(count) or None
        self._timestamps: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()
        self._alerted = False

    def record_error(self) -> bool:
        """Record an error event. Returns True if a burst alert fires."""
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            count = len(self._timestamps)
            if count >= self._threshold and not self._alerted:
                self._alerted = True
                if callable(self._on_alert):
                    self._on_alert(count)
                return True
            # reset alert flag when below threshold
            if count < self._threshold:
                self._alerted = False
        return False

    def current_count(self) -> int:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            return len(self._timestamps)


# ------------------------------------------------------------------ #
#  JSON Formatter                                                       #
# ------------------------------------------------------------------ #

class _JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ctx = _context_var.get()
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service_name": ctx.service_name or self._service_name,
            "trace_id": ctx.trace_id,
            "user_id": ctx.user_id,
        }
        anomaly_alert = getattr(record, "anomaly_alert", False)
        if anomaly_alert:
            payload["anomaly_alert"] = True
        if ctx.extra:
            payload.update(ctx.extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# ------------------------------------------------------------------ #
#  IntelligentLogger                                                    #
# ------------------------------------------------------------------ #

class IntelligentLogger:
    def __init__(
        self,
        name: str,
        service_name: str = "",
        anomaly_threshold: int = 10,
        anomaly_window_secs: float = 60.0,
    ) -> None:
        self._logger = logging.getLogger(name)
        self._service_name = service_name
        self._classifier = SeverityClassifier()
        self._anomaly = AnomalyDetector(
            window_secs=anomaly_window_secs,
            burst_threshold=anomaly_threshold,
        )
        # Attach JSON handler if none present
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(_JsonFormatter(service_name))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.DEBUG)
            self._logger.propagate = False

    def _emit(self, level: int, message: str, **kwargs: Any) -> None:
        anomaly_alert = False
        if level >= logging.ERROR:
            anomaly_alert = self._anomaly.record_error()
        extra = {"anomaly_alert": anomaly_alert}
        self._logger.log(level, message, extra=extra, **kwargs)

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
        level = self._classifier.classify(message)
        self._emit(level, message, **kwargs)


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #

def get_logger(name: str, service_name: str = "") -> IntelligentLogger:
    return IntelligentLogger(name=name, service_name=service_name)
