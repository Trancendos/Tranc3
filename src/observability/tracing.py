"""
Tranc3 Distributed Tracing — Zero-Cost Tracer
===============================================
Thread-local trace context, SQLite span storage, and W3C TraceContext propagation.
No external APM service required — all trace data stays local.
Exports to Grafana Tempo via OTEL bridge when available.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.tracing")

# ---------------------------------------------------------------------------
# Trace Context (thread-local)
# ---------------------------------------------------------------------------

_trace_ctx = threading.local()


def current_trace_id() -> Optional[str]:
    return getattr(_trace_ctx, "trace_id", None)


def current_span_id() -> Optional[str]:
    return getattr(_trace_ctx, "span_id", None)


def set_trace(trace_id: Optional[str], span_id: Optional[str]):
    _trace_ctx.trace_id = trace_id
    _trace_ctx.span_id = span_id


def clear_trace():
    _trace_ctx.trace_id = None
    _trace_ctx.span_id = None


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

class Span:
    """A single span within a distributed trace."""

    def __init__(self, trace_id: str, span_id: str, operation: str,
                 service: str = "", parent_span_id: Optional[str] = None):
        self.trace_id = trace_id
        self.span_id = span_id
        self.operation = operation
        self.service = service
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.start_ts = datetime.now(timezone.utc).isoformat()
        self.events: List[Dict[str, Any]] = []
        self.attributes: Dict[str, Any] = {}
        self.status = "ok"

    def add_event(self, name: str, **attrs):
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attrs,
        })

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def set_error(self, error_type: str, message: str):
        self.status = "error"
        self.events.append({
            "name": "exception",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": {"exception.type": error_type, "exception.message": message},
        })

    @property
    def duration_ms(self) -> float:
        return (time.time() - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "service": self.service,
            "status": self.status,
            "start_time": self.start_ts,
            "duration_ms": self.duration_ms,
            "events": self.events,
            "attributes": self.attributes,
        }


# ---------------------------------------------------------------------------
# Tracer (SQLite-backed)
# ---------------------------------------------------------------------------

class Tracer:
    """Distributed tracer with SQLite persistence."""

    def __init__(self, db_path: Optional[Path] = None, service_name: str = "tranc3"):
        self.service_name = service_name
        self._db_path = db_path
        self._local = threading.local()
        if db_path:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        if not self._db_path:
            return None
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        if not conn:
            return
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spans (
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                parent_span_id TEXT,
                operation TEXT NOT NULL,
                service TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ok',
                start_time TEXT NOT NULL,
                duration_ms REAL,
                events TEXT DEFAULT '[]',
                attributes TEXT DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_service ON spans(service)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_start ON spans(start_time)")
        conn.commit()

    def record_span(self, span: Span):
        """Record a completed span."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            conn.execute(
                "INSERT INTO spans (trace_id, span_id, parent_span_id, operation, service, status, start_time, duration_ms, events, attributes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (span.trace_id, span.span_id, span.parent_span_id,
                 span.operation, span.service, span.status,
                 span.start_ts, span.duration_ms,
                 json.dumps(span.events), json.dumps(span.attributes)),
            )
            conn.commit()
        except Exception as e:
            logger.debug("Failed to record span: %s", e)

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all spans for a trace."""
        conn = self._get_conn()
        if not conn:
            return []
        rows = conn.execute("SELECT * FROM spans WHERE trace_id=? ORDER BY start_time", (trace_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_recent_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent traces (one row per trace)."""
        conn = self._get_conn()
        if not conn:
            return []
        rows = conn.execute("""
            SELECT trace_id, MIN(start_time) as started, COUNT(*) as span_count,
                   GROUP_CONCAT(DISTINCT service) as services,
                   CASE WHEN SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) > 0 THEN 'error' ELSE 'ok' END as status
            FROM spans GROUP BY trace_id ORDER BY started DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    @contextmanager
    def span(self, operation: str, parent_trace_id: Optional[str] = None):
        """Context manager for creating and recording a trace span.

        Usage:
            with tracer.span("process_request") as span:
                span.set_attribute("user_id", "123")
                # Do work
        """
        trace_id = parent_trace_id or current_trace_id() or new_trace_id()
        span_id = new_span_id()
        parent_span_id = current_span_id()

        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            operation=operation,
            service=self.service_name,
            parent_span_id=parent_span_id,
        )

        old_trace = current_trace_id()
        old_span = current_span_id()
        set_trace(trace_id, span_id)

        try:
            yield span
        except Exception as e:
            span.set_error(type(e).__name__, str(e))
            raise
        finally:
            self.record_span(span)
            set_trace(old_trace, old_span)


# ---------------------------------------------------------------------------
# W3C TraceContext Propagation
# ---------------------------------------------------------------------------

TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"

# W3C TraceContext format: version-trace_id-span_id-flags
# Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01


def extract_trace_context(headers: Dict[str, str]) -> tuple:
    """Extract trace context from HTTP headers (W3C TraceContext format).

    Returns (trace_id, span_id) or (None, None) if not found.
    """
    traceparent = headers.get(TRACEPARENT_HEADER, "")
    if not traceparent:
        # Try lowercase
        traceparent = headers.get(TRACEPARENT_HEADER.lower(), "")

    if traceparent:
        try:
            parts = traceparent.split("-")
            if len(parts) == 4 and parts[0] == "00":
                trace_id = parts[1]
                parent_span_id = parts[2]
                return trace_id, parent_span_id
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110

    return None, None


def inject_trace_context(trace_id: str, span_id: str, flags: str = "01") -> Dict[str, str]:
    """Create W3C TraceContext headers for outgoing requests."""
    traceparent = f"00-{trace_id}-{span_id}-{flags}"
    return {TRACEPARENT_HEADER: traceparent}


# ---------------------------------------------------------------------------
# Convenience: Global tracer
# ---------------------------------------------------------------------------

_global_tracer: Optional[Tracer] = None


def init_tracing(db_path: Optional[Path] = None, service_name: str = "tranc3") -> Tracer:
    """Initialize the global tracer."""
    global _global_tracer
    _global_tracer = Tracer(db_path=db_path, service_name=service_name)
    return _global_tracer


def get_tracer() -> Tracer:
    """Get the global tracer (creates a no-op one if not initialized)."""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = Tracer(db_path=None, service_name="tranc3")
    return _global_tracer
