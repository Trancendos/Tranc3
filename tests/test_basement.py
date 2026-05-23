# tests/test_basement.py
# Tests for src/basement/archive.py
# Covers ArchiveSource, ArchiveRecord, Basement (ingest, search, stats),
# and the module-level get_basement() singleton.

from __future__ import annotations

from unittest.mock import MagicMock

from src.basement.archive import (
    ArchiveRecord,
    ArchiveSource,
    Basement,
    get_basement,
)


# ── ArchiveSource enum ───────────────────────────────────────────────


class TestArchiveSource:
    def test_enum_values(self):
        assert ArchiveSource.OBSERVATORY.value == "observatory"
        assert ArchiveSource.LIBRARY.value == "library"
        assert ArchiveSource.WORKFLOW.value == "workflow"
        assert ArchiveSource.INFERENCE.value == "inference"
        assert ArchiveSource.SECURITY.value == "security"

    def test_enum_is_str(self):
        assert isinstance(ArchiveSource.SECURITY, str)


# ── ArchiveRecord ────────────────────────────────────────────────────


class TestArchiveRecord:
    def test_defaults(self):
        rec = ArchiveRecord()
        assert rec.id != ""
        assert rec.source == ArchiveSource.OBSERVATORY
        assert rec.event_type == ""
        assert rec.content == ""
        assert rec.metadata == {}
        assert rec.embedding is None
        assert rec.retained is False

    def test_to_dict(self):
        rec = ArchiveRecord(
            source=ArchiveSource.SECURITY,
            event_type="alert",
            content="Something happened" * 20,  # long enough for preview
            metadata={"actor": "admin"},
            retained=True,
        )
        d = rec.to_dict()
        assert d["source"] == "security"
        assert d["event_type"] == "alert"
        assert "content_preview" in d
        assert len(d["content_preview"]) <= 200
        assert d["metadata"] == {"actor": "admin"}
        assert d["retained"] is True

    def test_custom_fields(self):
        rec = ArchiveRecord(
            id="custom-id",
            timestamp=12345.0,
            source=ArchiveSource.LIBRARY,
            event_type="retired",
            content="Old article",
            metadata={"key": "val"},
        )
        assert rec.id == "custom-id"
        assert rec.timestamp == 12345.0
        assert rec.source == ArchiveSource.LIBRARY


# ── Basement core operations ────────────────────────────────────────


class TestBasement:
    def setup_method(self):
        self.basement = Basement()

    def test_ingest_creates_record(self):
        rec = self.basement.ingest(
            content="Test event",
            source=ArchiveSource.OBSERVATORY,
            event_type="audit",
        )
        assert isinstance(rec, ArchiveRecord)
        assert rec.content == "Test event"
        assert rec.source == ArchiveSource.OBSERVATORY
        assert rec.event_type == "audit"

    def test_ingest_security_auto_retained(self):
        rec = self.basement.ingest(
            content="Security alert",
            source=ArchiveSource.SECURITY,
        )
        assert rec.retained is True

    def test_ingest_security_event_type_auto_retained(self):
        rec = self.basement.ingest(
            content="Something",
            event_type="security_breach",
        )
        assert rec.retained is True

    def test_ingest_non_security_not_retained(self):
        rec = self.basement.ingest(
            content="Normal event",
            source=ArchiveSource.OBSERVATORY,
        )
        assert rec.retained is False

    def test_ingest_with_metadata(self):
        rec = self.basement.ingest(
            content="Event",
            metadata={"key": "value"},
        )
        assert rec.metadata == {"key": "value"}

    def test_ingest_retained_flag_preserved(self):
        rec = self.basement.ingest(
            content="Keep forever",
            retained=True,
        )
        assert rec.retained is True

    def test_get_existing_record(self):
        rec = self.basement.ingest(content="Find me")
        fetched = self.basement.get(rec.id)
        assert fetched is rec

    def test_get_nonexistent_returns_none(self):
        assert self.basement.get("no-such-id") is None


# ── Basement search ─────────────────────────────────────────────────


class TestBasementSearch:
    def setup_method(self):
        self.basement = Basement()

    def test_keyword_search_finds_match(self):
        self.basement.ingest(content="database connection error", event_type="error")
        self.basement.ingest(content="user logged in successfully", event_type="auth")
        results = self.basement.search("database error")
        assert len(results) >= 1
        assert any("database" in r[0].content for r in results)

    def test_keyword_search_no_match(self):
        self.basement.ingest(content="hello world")
        results = self.basement.search("quantum")
        assert len(results) == 0

    def test_keyword_search_top_k(self):
        for i in range(10):
            self.basement.ingest(content=f"database event {i}", event_type="db")
        results = self.basement.search("database", top_k=3)
        assert len(results) <= 3

    def test_keyword_search_scores(self):
        self.basement.ingest(content="database connection error", event_type="db_error")
        results = self.basement.search("database")
        assert len(results) >= 1
        assert results[0][1] > 0.0  # score > 0

    def test_search_uses_keyword_when_no_faiss(self):
        # In test env, FAISS is typically not available
        self.basement.ingest(content="test query match")
        results = self.basement.search("query")
        assert len(results) >= 1


