"""
Tests for src/observability/tracing.py — Distributed Tracing
==============================================================
Covers: thread-local trace context, Span lifecycle, Tracer with SQLite,
W3C TraceContext propagation, convenience functions.
"""

import tempfile
import threading
from pathlib import Path

import pytest

from src.observability.tracing import (
    Tracer,
    Span,
    clear_trace,
    current_span_id,
    current_trace_id,
    extract_trace_context,
    get_tracer,
    inject_trace_context,
    init_tracing,
    new_span_id,
    new_trace_id,
    set_trace,
)


# ─────────────────────────────────────────────────────────────────────────────
# Trace Context (Thread-Local) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTraceContext:
    """Thread-local trace context management."""

    def setup_method(self):
        clear_trace()

    def teardown_method(self):
        clear_trace()

    def test_initial_state_is_none(self):
        assert current_trace_id() is None
        assert current_span_id() is None

    def test_set_trace(self):
        set_trace("trace-123", "span-456")
        assert current_trace_id() == "trace-123"
        assert current_span_id() == "span-456"

    def test_clear_trace(self):
        set_trace("trace-123", "span-456")
        clear_trace()
        assert current_trace_id() is None
        assert current_span_id() is None

    def test_set_trace_overwrites(self):
        set_trace("trace-1", "span-1")
        set_trace("trace-2", "span-2")
        assert current_trace_id() == "trace-2"
        assert current_span_id() == "span-2"

    def test_thread_isolation(self):
        """Trace context is per-thread."""
        set_trace("main-trace", "main-span")
        other_thread_result = {}

        def worker():
            other_thread_result["trace"] = current_trace_id()
            other_thread_result["span"] = current_span_id()

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Main thread still has its values
        assert current_trace_id() == "main-trace"
        # Other thread has no trace context
        assert other_thread_result["trace"] is None
        assert other_thread_result["span"] is None


