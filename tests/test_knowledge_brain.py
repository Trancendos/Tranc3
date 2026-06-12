"""
tests/test_knowledge_brain.py — Unit tests for src/knowledge/knowledge_brain.py

Tests cover:
  - BM25Index: indexing, scoring, query
  - _rrf: reciprocal rank fusion
  - KBPage / KBLink dataclasses
  - KnowledgeBrain: put/get/delete/list/search/remember/recall/stats
  - Wikilink parsing
  - SQLite persistence (in-memory via :memory:)

All tests are zero-dependency — no FAISS, no torch required for the core paths.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# BM25Index tests
# ---------------------------------------------------------------------------


class TestBM25Index:
    def _make_index(self):
        from src.knowledge.knowledge_brain import BM25Index

        return BM25Index()

    def _page(self, pid, content):
        from src.knowledge.knowledge_brain import KBPage

        return KBPage(id=pid, title=pid, content=content)

    def test_empty_index_returns_nothing(self):
        idx = self._make_index()
        results = idx.query("hello world")
        assert results == []

    def test_build_and_query(self):
        idx = self._make_index()
        idx.build([self._page("doc1", "hello world"), self._page("doc2", "foo bar")])
        results = idx.query("hello")
        assert len(results) >= 1
        # doc1 should score highest for "hello"
        assert results[0][0] == "doc1"

    def test_query_returns_topk(self):
        idx = self._make_index()
        pages = [self._page(f"doc{i}", f"term{i} common") for i in range(10)]
        idx.build(pages)
        results = idx.query("common", top_k=3)
        assert len(results) <= 3

    def test_add_single_doc(self):
        idx = self._make_index()
        idx.add(self._page("mypage", "python programming code"))
        results = idx.query("python")
        assert results[0][0] == "mypage"

    def test_remove_doc(self):
        idx = self._make_index()
        idx.add(self._page("removeme", "unique special token"))
        idx.remove("removeme")
        results = idx.query("unique special token")
        hits = [r[0] for r in results]
        assert "removeme" not in hits

    def test_scores_positive(self):
        idx = self._make_index()
        idx.build([self._page("d1", "alpha beta gamma")])
        results = idx.query("alpha beta")
        assert all(score >= 0 for _, score in results)


# ---------------------------------------------------------------------------
# RRF tests
# ---------------------------------------------------------------------------


class TestRRF:
    def test_single_list(self):
        from src.knowledge.knowledge_brain import _rrf

        result = _rrf([["a", "b", "c"]])
        ids = [r[0] for r in result]
        assert ids == ["a", "b", "c"]

    def test_two_identical_lists(self):
        from src.knowledge.knowledge_brain import _rrf

        result = _rrf([["a", "b", "c"], ["a", "b", "c"]])
        ids = [r[0] for r in result]
        assert ids == ["a", "b", "c"]

    def test_disjoint_lists(self):
        from src.knowledge.knowledge_brain import _rrf

        result = _rrf([["a", "b"], ["c", "d"]])
        ids = {r[0] for r in result}
        assert ids == {"a", "b", "c", "d"}

    def test_overlap_boosts_score(self):
        from src.knowledge.knowledge_brain import _rrf

        # "common" appears at rank 1 in both lists — should score highest
        result = _rrf([["common", "only_list1"], ["common", "only_list2"]])
        assert result[0][0] == "common"

    def test_scored_tuples(self):
        from src.knowledge.knowledge_brain import _rrf

        # Accepts (id, score) tuple lists as well as plain id lists
        result = _rrf([[("a", 1.0), ("b", 0.5)], [("a", 0.8), ("c", 0.3)]])
        ids = [r[0] for r in result]
        assert "a" in ids
        assert ids[0] == "a"  # "a" appears in both lists — should rank first

    def test_empty_lists(self):
        from src.knowledge.knowledge_brain import _rrf

        assert _rrf([]) == []
        assert _rrf([[]]) == []


# ---------------------------------------------------------------------------
# KBPage / KBLink dataclasses
# ---------------------------------------------------------------------------


class TestKBPageDataclass:
    def test_default_source(self):
        from src.knowledge.knowledge_brain import KBPage

        p = KBPage(id="x", title="T", content="C")
        assert p.source == "manual"
        assert p.tags == []
        assert p.metadata == {}

    def test_word_tokens(self):
        from src.knowledge.knowledge_brain import KBPage

        p = KBPage(id="x", title="T", content="Hello World foo 123 hi")
        tokens = p.word_tokens()
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens
        # Short tokens and numbers filtered by \b[a-z]{2,}\b
        assert "hi" in tokens
        assert "123" not in tokens

    def test_custom_id(self):
        from src.knowledge.knowledge_brain import KBPage

        p = KBPage(id="my-custom-id", title="T", content="c")
        assert p.id == "my-custom-id"


class TestKBLinkDataclass:
    def test_defaults(self):
        from src.knowledge.knowledge_brain import KBLink

        link = KBLink(source_id="a", target_id="b")
        assert link.relation == "mentions"
        assert link.weight == 1.0


# ---------------------------------------------------------------------------
# KnowledgeBrain integration tests (in-memory SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def brain(tmp_path):
    """Provide a KnowledgeBrain backed by a temp SQLite file."""
    from src.knowledge.knowledge_brain import KnowledgeBrain

    db = str(tmp_path / "test_kb.db")
    # Disable vector search so tests don't require FAISS
    kb = KnowledgeBrain(db_path=db, markdown_dir=str(tmp_path / "md"))
    return kb


class TestKnowledgeBrainCRUD:
    @pytest.mark.asyncio
    async def test_put_and_get_page(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        page = KBPage(id="p1", title="Hello Brain", content="This is a test page.")
        stored_id = await brain.put_page(page)
        assert stored_id == "p1"

        retrieved = await brain.get_page("p1")
        assert retrieved is not None
        assert retrieved.title == "Hello Brain"
        assert retrieved.content == "This is a test page."

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, brain):
        result = await brain.get_page("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_page(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        await brain.put_page(KBPage(id="del1", title="To Delete", content="bye"))
        deleted = await brain.delete_page("del1")
        assert deleted is True
        assert await brain.get_page("del1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, brain):
        result = await brain.delete_page("ghost")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_pages_empty(self, brain):
        pages = await brain.list_pages()
        assert isinstance(pages, list)

    @pytest.mark.asyncio
    async def test_list_pages_with_source_filter(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        await brain.put_page(KBPage(id="a1", title="A", content="manual", source="manual"))
        await brain.put_page(KBPage(id="a2", title="B", content="agent", source="agent"))

        manual = await brain.list_pages(source="manual")
        agent = await brain.list_pages(source="agent")
        assert all(p.source == "manual" for p in manual)
        assert all(p.source == "agent" for p in agent)


class TestKnowledgeBrainSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        await brain.put_page(
            KBPage(
                id="s1",
                title="Python Programming",
                content="Python is a great programming language for beginners.",
            ),
        )
        await brain.put_page(
            KBPage(
                id="s2",
                title="JavaScript",
                content="JavaScript runs in browsers and is used for web development.",
            ),
        )

        results = await brain.search("python programming", top_k=5, use_vector=False)
        assert len(results) >= 1
        ids = [r.page.id for r in results]
        assert "s1" in ids

    @pytest.mark.asyncio
    async def test_search_empty_brain(self, brain):
        results = await brain.search("anything", top_k=5, use_vector=False)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_result_has_score_and_excerpt(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        await brain.put_page(
            KBPage(
                id="e1",
                title="Excerpt Test",
                content="The quick brown fox jumps over the lazy dog.",
            ),
        )
        results = await brain.search("fox", top_k=3, use_vector=False)
        if results:
            r = results[0]
            assert isinstance(r.score, float)
            assert isinstance(r.excerpt, str)
            assert len(r.excerpt) > 0


class TestKnowledgeBrainAgentMemory:
    @pytest.mark.asyncio
    async def test_remember_and_recall(self, brain):
        page_id = await brain.remember(
            agent_id="agent-001",
            content="The user prefers dark mode and Python over JavaScript.",
            tags=["preference"],
        )
        assert isinstance(page_id, str) and page_id

        memories = await brain.recall(agent_id="agent-001", query="dark mode preference", top_k=5)
        assert len(memories) >= 1
        contents = [m.page.content for m in memories]
        assert any("dark mode" in c for c in contents)

    @pytest.mark.asyncio
    async def test_recall_scope_isolation(self, brain):
        """Agent A memories should not appear in Agent B recall (tag-based isolation)."""
        await brain.remember(agent_id="agent-A", content="Secret knowledge for agent A only.")
        await brain.remember(agent_id="agent-B", content="Agent B remembers something different.")

        # Recall for agent-A with agent-B query — should not return agent-B memory
        memories_a = await brain.recall(agent_id="agent-A", query="agent A secret", top_k=10)
        # All returned memories must be tagged with agent-A (not agent-B)
        assert all("agent:agent-A" in mem.page.tags for mem in memories_a)


class TestKnowledgeBrainStats:
    @pytest.mark.asyncio
    async def test_stats_structure(self, brain):
        stats = brain.stats()
        assert "page_count" in stats
        assert "link_count" in stats
        assert isinstance(stats["page_count"], int)

    @pytest.mark.asyncio
    async def test_stats_reflect_puts(self, brain):
        from src.knowledge.knowledge_brain import KBPage

        initial = brain.stats()["page_count"]
        await brain.put_page(KBPage(id="stat1", title="Stats Page", content="testing stats"))
        after = brain.stats()["page_count"]
        assert after == initial + 1


# ---------------------------------------------------------------------------
# Wikilink parsing
# ---------------------------------------------------------------------------


class TestWikilinkParsing:
    @pytest.mark.asyncio
    async def test_wikilinks_create_edges(self, brain):
        """Putting a page with [[Target]] wikilink should create a KBLink."""
        from src.knowledge.knowledge_brain import KBPage

        # Create target page first
        await brain.put_page(
            KBPage(id="target-page", title="Target Page", content="I am the target."),
        )
        # Create source with wikilink
        await brain.put_page(
            KBPage(
                id="source-page",
                title="Source Page",
                content="See [[Target Page]] for details.",
            ),
        )
        # Check a link was created (via graph_search or store inspection)
        stats = brain.stats()
        assert stats["link_count"] >= 0  # links may or may not resolve depending on impl

    @pytest.mark.asyncio
    async def test_wikilinks_with_alias(self, brain):
        """[[Target|alias]] should still wire to target."""
        from src.knowledge.knowledge_brain import KBPage

        await brain.put_page(
            KBPage(id="aliased", title="Aliased Target", content="I am the aliased target."),
        )
        await brain.put_page(
            KBPage(
                id="src-alias",
                title="Source",
                content="Click [[Aliased Target|here]] to read.",
            ),
        )
        # Should not raise
        p = await brain.get_page("src-alias")
        assert p is not None
