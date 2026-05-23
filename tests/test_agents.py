# tests/test_agents.py — Tests for src/agents/memory_stream.py
"""Comprehensive tests for the EpisodicMemory and MemoryStream."""

from __future__ import annotations

import time

import pytest

from src.agents.memory_stream import EpisodicMemory, MemoryStream


# ── EpisodicMemory tests ────────────────────────────────────────────────────


class TestEpisodicMemory:
    def test_defaults(self):
        mem = EpisodicMemory()
        assert mem.memory_id != ""
        assert mem.content == ""
        assert mem.tags == set()
        assert mem.importance == 0.5
        assert mem.timestamp > 0
        assert mem.metadata == {}
        assert mem.access_count == 0
        assert mem.last_accessed is None

    def test_custom_values(self):
        mem = EpisodicMemory(
            content="Test memory",
            tags={"test", "unit"},
            importance=0.9,
            metadata={"key": "value"},
        )
        assert mem.content == "Test memory"
        assert mem.tags == {"test", "unit"}
        assert mem.importance == 0.9
        assert mem.metadata == {"key": "value"}

    def test_recency_score_just_created(self):
        mem = EpisodicMemory()
        score = mem.recency_score()
        assert 0.9 < score <= 1.0

    def test_recency_score_one_half_life(self):
        half_life = 3600.0
        now = time.time()
        mem = EpisodicMemory(timestamp=now - half_life)
        score = mem.recency_score(now=now)
        assert abs(score - 0.5) < 0.01

    def test_recency_score_very_old(self):
        mem = EpisodicMemory(timestamp=time.time() - 86400 * 365)  # 1 year ago
        score = mem.recency_score()
        assert score < 0.01

    def test_relevance_score_keyword_match(self):
        mem = EpisodicMemory(content="Deployed the application to production")
        score = mem.relevance_score("deployed production")
        assert score > 0

    def test_relevance_score_no_match(self):
        mem = EpisodicMemory(content="The weather is nice today")
        score = mem.relevance_score("deployed production")
        assert score == 0.0

    def test_relevance_score_tag_match(self):
        mem = EpisodicMemory(content="Test", tags={"code", "review"})
        score = mem.relevance_score("", query_tags={"code"})
        assert score > 0

    def test_relevance_score_empty_query(self):
        mem = EpisodicMemory(content="Some content")
        score = mem.relevance_score("")
        assert score == 0.0

    def test_combined_score(self):
        mem = EpisodicMemory(content="deploy code", importance=0.8)
        score = mem.combined_score(query="deploy")
        assert 0 < score <= 1.0

    def test_combined_score_zero_weights(self):
        mem = EpisodicMemory(content="test", importance=0.5)
        score = mem.combined_score(w_recency=0, w_relevance=0, w_importance=0)
        assert score == 0.0

    def test_touch(self):
        mem = EpisodicMemory()
        assert mem.access_count == 0
        mem.touch()
        assert mem.access_count == 1
        assert mem.last_accessed is not None

    def test_to_dict(self):
        mem = EpisodicMemory(content="test", tags={"a", "b"}, importance=0.7)
        d = mem.to_dict()
        assert d["content"] == "test"
        assert d["importance"] == 0.7
        assert sorted(d["tags"]) == ["a", "b"]
        assert "recency" in d


# ── MemoryStream tests ──────────────────────────────────────────────────────


class TestMemoryStream:
    @pytest.fixture
    def stream(self):
        return MemoryStream(capacity=10)

    def test_capacity_property(self, stream):
        assert stream.capacity == 10

    def test_count_empty(self, stream):
        assert stream.count == 0

    @pytest.mark.asyncio
    async def test_add(self, stream):
        mid = await stream.add("Test memory", importance=0.5)
        assert mid != ""
        assert stream.count == 1

    @pytest.mark.asyncio
    async def test_add_with_tags(self, stream):
        mid = await stream.add("Test", tags={"code"}, importance=0.7)
        mem = await stream.get(mid)
        assert mem is not None
        assert "code" in mem.tags

    @pytest.mark.asyncio
    async def test_importance_clamping(self, stream):
        mid = await stream.add("High importance", importance=5.0)
        mem = await stream.get(mid)
        assert mem.importance == 1.0

        mid2 = await stream.add("Low importance", importance=-1.0)
        mem2 = await stream.get(mid2)
        assert mem2.importance == 0.0

    @pytest.mark.asyncio
    async def test_remove(self, stream):
        mid = await stream.add("To remove")
        assert await stream.remove(mid)
        assert stream.count == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, stream):
        assert not await stream.remove("nonexistent")

    @pytest.mark.asyncio
    async def test_retrieve_by_query(self, stream):
        await stream.add("Deploy code to production", importance=0.8)
        await stream.add("Weather is sunny", importance=0.3)
        results = await stream.retrieve("deploy", top_k=5)
        assert len(results) >= 1
        assert "deploy" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_retrieve_by_tags(self, stream):
        await stream.add("Code review done", tags={"code"}, importance=0.6)
        await stream.add("Lunch break", tags={"personal"}, importance=0.3)
        results = await stream.get_by_tags({"code"})
        assert len(results) == 1
        assert "code" in results[0].tags

    @pytest.mark.asyncio
    async def test_retrieve_by_time_range(self, stream):
        now = time.time()
        await stream.add("Recent memory", importance=0.5)
        results = await stream.get_by_time_range(start=now - 10, end=now + 10)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_recent(self, stream):
        for i in range(5):
            await stream.add(f"Memory {i}", importance=0.5)
        recent = await stream.get_recent(count=3)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_get_by_id(self, stream):
        mid = await stream.add("Specific memory")
        mem = await stream.get(mid)
        assert mem is not None
        assert mem.content == "Specific memory"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, stream):
        assert await stream.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_eviction_on_capacity(self, stream):
        """When capacity is exceeded, oldest low-importance memories are evicted."""
        for i in range(15):  # capacity is 10
            await stream.add(f"Memory {i}", importance=0.1 + i * 0.01)
        assert stream.count <= 10

    @pytest.mark.asyncio
    async def test_reflect(self, stream):
        await stream.add("Important event", importance=0.9)
        await stream.add("Trivial event", importance=0.1)
        reflections = await stream.reflect(top_k=5)
        assert len(reflections) >= 1
        assert "content" in reflections[0]

    @pytest.mark.asyncio
    async def test_get_summary_empty(self, stream):
        summary = await stream.get_summary()
        assert summary["total"] == 0
        assert summary["utilization"] == 0.0

    @pytest.mark.asyncio
    async def test_get_summary_populated(self, stream):
        await stream.add("Test memory", tags={"test"}, importance=0.6)
        summary = await stream.get_summary()
        assert summary["total"] == 1
        assert summary["utilization"] > 0
        assert "test" in summary["tag_counts"]

    @pytest.mark.asyncio
    async def test_get_all(self, stream):
        await stream.add("First")
        await stream.add("Second")
        all_memories = await stream.get_all()
        assert len(all_memories) == 2

    @pytest.mark.asyncio
    async def test_retrieve_touches_access_count(self, stream):
        mid = await stream.add("Access test", importance=0.5)
        mem = await stream.get(mid)
        assert mem.access_count == 0
        await stream.retrieve("Access", top_k=5)
        mem = await stream.get(mid)
        assert mem.access_count >= 1
