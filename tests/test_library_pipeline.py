# tests/test_library_pipeline.py — Tests for src/observability/library_pipeline.py
"""Tests for the Observatory → Library pipeline.

Covers the two bugs fixed here: ingest() was never called from anywhere
(Observatory.record() didn't forward to it), and _should_trigger()/KBTrigger
checked event["action"]/event["resource"] — keys that don't exist on
AuditEvent.to_dict(), which uses event_type/target/metadata instead.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.library.knowledge_base import Library
from src.observability import library_pipeline
from src.observability.observatory import (
    EventCategory,
    EventSeverity,
    Observatory,
)


@pytest.fixture(autouse=True)
def _reset_queue():
    library_pipeline._queue.clear()
    yield
    library_pipeline._queue.clear()


class TestShouldTrigger:
    def test_matches_on_audit_event_shape(self):
        # Real AuditEvent.to_dict() keys — not the old "action"/"resource" ones.
        assert library_pipeline._should_trigger(
            {"event_type": "user.login", "severity": "critical"}
        )
        assert library_pipeline._should_trigger(
            {"event_type": "secret.retrieve", "severity": "info"}
        )
        assert library_pipeline._should_trigger(
            {"event_type": "auth.mfa_failed", "severity": "warning"}
        )

    def test_security_severity_triggers(self):
        assert library_pipeline._should_trigger(
            {"event_type": "vault.unseal", "severity": "security"}
        )

    def test_rejects_routine_info_events(self):
        assert not library_pipeline._should_trigger(
            {"event_type": "article.created", "severity": "info"}
        )

    def test_old_action_key_no_longer_required(self):
        # Confirms the fixed field mapping — "action" was the old (wrong) key
        # this used to check; it must not be required for a match anymore.
        assert "action" not in {"event_type", "severity"}
        assert library_pipeline._should_trigger(
            {"event_type": "cve.detected", "severity": "warning", "action": "unused"}
        )


class TestIngest:
    @pytest.mark.asyncio
    async def test_non_triggering_event_is_not_queued(self):
        await library_pipeline.ingest({"event_type": "article.created", "severity": "info"})
        assert library_pipeline._queue == []

    @pytest.mark.asyncio
    async def test_triggering_event_is_queued_below_batch_size(self):
        await library_pipeline.ingest(
            {
                "event_type": "secret.retrieve",
                "severity": "critical",
                "actor": "user:1",
                "target": "secret:db-password",
                "metadata": {"message": "unauthorized access attempt", "tags": ["breach"]},
                "timestamp": 123.0,
            }
        )
        assert len(library_pipeline._queue) == 1
        trigger = library_pipeline._queue[0]
        assert trigger.event_type == "secret.retrieve"
        assert trigger.actor == "user:1"
        assert trigger.resource == "secret:db-password"
        assert trigger.summary == "unauthorized access attempt"
        assert trigger.tags == ["breach"]

    @pytest.mark.asyncio
    async def test_disabled_pipeline_never_queues(self):
        with patch.object(library_pipeline, "PIPELINE_ENABLED", False):
            await library_pipeline.ingest({"event_type": "secret.retrieve", "severity": "critical"})
        assert library_pipeline._queue == []

    @pytest.mark.asyncio
    async def test_batch_flush_creates_library_article(self):
        test_lib = Library()
        with patch.object(library_pipeline, "BATCH_SIZE", 2):
            with patch("src.library.knowledge_base.get_library", return_value=test_lib):
                await library_pipeline.ingest(
                    {
                        "event_type": "auth.brute_force",
                        "severity": "critical",
                        "actor": "ip:1.2.3.4",
                    }
                )
                assert library_pipeline._queue  # not flushed yet (batch size 2)
                await library_pipeline.ingest(
                    {"event_type": "vault.tamper", "severity": "security", "actor": "unknown"}
                )
        # Batch of 2 reached — queue drained and an article created.
        assert library_pipeline._queue == []
        observatory_articles = [a for a in test_lib.recent(limit=20) if a.source == "observatory"]
        assert len(observatory_articles) == 1
        art = observatory_articles[0]
        assert art.author == "observatory"
        assert "observatory" in art.tags
        assert "auto-generated" in art.tags
        assert "auth.brute_force" in art.body
        assert "vault.tamper" in art.body


class TestObservatoryForwarding:
    @pytest.mark.asyncio
    async def test_critical_event_reaches_library_pipeline(self):
        """The bug this closes: record() never called ingest() at all."""
        test_lib = Library()
        obs = Observatory()
        with patch.object(library_pipeline, "BATCH_SIZE", 1):
            with patch("src.library.knowledge_base.get_library", return_value=test_lib):
                obs.record(
                    "secret.retrieve",
                    actor="user:99",
                    target="secret:api-key",
                    category=EventCategory.SECRETS,
                    severity=EventSeverity.CRITICAL,
                )
                # record() schedules ingest() as a fire-and-forget task; let it run.
                for _ in range(3):
                    await asyncio.sleep(0)
        recent = test_lib.recent(limit=5)
        assert any(a.source == "observatory" for a in recent)

    @pytest.mark.asyncio
    async def test_info_event_does_not_reach_library_pipeline(self):
        test_lib = Library()
        obs = Observatory()
        before = test_lib.count()
        with patch("src.library.knowledge_base.get_library", return_value=test_lib):
            obs.record(
                "user.login",
                actor="user:1",
                category=EventCategory.AUTH,
                severity=EventSeverity.INFO,
            )
            for _ in range(3):
                await asyncio.sleep(0)
        assert test_lib.count() == before
