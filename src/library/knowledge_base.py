# src/library/knowledge_base.py
# The Library — structured knowledge base for the Trancendos platform.
#
# Provides:
#   - Article CRUD with full-text indexing
#   - Tag-based retrieval
#   - Integration hooks for Outline (self-hosted wiki)
#   - Triggered by Observatory audit events (e.g. new workflow runs → KB article)
#   - Feeds The Spark's RAG pipeline via The Basement's FAISS index

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class ArticleStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class Article:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    body: str = ""
    tags: List[str] = field(default_factory=list)
    status: ArticleStatus = ArticleStatus.DRAFT
    author: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    source: str = "internal"  # "internal" | "outline" | "observatory"
    outline_id: Optional[str] = None  # ID in external Outline instance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body_preview": self.body[:200],
            "tags": self.tags,
            "status": self.status.value,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
            "outline_id": self.outline_id,
        }


class Library:
    """
    The Library — knowledge base and documentation store.

    Stores articles in-process (with optional Outline sync).
    The RAG pipeline in The Basement consumes articles via embed_article().
    """

    def __init__(self):
        self._articles: Dict[str, Article] = {}
        self._tag_index: Dict[str, List[str]] = {}  # tag → [article_id]
        self._seed_platform_articles()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        author: str = "system",
        source: str = "internal",
        outline_id: Optional[str] = None,
    ) -> Article:
        art = Article(
            title=title,
            body=body,
            tags=tags or [],
            author=author,
            source=source,
            outline_id=outline_id,
            status=ArticleStatus.PUBLISHED,
        )
        self._articles[art.id] = art
        for tag in art.tags:
            self._tag_index.setdefault(tag, []).append(art.id)
        logger.debug(
            "library: created article id=%s title=%r",
            art.id,
            sanitize_for_log(title),
        )  # codeql[py/cleartext-logging]
        self._emit_observatory_event(art, "article.created")
        return art

    def get(self, article_id: str) -> Optional[Article]:
        return self._articles.get(article_id)

    def update(self, article_id: str, **kwargs) -> Optional[Article]:
        art = self._articles.get(article_id)
        if not art:
            return None
        for k, v in kwargs.items():
            if hasattr(art, k):
                setattr(art, k, v)
        art.updated_at = time.time()
        self._emit_observatory_event(art, "article.updated")
        return art

    def delete(self, article_id: str) -> bool:
        art = self._articles.pop(article_id, None)
        if not art:
            return False
        for tag in art.tags:
            ids = self._tag_index.get(tag, [])
            if article_id in ids:
                ids.remove(article_id)
        self._emit_observatory_event(art, "article.deleted")
        return True

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> List[Article]:
        """Simple in-process substring search. Replaced by FAISS for semantic."""
        q = query.lower()
        results = [
            a for a in self._articles.values() if q in a.title.lower() or q in a.body.lower()
        ]
        return sorted(results, key=lambda a: a.updated_at, reverse=True)[:limit]

    def by_tag(self, tag: str, limit: int = 50) -> List[Article]:
        ids = self._tag_index.get(tag, [])
        return [self._articles[i] for i in ids[:limit] if i in self._articles]

    def recent(self, limit: int = 20, status: Optional[ArticleStatus] = None) -> List[Article]:
        articles = list(self._articles.values())
        if status:
            articles = [a for a in articles if a.status == status]
        return sorted(articles, key=lambda a: a.updated_at, reverse=True)[:limit]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        total = len(self._articles)
        by_status = {}
        by_source = {}
        for art in self._articles.values():
            by_status[art.status.value] = by_status.get(art.status.value, 0) + 1
            by_source[art.source] = by_source.get(art.source, 0) + 1
        return {
            "total_articles": total,
            "by_status": by_status,
            "by_source": by_source,
            "tags": len(self._tag_index),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emit_observatory_event(self, art: Article, event_type: str) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                event_type,
                actor=art.author,
                target=f"article:{art.id}",
                category=EventCategory.DATA,
                service="library",
                metadata={"title": art.title, "tags": art.tags},
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream

        # Also emit directly to the EventBus for search-service indexing
        try:
            from src.event_bus import get_event_bus  # noqa: PLC0415

            bus = get_event_bus()
            bus.emit_async(
                event_type=event_type,
                data={
                    "id": art.id,
                    "title": art.title,
                    "body": art.body,
                    "tags": art.tags,
                    "author": art.author,
                    "source": art.source,
                    "status": art.status.value,
                },
                source="library",
            )
        except Exception:
            pass  # nosec B110 — graceful degradation

    def _seed_platform_articles(self) -> None:
        """Seed initial platform documentation articles."""
        seed_articles = [
            {
                "title": "The Spark — MCP Server Guide",
                "body": (
                    "The Spark is Trancendos's MCP (Model Context Protocol) server, "
                    "exposing all platform tools as JSON-RPC 2.0 endpoints. "
                    "Routes: /mcp/rpc (POST), /mcp/sse (SSE), /mcp/tools (GET), "
                    "/mcp/health (GET), /mcp/grid/status (GET)."
                ),
                "tags": ["spark", "mcp", "tools", "platform"],
            },
            {
                "title": "The Digital Grid — Workflow Execution",
                "body": (
                    "The Digital Grid executes DAG-based workflows using topological BFS. "
                    "WorkflowBuilder provides a fluent DSL for building pipelines. "
                    "Events are forwarded to The Spark's SSE bus on first client connect."
                ),
                "tags": ["grid", "workflow", "dag", "platform"],
            },
            {
                "title": "The Observatory — Audit Log",
                "body": (
                    "The Observatory records every write operation across the platform. "
                    "Events are stored in a 10k-event ring buffer and streamed via SSE "
                    "at /observatory/sse. Query recent events at /observatory/recent."
                ),
                "tags": ["observatory", "audit", "observability", "platform"],
            },
            {
                "title": "The Void — Secrets Vault",
                "body": (
                    "The Void is a Cloudflare Worker providing AES-GCM encrypted secrets storage. "
                    "Keys are derived via PBKDF2 (100k iterations, SHA-256). "
                    "Storage: Cloudflare D1 for metadata + payload; R2 optional for large secrets. "
                    "Routes: GET /health, POST /secrets, POST /secrets/retrieve."
                ),
                "tags": ["void", "secrets", "security", "cloudflare", "platform"],
            },
            {
                "title": "The Workshop — CI/CD with Forgejo",
                "body": (
                    "The Workshop is the Trancendos self-hosted CI/CD system powered by Forgejo "
                    "(a lightweight Gitea fork). It runs at trancendos.com/the-workshop. "
                    "Workflow files live in .forgejo/workflows/. "
                    "IMPORTANT: Never use GitHub Actions — all CI/CD goes through The Workshop."
                ),
                "tags": ["workshop", "ci-cd", "forgejo", "devops", "platform"],
            },
            {
                "title": "Zero-Cost Architecture",
                "body": (
                    "Trancendos operates on a strict zero-cost model. All services must stay "
                    "within free tiers: Cloudflare Workers (100K req/day), Cloudflare R2 (10GB), "
                    "Cloudflare D1 (5GB), Upstash Redis (10K/day), Supabase (500MB + 50K MAU), "
                    "Fly.io (3 shared VMs). No paid external AI APIs."
                ),
                "tags": ["billing", "zero-cost", "compliance", "platform"],
            },
        ]
        for a in seed_articles:
            art = Article(
                title=a["title"],
                body=a["body"],
                tags=a["tags"],
                author="system",
                source="internal",
                status=ArticleStatus.PUBLISHED,
            )
            self._articles[art.id] = art
            for tag in art.tags:
                self._tag_index.setdefault(tag, []).append(art.id)


# ── Module-level singleton ────────────────────────────────────────────────────
_library: Optional[Library] = None


def get_library() -> Library:
    global _library
    if _library is None:
        _library = Library()
    return _library
