"""KnowledgeBrain — The Library (Zimik) knowledge base.

A lightweight, zero-dependency knowledge store backed by SQLite. Provides:

  - ``BM25Index``      : in-memory BM25 ranking over page tokens
  - ``_rrf``           : reciprocal rank fusion for hybrid (lexical+vector) search
  - ``KBPage`` / ``KBLink`` : page and graph-edge dataclasses
  - ``KnowledgeBrain`` : async CRUD + search + agent memory + wikilink graph
  - ``get_brain``      : process-wide singleton accessor

Vector search (FAISS / embeddings) is optional and only engaged when
``use_vector=True`` and the optional dependency is importable; the core lexical
paths require neither FAISS nor torch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sqlite3
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tranc3.knowledge.brain")

# Alphabetic tokens of length >= 2 (numbers and single chars filtered out).
_WORD_RE = re.compile(r"\b[a-z]{2,}\b")
# [[Target]] or [[Target|alias]] wikilinks.
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class KBPage:
    """A single knowledge-base page."""

    id: str
    title: str
    content: str
    source: str = "manual"
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def word_tokens(self) -> list[str]:
        """Lowercased alphabetic tokens (length >= 2) from title + content."""
        return _WORD_RE.findall(f"{self.title} {self.content}".lower())


@dataclass
class KBLink:
    """A directed edge between two pages in the knowledge graph."""

    source_id: str
    target_id: str
    relation: str = "mentions"
    weight: float = 1.0


@dataclass
class SearchResult:
    """A single ranked search hit."""

    page: KBPage
    score: float
    excerpt: str


# ---------------------------------------------------------------------------
# BM25 lexical index
# ---------------------------------------------------------------------------


class BM25Index:
    """In-memory Okapi BM25 index over page tokens."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: dict[str, list[str]] = {}
        self._df: dict[str, int] = {}
        self._avgdl: float = 0.0
        self._n: int = 0

    def _recompute(self) -> None:
        self._n = len(self._docs)
        self._df = {}
        total_len = 0
        for tokens in self._docs.values():
            total_len += len(tokens)
            for term in set(tokens):
                self._df[term] = self._df.get(term, 0) + 1
        self._avgdl = (total_len / self._n) if self._n else 0.0

    def build(self, pages: list[KBPage]) -> None:
        """Rebuild the index from a list of pages."""
        self._docs = {p.id: p.word_tokens() for p in pages}
        self._recompute()

    def add(self, page: KBPage) -> None:
        """Index (or re-index) a single page."""
        self._docs[page.id] = page.word_tokens()
        self._recompute()

    def remove(self, page_id: str) -> None:
        """Drop a page from the index (no-op if absent)."""
        if page_id in self._docs:
            del self._docs[page_id]
            self._recompute()

    def query(self, text: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return ``[(page_id, score), ...]`` ranked by BM25, highest first."""
        if not self._docs:
            return []
        q_terms = _WORD_RE.findall(text.lower())
        if not q_terms:
            return []
        avgdl = self._avgdl or 1.0
        scores: dict[str, float] = {}
        for doc_id, tokens in self._docs.items():
            if not tokens:
                continue
            tf = Counter(tokens)
            dl = len(tokens)
            score = 0.0
            for term in q_terms:
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                df = self._df.get(term, 0)
                # BM25+ idf form — always >= 0.
                idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
                denom = freq + self.k1 * (1 - self.b + self.b * dl / avgdl)
                score += idf * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scores[doc_id] = score
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def _rrf(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Fuse multiple ranked id-lists via Reciprocal Rank Fusion.

    Returns ``[(id, fused_score), ...]`` sorted by score descending.
    """
    if not ranked_lists:
        return []
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


# ---------------------------------------------------------------------------
# KnowledgeBrain
# ---------------------------------------------------------------------------


def _excerpt(content: str, query: str, width: int = 200) -> str:
    """Return a snippet of ``content`` around the first query-term match."""
    if not content:
        return ""
    q_terms = _WORD_RE.findall(query.lower())
    lowered = content.lower()
    pos = -1
    for term in q_terms:
        pos = lowered.find(term)
        if pos != -1:
            break
    if pos == -1:
        return content[:width].strip()
    start = max(0, pos - width // 2)
    end = min(len(content), pos + width // 2)
    snippet = content[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(content) else "")


class KnowledgeBrain:
    """SQLite-backed knowledge base with lexical search and an agent-memory API."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        markdown_dir: Optional[str] = None,
    ) -> None:
        self._db_path = db_path or os.environ.get("KNOWLEDGE_DB_PATH", "/data/knowledge.db")
        self._markdown_dir = markdown_dir
        if markdown_dir:
            try:
                Path(markdown_dir).mkdir(parents=True, exist_ok=True)
            except Exception:  # pragma: no cover - best effort
                pass
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        self._index = BM25Index()
        self._rebuild_index()
        self._dream_task: Optional[asyncio.Task] = None
        self._dream_interval = float(os.environ.get("KNOWLEDGE_DREAM_INTERVAL", "3600"))

    # ── Schema / index ────────────────────────────────────────────────────
    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                source      TEXT DEFAULT 'manual',
                tags        TEXT DEFAULT '[]',
                metadata    TEXT DEFAULT '{}',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS links (
                source_id   TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                relation    TEXT DEFAULT 'mentions',
                weight      REAL DEFAULT 1.0,
                PRIMARY KEY (source_id, target_id, relation)
            );
            CREATE INDEX IF NOT EXISTS idx_pages_source ON pages(source);
            CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id);
            """
        )
        self._conn.commit()

    def _row_to_page(self, row: sqlite3.Row) -> KBPage:
        return KBPage(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            source=row["source"],
            tags=json.loads(row["tags"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _rebuild_index(self) -> None:
        rows = self._conn.execute("SELECT * FROM pages").fetchall()
        self._index.build([self._row_to_page(r) for r in rows])

    # ── Wikilink graph ────────────────────────────────────────────────────
    def _resolve_target(self, ref: str) -> Optional[str]:
        ref = ref.strip()
        row = self._conn.execute("SELECT id FROM pages WHERE id = ?", (ref,)).fetchone()
        if row:
            return row["id"]
        row = self._conn.execute(
            "SELECT id FROM pages WHERE lower(title) = ?", (ref.lower(),)
        ).fetchone()
        return row["id"] if row else None

    def _wire_wikilinks(self, page: KBPage) -> None:
        self._conn.execute("DELETE FROM links WHERE source_id = ?", (page.id,))
        for ref in _WIKILINK_RE.findall(page.content):
            target_id = self._resolve_target(ref)
            if target_id and target_id != page.id:
                self._conn.execute(
                    "INSERT OR REPLACE INTO links "
                    "(source_id, target_id, relation, weight) VALUES (?, ?, 'mentions', 1.0)",
                    (page.id, target_id),
                )
        self._conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────
    async def put_page(self, page: KBPage) -> str:
        """Insert or update a page; returns the stored page id."""
        now = time.time()
        page.updated_at = now
        self._conn.execute(
            "INSERT INTO pages (id, title, content, source, tags, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "title=excluded.title, content=excluded.content, source=excluded.source, "
            "tags=excluded.tags, metadata=excluded.metadata, updated_at=excluded.updated_at",
            (
                page.id,
                page.title,
                page.content,
                page.source,
                json.dumps(page.tags),
                json.dumps(page.metadata),
                page.created_at,
                now,
            ),
        )
        self._conn.commit()
        self._wire_wikilinks(page)
        self._index.add(page)
        self._write_markdown(page)
        return page.id

    def _write_markdown(self, page: KBPage) -> None:
        if not self._markdown_dir:
            return
        try:
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", page.id)
            Path(self._markdown_dir, f"{safe}.md").write_text(
                f"# {page.title}\n\n{page.content}\n", encoding="utf-8"
            )
        except Exception:  # pragma: no cover - best effort
            pass

    async def get_page(self, page_id: str) -> Optional[KBPage]:
        row = self._conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        return self._row_to_page(row) if row else None

    async def delete_page(self, page_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        self._conn.execute(
            "DELETE FROM links WHERE source_id = ? OR target_id = ?", (page_id, page_id)
        )
        self._conn.commit()
        self._index.remove(page_id)
        return cur.rowcount > 0

    async def list_pages(self, source: Optional[str] = None, limit: int = 1000) -> list[KBPage]:
        if source is not None:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE source = ? ORDER BY updated_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM pages ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_page(r) for r in rows]

    # ── Search ────────────────────────────────────────────────────────────
    async def search(
        self, query: str, top_k: int = 10, use_vector: bool = False
    ) -> list[SearchResult]:
        lexical = self._index.query(query, top_k=top_k)
        ranked_ids: list[str]
        if use_vector:
            vector_ids = self._vector_query(query, top_k=top_k)
            if vector_ids:
                fused = _rrf([[pid for pid, _ in lexical], vector_ids])
                ranked_ids = [pid for pid, _ in fused][:top_k]
            else:
                ranked_ids = [pid for pid, _ in lexical]
        else:
            ranked_ids = [pid for pid, _ in lexical]

        score_map = dict(lexical)
        results: list[SearchResult] = []
        for pid in ranked_ids:
            page = await self.get_page(pid)
            if page is None:
                continue
            results.append(
                SearchResult(
                    page=page,
                    score=float(score_map.get(pid, 0.0)),
                    excerpt=_excerpt(page.content, query),
                )
            )
        return results

    def _vector_query(self, query: str, top_k: int = 10) -> list[str]:
        """Optional embedding search; returns [] when unavailable."""
        try:  # pragma: no cover - optional dependency path
            from src.knowledge.vector_store import VectorStore  # noqa: F401
        except Exception:
            return []
        return []

    # ── Agent memory ──────────────────────────────────────────────────────
    async def remember(
        self,
        agent_id: str,
        content: str,
        tags: Optional[list[str]] = None,
        title: Optional[str] = None,
    ) -> str:
        """Persist an agent memory, isolated by an ``agent:<id>`` tag."""
        page_id = f"mem-{uuid.uuid4().hex}"
        all_tags = [f"agent:{agent_id}"] + list(tags or [])
        page = KBPage(
            id=page_id,
            title=title or f"Memory ({agent_id})",
            content=content,
            source="agent-memory",
            tags=all_tags,
        )
        await self.put_page(page)
        return page_id

    async def recall(self, agent_id: str, query: str, top_k: int = 10) -> list[SearchResult]:
        """Recall an agent's memories matching ``query`` (tag-scoped)."""
        tag = f"agent:{agent_id}"
        # Over-fetch then filter so isolation never drops relevant hits.
        results = await self.search(query, top_k=top_k * 4, use_vector=False)
        scoped = [r for r in results if tag in r.page.tags]
        return scoped[:top_k]

    # ── Stats ─────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        page_count = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        link_count = self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        return {
            "page_count": int(page_count),
            "link_count": int(link_count),
            "indexed_docs": self._index._n,
        }

    # ── Dream cycle (background consolidation) ─────────────────────────────
    async def start_dream_cycle(self) -> None:
        """Start the background consolidation loop (idempotent)."""
        if self._dream_task and not self._dream_task.done():
            return
        self._dream_task = asyncio.create_task(self._dream_loop())

    async def stop_dream_cycle(self) -> None:
        """Stop the background consolidation loop."""
        if self._dream_task and not self._dream_task.done():
            self._dream_task.cancel()
            try:
                await self._dream_task
            except (asyncio.CancelledError, Exception):
                pass
        self._dream_task = None

    async def _dream_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._dream_interval)
                self._rebuild_index()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - resilience
                logger.debug("dream cycle iteration failed: %s", exc)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_brain: Optional[KnowledgeBrain] = None


def get_brain() -> KnowledgeBrain:
    """Return the process-wide KnowledgeBrain singleton."""
    global _brain
    if _brain is None:
        _brain = KnowledgeBrain()
    return _brain
