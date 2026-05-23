# tests/test_library.py — Tests for src/library/knowledge_base.py
"""Comprehensive tests for the Library knowledge base."""

from __future__ import annotations

from src.library.knowledge_base import (
    Article,
    ArticleStatus,
    Library,
    get_library,
)


# ── Enum tests ──────────────────────────────────────────────────────────────


class TestArticleStatus:
    def test_values(self):
        assert ArticleStatus.DRAFT == "draft"
        assert ArticleStatus.PUBLISHED == "published"
        assert ArticleStatus.ARCHIVED == "archived"


# ── Article dataclass tests ────────────────────────────────────────────────


class TestArticle:
    def test_defaults(self):
        art = Article()
        assert art.id != ""
        assert art.title == ""
        assert art.body == ""
        assert art.tags == []
        assert art.status == ArticleStatus.DRAFT
        assert art.author == "system"
        assert art.created_at > 0
        assert art.updated_at > 0
        assert art.source == "internal"
        assert art.outline_id is None

    def test_to_dict(self):
        art = Article(
            title="Test Article",
            body="This is a test body that has some content in it",
            tags=["test", "unit"],
            status=ArticleStatus.PUBLISHED,
        )
        d = art.to_dict()
        assert d["title"] == "Test Article"
        assert d["body_preview"] == "This is a test body that has some content in it"
        assert d["tags"] == ["test", "unit"]
        assert d["status"] == "published"

    def test_body_preview_truncation(self):
        art = Article(body="A" * 500)
        d = art.to_dict()
        assert len(d["body_preview"]) == 200


# ── Library tests ───────────────────────────────────────────────────────────


class TestLibrary:
    def setup_method(self):
        """Create a fresh Library for each test (seeds 6 articles)."""
        self.lib = Library()

    def test_seed_articles_loaded(self):
        """Library seeds 6 platform articles on init."""
        stats = self.lib.stats()
        assert stats["total_articles"] == 6

    def test_seed_articles_all_published(self):
        stats = self.lib.stats()
        assert stats["by_status"].get("published", 0) == 6

    def test_create_article(self):
        art = self.lib.create(
            title="New Article",
            body="Article content",
            tags=["new"],
            author="tester",
        )
        assert art.title == "New Article"
        assert art.body == "Article content"
        assert art.tags == ["new"]
        assert art.author == "tester"
        assert art.status == ArticleStatus.PUBLISHED

    def test_create_article_default_tags(self):
        art = self.lib.create(title="No Tags", body="Content")
        assert art.tags == []

    def test_get_article(self):
        art = self.lib.create(title="Find Me", body="Content")
        retrieved = self.lib.get(art.id)
        assert retrieved is art

    def test_get_article_not_found(self):
        assert self.lib.get("nonexistent") is None

    def test_update_article(self):
        art = self.lib.create(title="Original", body="Content")
        updated = self.lib.update(art.id, title="Updated")
        assert updated.title == "Updated"
        assert updated.id == art.id

    def test_update_article_updates_timestamp(self):
        import time

        art = self.lib.create(title="Original", body="Content")
        old_updated = art.updated_at
        time.sleep(0.01)
        self.lib.update(art.id, title="Updated")
        assert art.updated_at >= old_updated

    def test_update_nonexistent_article(self):
        result = self.lib.update("nonexistent", title="Nope")
        assert result is None

    def test_delete_article(self):
        art = self.lib.create(title="Delete Me", body="Content", tags=["delete"])
        assert self.lib.delete(art.id)
        assert self.lib.get(art.id) is None

    def test_delete_removes_from_tag_index(self):
        art = self.lib.create(title="Tagged", body="Content", tags=["unique-tag"])
        self.lib.delete(art.id)
        by_tag = self.lib.by_tag("unique-tag")
        assert len(by_tag) == 0

    def test_delete_nonexistent_article(self):
        assert not self.lib.delete("nonexistent")

    # ── Search ──────────────────────────────────────────────────────────

    def test_search_by_title(self):
        self.lib.create(title="Deploying with Forgejo", body="Content here")
        results = self.lib.search("forgejo")
        assert len(results) >= 1

    def test_search_by_body(self):
        self.lib.create(title="Guide", body="This is about deployment procedures")
        results = self.lib.search("deployment")
        assert len(results) >= 1

    def test_search_case_insensitive(self):
        self.lib.create(title="UPPERCASE TITLE", body="content")
        results = self.lib.search("uppercase")
        assert len(results) >= 1

    def test_search_no_results(self):
        results = self.lib.search("zzz_nonexistent_topic_zzz")
        assert len(results) == 0

    def test_search_limit(self):
        for i in range(10):
            self.lib.create(title=f"Test Article {i}", body="common keyword")
        results = self.lib.search("common keyword", limit=3)
        assert len(results) == 3

    # ── Tag-based retrieval ─────────────────────────────────────────────

    def test_by_tag(self):
        self.lib.create(title="Tagged Article", body="Content", tags=["searchable"])
        results = self.lib.by_tag("searchable")
        assert len(results) >= 1

    def test_by_tag_not_found(self):
        results = self.lib.by_tag("nonexistent-tag")
        assert len(results) == 0

    def test_by_tag_limit(self):
        for i in range(10):
            self.lib.create(title=f"Article {i}", body="Content", tags=["batch"])
        results = self.lib.by_tag("batch", limit=3)
        assert len(results) == 3

    def test_seed_articles_tag_index(self):
        """Seed articles should be indexed by their tags."""
        results = self.lib.by_tag("spark")
        assert len(results) >= 1
        results = self.lib.by_tag("platform")
        assert len(results) >= 1

    # ── Recent ──────────────────────────────────────────────────────────

    def test_recent(self):
        self.lib.create(title="New", body="Content")
        recent = self.lib.recent(limit=5)
        assert len(recent) >= 1

    def test_recent_filter_by_status(self):
        self.lib.create(title="Published", body="Content")
        recent = self.lib.recent(status=ArticleStatus.PUBLISHED)
        assert len(recent) >= 1
        assert all(a.status == ArticleStatus.PUBLISHED for a in recent)

    def test_recent_drafts_empty(self):
        """No drafts in seed data or new articles (create sets PUBLISHED)."""
        recent = self.lib.recent(status=ArticleStatus.DRAFT)
        assert len(recent) == 0

    # ── Stats ───────────────────────────────────────────────────────────

    def test_stats(self):
        self.lib.create(title="Extra", body="Content", tags=["test"])
        stats = self.lib.stats()
        assert stats["total_articles"] == 7
        assert "by_status" in stats
        assert "by_source" in stats
        assert stats["tags"] > 0

    def test_stats_by_source(self):
        self.lib.create(title="Outline", body="Content", source="outline")
        stats = self.lib.stats()
        assert stats["by_source"].get("outline", 0) >= 1

    # ── Singleton ───────────────────────────────────────────────────────

    def test_get_library_singleton(self):
        lib1 = get_library()
        lib2 = get_library()
        assert lib1 is lib2


# ── Article with Outline integration tests ──────────────────────────────────


class TestArticleOutlineIntegration:
    def test_create_with_outline_id(self):
        lib = Library()
        art = lib.create(
            title="Synced Article",
            body="Content",
            source="outline",
            outline_id="outline-doc-123",
        )
        assert art.source == "outline"
        assert art.outline_id == "outline-doc-123"

    def test_to_dict_includes_outline_id(self):
        art = Article(outline_id="outline-456")
        d = art.to_dict()
        assert d["outline_id"] == "outline-456"
