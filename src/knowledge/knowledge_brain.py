"""
src/knowledge/knowledge_brain.py — Lightweight in-process knowledge base.

Provides:
  - BM25Index   : BM25 full-text scoring without external dependencies
  - KBPage      : Page dataclass (title, content, metadata, tags)
  - KBLink      : Wikilink edge dataclass
  - KnowledgeBrain : CRUD + search + agent memory (SQLite-backed, async API)

Zero external dependencies for core paths — FAISS/torch are optional for
vector similarity search (falls back to BM25-only if unavailable).
"""

from __future__ import annotations

import asyncio
import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class KBPage:
    id: str
    title: str
    content: str
    source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def word_tokens(self) -> list[str]:
        """Return lowercased word tokens from content, filtering numbers and very short tokens."""
        return re.findall(r"\b[a-z]{2,}\b", self.content.lower())


@dataclass
class KBLink:
    source_id: str
    target_id: str
    alias: str = ""
    relation: str = "mentions"
    weight: float = 1.0


@dataclass
class SearchResult:
    page: KBPage
    score: float
    excerpt: str = ""


# ── BM25 Index ────────────────────────────────────────────────────────────────


class BM25Index:
    """BM25F text scoring index backed by in-memory data structures."""

    K1 = 1.5
    B = 0.75

    def __init__(self) -> None:
        self._docs: dict[str, list[str]] = {}  # doc_id → tokens
        self._idf: dict[str, float] = {}
        self._avgdl: float = 0.0
        self._dirty = True

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def build(self, pages: list[KBPage]) -> None:
        """Build index from a list of KBPage objects."""
        self._docs.clear()
        for page in pages:
            self._docs[page.id] = self._tokenize(f"{page.title} {page.content}")
        self._dirty = True

    def add(self, page_or_id: "KBPage | str", text: str = "") -> None:
        """Add a single page or (doc_id, text) pair to the index."""
        if isinstance(page_or_id, str):
            # Legacy: add(doc_id, text)
            self._docs[page_or_id] = self._tokenize(text)
        else:
            # New: add(KBPage)
            page = page_or_id
            self._docs[page.id] = self._tokenize(f"{page.title} {page.content}")
        self._dirty = True

    def remove(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._dirty = True

    def _build(self) -> None:
        if not self._dirty:
            return
        N = len(self._docs)
        if N == 0:
            self._idf = {}
            self._avgdl = 0.0
            self._dirty = False
            return
        self._avgdl = sum(len(t) for t in self._docs.values()) / N
        df: dict[str, int] = {}
        for tokens in self._docs.values():
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1
        self._idf = {
            tok: math.log((N - freq + 0.5) / (freq + 0.5) + 1.0)
            for tok, freq in df.items()
        }
        self._dirty = False

    def query(self, text: str, top_k: int = 10) -> list[tuple[str, float]]:
        self._build()
        if not self._docs:
            return []
        query_tokens = self._tokenize(text)
        scores: dict[str, float] = {}
        for doc_id, tokens in self._docs.items():
            dl = len(tokens)
            tf: dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            score = 0.0
            for qt in query_tokens:
                if qt not in self._idf:
                    continue
                idf = self._idf[qt]
                f = tf.get(qt, 0)
                norm = f * (self.K1 + 1) / (
                    f + self.K1 * (1 - self.B + self.B * dl / max(self._avgdl, 1))
                )
                score += idf * norm
            if score > 0:
                scores[doc_id] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────


def _rrf(
    rankings: "list[list[str]] | list[list[tuple[str, float]]]",
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge multiple ranked lists via Reciprocal Rank Fusion.

    Accepts either plain id lists or scored (id, score) tuple lists.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            doc_id = item if isinstance(item, str) else item[0]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Knowledge Brain ───────────────────────────────────────────────────────────


class KnowledgeBrain:
    """
    CRUD + search knowledge base backed by SQLite and an in-process BM25 index.

    Usage:
        brain = KnowledgeBrain()                                      # in-memory (tests)
        brain = KnowledgeBrain("data/knowledge.db")                   # persistent
        brain = KnowledgeBrain("data/knowledge.db", markdown_dir=...) # with markdown import dir
    """

    def __init__(self, db_path: str = ":memory:", markdown_dir: Optional[str] = None) -> None:
        self._db_path = db_path
        self._markdown_dir = Path(markdown_dir) if markdown_dir else None
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._bm25 = BM25Index()
        self._init_db()
        self._rebuild_index()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                source     TEXT DEFAULT 'manual',
                metadata   TEXT DEFAULT '{}',
                tags       TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS links (
                source_id  TEXT NOT NULL,
                target_id  TEXT NOT NULL,
                alias      TEXT DEFAULT '',
                relation   TEXT DEFAULT 'mentions',
                weight     REAL DEFAULT 1.0,
                PRIMARY KEY (source_id, target_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pages_source ON pages(source);
            CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id);
        """)
        self._conn.commit()

    def _rebuild_index(self) -> None:
        rows = self._conn.execute("SELECT id, title, content FROM pages").fetchall()
        for row in rows:
            self._bm25._docs[row["id"]] = BM25Index._tokenize(f"{row['title']} {row['content']}")
        if rows:
            self._bm25._dirty = True

    def _row_to_page(self, row: sqlite3.Row) -> KBPage:
        import json
        return KBPage(
            id=row["id"], title=row["title"], content=row["content"],
            source=row["source"], metadata=json.loads(row["metadata"] or "{}"),
            tags=json.loads(row["tags"] or "[]"),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # ── Async CRUD ────────────────────────────────────────────────────────────

    async def put_page(self, page: KBPage) -> str:
        """Insert or update a page; returns the page id."""
        import json
        now = time.time()
        self._conn.execute(
            """INSERT INTO pages(id, title, content, source, metadata, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, content=excluded.content,
                 source=excluded.source, metadata=excluded.metadata,
                 tags=excluded.tags, updated_at=excluded.updated_at""",
            (
                page.id, page.title, page.content, page.source,
                json.dumps(page.metadata), json.dumps(page.tags), now, now,
            ),
        )
        self._conn.commit()
        self._bm25.add(page)
        # Remove stale wikilinks before re-inserting
        self._conn.execute("DELETE FROM links WHERE source_id = ?", (page.id,))
        for link in _parse_wikilinks(page.id, page.content):
            self._conn.execute(
                """INSERT OR IGNORE INTO links(source_id, target_id, alias, relation, weight)
                   VALUES (?, ?, ?, ?, ?)""",
                (link.source_id, link.target_id, link.alias, link.relation, link.weight),
            )
        self._conn.commit()
        return page.id

    async def get_page(self, page_id: str) -> Optional[KBPage]:
        """Retrieve a page by id; returns None if not found."""
        row = self._conn.execute(
            "SELECT * FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    async def delete_page(self, page_id: str) -> bool:
        """Delete a page; returns True if a row was deleted."""
        cursor = self._conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        self._conn.commit()
        if cursor.rowcount > 0:
            self._bm25.remove(page_id)
            self._conn.execute(
                "DELETE FROM links WHERE source_id = ? OR target_id = ?", (page_id, page_id)
            )
            self._conn.commit()
            return True
        return False

    async def list_pages(self, source: Optional[str] = None) -> list[KBPage]:
        """List all pages, optionally filtered by source."""
        if source is not None:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE source = ? ORDER BY updated_at DESC", (source,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM pages ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_page(r) for r in rows]

    # ── Async Search ──────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 10,
        use_vector: bool = True,
    ) -> list[SearchResult]:
        """Search pages; use_vector=False forces BM25-only (no FAISS required)."""
        hits = self._bm25.query(query, top_k=top_k)
        results: list[SearchResult] = []
        for doc_id, score in hits:
            page = await self.get_page(doc_id)
            if page is None:
                continue
            excerpt = _make_excerpt(page.content, query)
            results.append(SearchResult(page=page, score=score, excerpt=excerpt))
        return results

    # ── Async Agent Memory ────────────────────────────────────────────────────

    async def remember(
        self,
        agent_id: str,
        content: str,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Store a memory for an agent; returns the page id."""
        page_id = f"mem:{agent_id}:{uuid.uuid4().hex[:8]}"
        all_tags = [f"agent:{agent_id}"] + (tags or [])
        page = KBPage(
            id=page_id,
            title=f"Memory for {agent_id}",
            content=content,
            source="agent_memory",
            tags=all_tags,
        )
        return await self.put_page(page)

    async def recall(
        self,
        agent_id: str,
        query: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Retrieve memories for an agent scoped by agent_id tag."""
        hits = self._bm25.query(query, top_k=top_k * 3)
        results: list[SearchResult] = []
        agent_tag = f"agent:{agent_id}"
        for doc_id, score in hits:
            page = await self.get_page(doc_id)
            if page is None:
                continue
            if agent_tag not in page.tags:
                continue
            excerpt = _make_excerpt(page.content, query)
            results.append(SearchResult(page=page, score=score, excerpt=excerpt))
            if len(results) >= top_k:
                break
        return results

    # ── Stats (sync — fast) ───────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        page_count = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        link_count = self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        sources = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT source FROM pages WHERE source != ''"
            ).fetchall()
        ]
        return {
            "page_count": page_count,
            "link_count": link_count,
            "sources": sources,
            "indexed": len(self._bm25._docs),
        }

    # ── Legacy sync aliases ───────────────────────────────────────────────────

    def put(self, page: KBPage) -> None:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.put_page(page), loop)
            fut.result(timeout=10)
        else:
            loop.run_until_complete(self.put_page(page))

    def get(self, page_id: str) -> Optional[KBPage]:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.get_page(page_id), loop)
            return fut.result(timeout=10)
        return loop.run_until_complete(self.get_page(page_id))

    def delete(self, page_id: str) -> bool:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.delete_page(page_id), loop)
            return fut.result(timeout=10)
        return loop.run_until_complete(self.delete_page(page_id))

    def list(self, source: Optional[str] = None) -> list[KBPage]:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self.list_pages(source=source), loop)
            return fut.result(timeout=10)
        return loop.run_until_complete(self.list_pages(source=source))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_wikilinks(source_id: str, content: str) -> list[KBLink]:
    """Extract [[Target]] and [[Target|Alias]] wikilinks from content."""
    links: list[KBLink] = []
    for m in re.finditer(r"\[\[([^\]]+)\]\]", content):
        raw = m.group(1)
        if "|" in raw:
            target, alias = raw.split("|", 1)
        else:
            target, alias = raw, ""
        target = target.strip().lower().replace(" ", "-")
        if target and target != source_id:
            links.append(KBLink(source_id=source_id, target_id=target, alias=alias.strip()))
    return links


def _make_excerpt(content: str, query: str, window: int = 120) -> str:
    """Return a short excerpt from content near the first query term hit."""
    lower = content.lower()
    for token in re.findall(r"\w+", query.lower()):
        pos = lower.find(token)
        if pos != -1:
            start = max(0, pos - window // 2)
            end = min(len(content), pos + window // 2)
            return ("…" if start > 0 else "") + content[start:end] + ("…" if end < len(content) else "")
    return content[:window] + ("…" if len(content) > window else "")