# ── Basement by_source / recent ──────────────────────────────────────


class TestBasementQuery:
    def setup_method(self):
        self.basement = Basement()

    def test_by_source(self):
        self.basement.ingest(content="obs event", source=ArchiveSource.OBSERVATORY)
        self.basement.ingest(content="sec event", source=ArchiveSource.SECURITY)
        self.basement.ingest(content="lib event", source=ArchiveSource.LIBRARY)
        obs_records = self.basement.by_source(ArchiveSource.OBSERVATORY)
        assert len(obs_records) == 1
        assert obs_records[0].source == ArchiveSource.OBSERVATORY

    def test_by_source_empty(self):
        records = self.basement.by_source(ArchiveSource.WORKFLOW)
        assert records == []

    def test_by_source_limit(self):
        for i in range(5):
            self.basement.ingest(content=f"obs {i}", source=ArchiveSource.OBSERVATORY)
        records = self.basement.by_source(ArchiveSource.OBSERVATORY, limit=2)
        assert len(records) == 2

    def test_recent(self):
        self.basement.ingest(content="first")
        self.basement.ingest(content="second")
        self.basement.ingest(content="third")
        records = self.basement.recent(limit=2)
        assert len(records) == 2

    def test_recent_with_source_filter(self):
        self.basement.ingest(content="a", source=ArchiveSource.OBSERVATORY)
        self.basement.ingest(content="b", source=ArchiveSource.SECURITY)
        records = self.basement.recent(limit=10, source=ArchiveSource.SECURITY)
        assert len(records) == 1
        assert records[0].source == ArchiveSource.SECURITY

    def test_recent_returns_newest_first(self):
        rec1 = self.basement.ingest(content="old")
        rec1.timestamp = 100.0
        rec2 = self.basement.ingest(content="new")
        rec2.timestamp = 200.0
        records = self.basement.recent(limit=10)
        assert records[0].content == "new"
        assert records[1].content == "old"


# ── Basement stats ───────────────────────────────────────────────────


class TestBasementStats:
    def setup_method(self):
        self.basement = Basement()

    def test_stats_empty(self):
        s = self.basement.stats()
        assert s["total_records"] == 0
        assert s["retained_records"] == 0
        assert s["by_source"] == {}
        assert s["faiss_indexed"] == 0
        assert s["vector_search"] is False

    def test_stats_with_records(self):
        self.basement.ingest(content="obs", source=ArchiveSource.OBSERVATORY)
        self.basement.ingest(content="sec", source=ArchiveSource.SECURITY)
        s = self.basement.stats()
        assert s["total_records"] == 2
        assert s["retained_records"] == 1  # SECURITY auto-retained
        assert "observatory" in s["by_source"]
        assert "security" in s["by_source"]


# ── Basement ingest_observatory_event ────────────────────────────────


class TestBasementObservatoryEvent:
    def setup_method(self):
        self.basement = Basement()

    def test_ingest_observatory_event_normal(self):
        event = MagicMock()
        event.event_type = "user_action"
        event.actor = "user1"
        event.target = "resource1"
        event.outcome = "success"
        event.service = "api"
        rec = self.basement.ingest_observatory_event(event)
        assert "user_action" in rec.content
        assert rec.source == ArchiveSource.OBSERVATORY

    def test_ingest_observatory_event_critical(self):
        event = MagicMock()
        event.event_type = "security_breach"
        event.actor = "attacker"
        event.target = "system"
        event.outcome = "failure"
        event.service = "auth"
        event.severity = "critical"
        rec = self.basement.ingest_observatory_event(event)
        assert rec.retained is True
        assert rec.source == ArchiveSource.SECURITY

    def test_ingest_observatory_event_security_severity(self):
        event = MagicMock()
        event.event_type = "login"
        event.actor = "admin"
        event.target = "panel"
        event.outcome = "success"
        event.service = "auth"
        event.severity = "security"
        rec = self.basement.ingest_observatory_event(event)
        assert rec.retained is True


# ── get_basement() singleton ────────────────────────────────────────


class TestGetBasement:
    def setup_method(self):
        # Reset the module-level singleton before each test
        import src.basement.archive as _mod

        _mod._basement = None

    def test_get_basement_creates_instance(self):
        b = get_basement()
        assert isinstance(b, Basement)

    def test_get_basement_returns_same_instance(self):
        b1 = get_basement()
        b2 = get_basement()
        assert b1 is b2

    def teardown_method(self):
        import src.basement.archive as _mod

        _mod._basement = None
