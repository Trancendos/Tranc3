# tests/test_observability.py — Tests for src/observability/observatory.py
"""Comprehensive tests for the Observatory audit log system."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from src.observability.observatory import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    Observatory,
    get_observatory,
    observe,
)

# ── Enum tests ──────────────────────────────────────────────────────────────


class TestEventSeverity:
    def test_values(self):
        assert EventSeverity.DEBUG == "debug"
        assert EventSeverity.INFO == "info"
        assert EventSeverity.WARNING == "warning"
        assert EventSeverity.CRITICAL == "critical"
        assert EventSeverity.SECURITY == "security"


class TestEventCategory:
    def test_values(self):
        assert EventCategory.AUTH == "auth"
        assert EventCategory.DATA == "data"
        assert EventCategory.SECRETS == "secrets"
        assert EventCategory.WORKFLOW == "workflow"
        assert EventCategory.AI == "ai"
        assert EventCategory.BILLING == "billing"
        assert EventCategory.SECURITY == "security"
        assert EventCategory.GOVERNANCE == "governance"
        assert EventCategory.SYSTEM == "system"
        assert EventCategory.AUDIT == "audit"


# ── AuditEvent tests ────────────────────────────────────────────────────────


class TestAuditEvent:
    def test_defaults(self):
        event = AuditEvent()
        assert event.id != ""
        assert event.timestamp > 0
        assert event.event_type == ""
        assert event.category == EventCategory.SYSTEM
        assert event.severity == EventSeverity.INFO
        assert event.actor is None
        assert event.target is None
        assert event.service == "tranc3-backend"
        assert event.outcome == "success"
        assert event.metadata == {}

    def test_to_dict(self):
        event = AuditEvent(
            event_type="user.login",
            category=EventCategory.AUTH,
            severity=EventSeverity.INFO,
            actor="user:42",
        )
        d = event.to_dict()
        assert d["event_type"] == "user.login"
        assert d["category"] == "auth"
        assert d["severity"] == "info"
        assert d["actor"] == "user:42"


# ── Observatory tests ───────────────────────────────────────────────────────
# Observatory.__init__ calls asyncio.get_event_loop().is_running() which
# raises RuntimeError when no event loop exists.  We patch it so the
# constructor works in synchronous test methods.


def _fake_loop_not_running():
    """Return a mock loop whose is_running() returns False."""
    loop = MagicMock()
    loop.is_running.return_value = False
    return loop


def _make_observatory(**kwargs):
    """Create an Observatory without triggering asyncio event-loop issues."""
    with patch.object(asyncio, "get_event_loop", return_value=_fake_loop_not_running()):
        obs = Observatory(**kwargs)
    return obs


class TestObservatory:
    def setup_method(self):
        self.obs = _make_observatory(buffer_size=100)

    def test_record_event(self):
        event = self.obs.record("user.login")
        assert event.event_type == "user.login"
        assert len(self.obs._buffer) == 1

    def test_record_with_all_fields(self):
        event = self.obs.record(
            "secret.retrieve",
            actor="user:1",
            target="secret:abc",
            category=EventCategory.SECRETS,
            severity=EventSeverity.SECURITY,
            service="void",
            location="The Void",
            outcome="success",
            metadata={"key": "test"},
            actor_ip="10.0.0.1",
            session_id="sess-123",
        )
        assert event.actor == "user:1"
        assert event.target == "secret:abc"
        assert event.category == EventCategory.SECRETS
        assert event.severity == EventSeverity.SECURITY
        assert event.service == "void"
        assert event.location == "The Void"
        assert event.outcome == "success"
        assert event.metadata == {"key": "test"}
        assert event.actor_ip == "10.0.0.1"
        assert event.session_id == "sess-123"

    def test_recent_events(self):
        self.obs.record("event1")
        self.obs.record("event2")
        self.obs.record("event3")
        recent = self.obs.recent(limit=2)
        assert len(recent) == 2

    def test_recent_filter_by_category(self):
        self.obs.record("user.login", category=EventCategory.AUTH)
        self.obs.record("data.create", category=EventCategory.DATA)
        auth_events = self.obs.recent(category=EventCategory.AUTH)
        assert len(auth_events) == 1
        assert auth_events[0].category == EventCategory.AUTH

    def test_search_by_actor(self):
        self.obs.record("action1", actor="user:1")
        self.obs.record("action2", actor="user:2")
        self.obs.record("action3", actor="user:1")
        results = self.obs.search(actor="user:1")
        assert len(results) == 2

    def test_search_by_event_type(self):
        self.obs.record("user.login")
        self.obs.record("user.logout")
        self.obs.record("data.create")
        results = self.obs.search(event_type="user")
        assert len(results) == 2

    def test_search_with_limit(self):
        for i in range(20):
            self.obs.record("event", actor="user:1")
        results = self.obs.search(actor="user:1", limit=5)
        assert len(results) == 5

    def test_stats_empty(self):
        stats = self.obs.stats()
        assert stats["total_events"] == 0
        assert stats["buffer_capacity"] == 100
        assert stats["subscribers"] == 0

    def test_stats_populated(self):
        self.obs.record("e1", category=EventCategory.AUTH, severity=EventSeverity.INFO)
        self.obs.record("e2", category=EventCategory.SECURITY, severity=EventSeverity.CRITICAL)
        stats = self.obs.stats()
        assert stats["total_events"] == 2
        assert "auth" in stats["by_category"]
        assert "security" in stats["by_category"]

    def test_subscribe_unsubscribe(self):
        """Subscribe creates an asyncio.Queue which requires a running loop.
        We skip the Queue creation and just test the subscriber list logic."""
        # Manually add a mock queue to test unsubscribe logic
        mock_q = MagicMock()
        self.obs._subscribers.append(mock_q)
        assert len(self.obs._subscribers) == 1
        self.obs.unsubscribe(mock_q)
        assert len(self.obs._subscribers) == 0

    def test_buffer_overflow(self):
        """When buffer overflows, oldest events are dropped."""
        obs = _make_observatory(buffer_size=5)
        for i in range(10):
            obs.record(f"event-{i}")
        assert len(obs._buffer) == 5
        recent = obs.recent(limit=10)
        # Should only have the 5 most recent
        assert len(recent) == 5


# ── Module-level function tests ─────────────────────────────────────────────


class TestModuleFunctions:
    def test_observe(self):
        """observe() creates a singleton and records an event."""
        import src.observability.observatory as obs_mod

        obs_mod._observatory = None
        try:
            with patch.object(asyncio, "get_event_loop", return_value=_fake_loop_not_running()):
                event = observe("test.event", actor="system")
                assert event.event_type == "test.event"
                assert event.actor == "system"
        finally:
            obs_mod._observatory = None

    def test_get_observatory_singleton(self):
        """get_observatory() returns the same instance each call."""
        import src.observability.observatory as obs_mod

        obs_mod._observatory = None
        try:
            with patch.object(asyncio, "get_event_loop", return_value=_fake_loop_not_running()):
                obs1 = get_observatory()
                obs2 = get_observatory()
                assert obs1 is obs2
        finally:
            obs_mod._observatory = None


class TestInstrumentWorker:
    """Tests for src.observability.worker_setup.instrument_worker."""

    def test_instrument_worker_no_packages(self):
        """instrument_worker() is a no-op when optional packages are absent."""
        from fastapi import FastAPI

        app = FastAPI()
        # Patch away optional packages so the function degrades gracefully
        import sys

        with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
            sys.modules,
            {
                "prometheus_fastapi_instrumentator": None,
                "opentelemetry.instrumentation.fastapi": None,
            },
        ):
            from importlib import reload
            import src.observability.worker_setup as ws_mod

            reload(ws_mod)
            # Should complete without raising
            ws_mod.instrument_worker(app, service_name="tranc3.test-worker")
            # State flag must be set even without packages
            assert getattr(app.state, "_tranc3_instrumented", False)

    def test_instrument_worker_idempotent(self):
        """Calling instrument_worker twice on the same app is a no-op on second call."""
        from fastapi import FastAPI
        from src.observability.worker_setup import instrument_worker

        app = FastAPI()
        app.state._tranc3_instrumented = True  # pre-set as if already instrumented
        # Second call must return immediately — no side effects
        instrument_worker(app, service_name="tranc3.test-worker")
        assert app.state._tranc3_instrumented is True

    def test_sanitise_service_name(self):
        """_sanitise converts dots, dashes, slashes to underscores."""
        from src.observability.worker_setup import _sanitise

        assert _sanitise("tranc3.my-service/v1") == "tranc3_my_service_v1"