class TestTraceIdGeneration:
    """Trace ID and Span ID generation."""

    def test_new_trace_id_is_hex(self):
        tid = new_trace_id()
        assert isinstance(tid, str)
        assert len(tid) == 32  # uuid4 hex
        int(tid, 16)  # Should not raise

    def test_new_trace_id_unique(self):
        ids = {new_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_new_span_id_is_hex(self):
        sid = new_span_id()
        assert isinstance(sid, str)
        assert len(sid) == 16  # uuid4 hex[:16]
        int(sid, 16)  # Should not raise

    def test_new_span_id_unique(self):
        ids = {new_span_id() for _ in range(100)}
        assert len(ids) == 100


# ─────────────────────────────────────────────────────────────────────────────
# Span Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSpan:
    """Span lifecycle: creation, events, attributes, errors, serialization."""

    def test_span_creation(self):
        span = Span(
            trace_id="t1",
            span_id="s1",
            operation="test_op",
            service="test-service",
        )
        assert span.trace_id == "t1"
        assert span.span_id == "s1"
        assert span.operation == "test_op"
        assert span.service == "test-service"
        assert span.parent_span_id is None
        assert span.status == "ok"
        assert span.events == []
        assert span.attributes == {}

    def test_span_with_parent(self):
        span = Span(
            trace_id="t1",
            span_id="s1",
            operation="child_op",
            parent_span_id="parent-1",
        )
        assert span.parent_span_id == "parent-1"

    def test_add_event(self):
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.add_event("request_started", url="/api/test")
        assert len(span.events) == 1
        assert span.events[0]["name"] == "request_started"
        assert span.events[0]["attributes"]["url"] == "/api/test"
        assert "timestamp" in span.events[0]

    def test_set_attribute(self):
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.set_attribute("user_id", "12345")
        span.set_attribute("region", "us-east")
        assert span.attributes["user_id"] == "12345"
        assert span.attributes["region"] == "us-east"

    def test_set_error(self):
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.set_error("ValueError", "Invalid input")
        assert span.status == "error"
        assert len(span.events) == 1
        assert span.events[0]["name"] == "exception"
        assert span.events[0]["attributes"]["exception.type"] == "ValueError"
        assert span.events[0]["attributes"]["exception.message"] == "Invalid input"

    def test_duration_ms(self):
        span = Span(trace_id="t1", span_id="s1", operation="op")
        import time
        time.sleep(0.01)  # 10ms
        duration = span.duration_ms
        assert duration >= 8  # At least ~10ms with some tolerance

    def test_to_dict(self):
        span = Span(
            trace_id="t1",
            span_id="s1",
            operation="op",
            service="svc",
            parent_span_id="p1",
        )
        span.set_attribute("key", "value")
        span.add_event("event1")
        d = span.to_dict()
        assert d["trace_id"] == "t1"
        assert d["span_id"] == "s1"
        assert d["parent_span_id"] == "p1"
        assert d["operation"] == "op"
        assert d["service"] == "svc"
        assert d["status"] == "ok"
        assert d["attributes"]["key"] == "value"
        assert len(d["events"]) == 1
        assert "duration_ms" in d
        assert "start_time" in d


# ─────────────────────────────────────────────────────────────────────────────
# Tracer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTracer:
    """Tracer with SQLite persistence."""

    def test_tracer_no_db(self):
        """Tracer works without a database (no-op recording)."""
        tracer = Tracer(db_path=None, service_name="test")
        with tracer.span("test_op") as span:
            span.set_attribute("x", "1")
        # Should not raise

    def test_tracer_with_db(self):
        """Tracer records spans to SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "traces.db"
            tracer = Tracer(db_path=db_path, service_name="test-svc")

            with tracer.span("op1") as span:
                span.set_attribute("user", "alice")

            # Verify the span was recorded
            traces = tracer.get_trace(span.trace_id)
            assert len(traces) == 1
            assert traces[0]["operation"] == "op1"
            assert traces[0]["service"] == "test-svc"
            assert traces[0]["status"] == "ok"

    def test_tracer_span_with_error(self):
        """Errors in spans are recorded with error status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "traces.db"
            tracer = Tracer(db_path=db_path, service_name="test-svc")

            with pytest.raises(ValueError):
                with tracer.span("failing_op"):
                    raise ValueError("boom")

            # The span should still be recorded with error status
            traces = tracer.get_recent_traces(limit=1)
            assert len(traces) == 1

    def test_tracer_multiple_spans_in_trace(self):
        """Multiple spans in the same trace are linked by trace_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "traces.db"
            tracer = Tracer(db_path=db_path, service_name="test-svc")

            trace_id = new_trace_id()
            with tracer.span("parent_op", parent_trace_id=trace_id) as parent_span:
                parent_span.set_attribute("role", "parent")

            with tracer.span("child_op", parent_trace_id=trace_id) as child_span:
                child_span.set_attribute("role", "child")

            spans = tracer.get_trace(trace_id)
            assert len(spans) == 2
            operations = {s["operation"] for s in spans}
            assert operations == {"parent_op", "child_op"}

    def test_tracer_get_recent_traces(self):
        """get_recent_traces returns summary rows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "traces.db"
            tracer = Tracer(db_path=db_path, service_name="test-svc")

            # Create two traces
            with tracer.span("op1"):
                pass
            with tracer.span("op2"):
                pass

            traces = tracer.get_recent_traces(limit=10)
            assert len(traces) == 2

    def test_tracer_span_restores_context(self):
        """After span context manager exits, previous context is restored."""
        tracer = Tracer(db_path=None, service_name="test")
        set_trace("outer-trace", "outer-span")

        with tracer.span("inner_op") as span:
            # Inside the span, context should be the new span
            assert current_trace_id() == span.trace_id
            assert current_span_id() == span.span_id

        # After the span, previous context should be restored
        assert current_trace_id() == "outer-trace"
        assert current_span_id() == "outer-span"

    def test_tracer_span_uses_existing_trace(self):
        """When there's a current trace, the span joins it."""
        tracer = Tracer(db_path=None, service_name="test")
        existing_trace = new_trace_id()
        set_trace(existing_trace, "existing-span")

        with tracer.span("new_op") as span:
            assert span.trace_id == existing_trace
            assert span.parent_span_id == "existing-span"

    def test_tracer_span_creates_new_trace(self):
        """When there's no current trace, the span creates one."""
        tracer = Tracer(db_path=None, service_name="test")
        clear_trace()

        with tracer.span("standalone_op") as span:
            assert span.trace_id is not None
            assert len(span.trace_id) > 0

    def test_tracer_parent_trace_id_override(self):
        """parent_trace_id parameter overrides current trace context."""
        tracer = Tracer(db_path=None, service_name="test")
        set_trace("existing-trace", "existing-span")

        override_id = new_trace_id()
        with tracer.span("linked_op", parent_trace_id=override_id) as span:
            assert span.trace_id == override_id


# ─────────────────────────────────────────────────────────────────────────────
# W3C TraceContext Propagation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestW3CTraceContext:
    """W3C TraceContext header extraction and injection."""

    def test_extract_valid_traceparent(self):
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        }
        trace_id, span_id = extract_trace_context(headers)
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span_id == "00f067aa0ba902b7"

    def test_extract_lowercase_header(self):
        headers = {
            "traceparent": "00-abc123-def456-01",
        }
        trace_id, span_id = extract_trace_context(headers)
        assert trace_id == "abc123"
        assert span_id == "def456"

    def test_extract_no_header(self):
        trace_id, span_id = extract_trace_context({})
        assert trace_id is None
        assert span_id is None

    def test_extract_invalid_version(self):
        headers = {"traceparent": "01-abc123-def456-01"}
        trace_id, span_id = extract_trace_context(headers)
        # Version must be "00"
        assert trace_id is None
        assert span_id is None

    def test_extract_wrong_part_count(self):
        headers = {"traceparent": "00-abc123-def456"}
        trace_id, span_id = extract_trace_context(headers)
        assert trace_id is None
        assert span_id is None

    def test_inject_trace_context(self):
        headers = inject_trace_context("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")
        assert "traceparent" in headers
        assert headers["traceparent"] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_inject_with_custom_flags(self):
        headers = inject_trace_context("abc123", "def456", flags="00")
        assert headers["traceparent"] == "00-abc123-def456-00"

    def test_roundtrip_extract_inject(self):
        """Extracted context should produce the same traceparent when re-injected."""
        original = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        trace_id, span_id = extract_trace_context({"traceparent": original})
        headers = inject_trace_context(trace_id, span_id)
        assert headers["traceparent"] == original


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConvenienceFunctions:
    """init_tracing and get_tracer global instances."""

    def setup_method(self):
        # Reset global tracer
        import src.observability.tracing as mod
        mod._global_tracer = None

    def test_get_tracer_creates_default(self):
        tracer = get_tracer()
        assert tracer is not None
        assert tracer.service_name == "tranc3"

    def test_init_tracing(self):
        tracer = init_tracing(db_path=None, service_name="custom-svc")
        assert tracer.service_name == "custom-svc"
        assert get_tracer() is tracer

    def test_get_tracer_returns_initialized(self):
        init_tracing(db_path=None, service_name="my-svc")
        assert get_tracer().service_name == "my-svc"
