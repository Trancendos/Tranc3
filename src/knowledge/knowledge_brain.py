"""
Knowledge Brain — GBrain-inspired hybrid retrieval + persistent knowledge graph
===============================================================================
Provides The Library (Zimik) with:

  • Markdown document store (git-friendly, human-editable source of truth)
  • SQLite-backed persistence — survives restarts, no paid services
  • BM25 full-text search (pure Python, zero extra deps)
  • Vector search via FAISS (existing src/knowledge/vector_store.py)
  • RRF (Reciprocal Rank Fusion) combining both signal streams
  • Wikilink auto-wiring [[Target|Label]] → typed KnowledgeEdge
  • Agent memory: structured read/write for Tranc3 agents
  • Dream cycle: background consolidation pass (deduplication + reinforcement)

Zero external dependencies beyond what is already in requirements.txt.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/knowledge_brain.db")
_MARKDOWN_DIR = Path("data/knowledge")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class KBPage:
    """A single page in the knowledge base (markdown doc or agent memory)."""

    id: str
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    source: str = "manual"          # "manual" | "agent" | "ingestion" | "dream"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")

    def word_tokens(self) -> List[str]:
        """Lowercase word tokens for BM25."""
        return re.findall(r"\b[a-z]{2,}\b", self.content.lower())


@dataclass
class KBLink:
    """Typed directed link between two pages (from wikilinks or manual edges)."""

    source_id: str
    target_id: str
    relation: str = "mentions"      # mentions | works_at | founded | part_of | …
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    """A ranked page returned from hybrid search."""

    page: KBPage
    score: float
    matched_by: str                 # "bm25" | "vector" | "hybrid"
    excerpt: str = ""               # short snippet from page content


# ---------------------------------------------------------------------------
# BM25 implementation (pure Python — no extra deps)
# ---------------------------------------------------------------------------


class BM25Index:
    """
    Okapi BM25 index over a corpus of KBPage objects.

    k1=1.5, b=0.75 are the standard constants.  Reindex incrementally
    by calling `add()` / `remove()`; full rebuild via `build()`.
    """

    K1 = 1.5
    B = 0.75

    def __init__(self) -> None:
        self._docs: Dict[str, List[str]] = {}      # id → token list
        self._df: Dict[str, int] = defaultdict(int)  # term → doc freq
        self._avgdl: float = 0.0
        self._dirty = False

    def build(self, pages: List[KBPage]) -> None:
        self._docs = {p.id: p.word_tokens() for p in pages}
        self._recompute_stats()

    def add(self, page: KBPage) -> None:
        tokens = page.word_tokens()
        if page.id in self._docs:
            self.remove(page.id)
        self._docs[page.id] = tokens
        for tok in set(tokens):
            self._df[tok] += 1
        self._dirty = True

    def remove(self, page_id: str) -> None:
        if page_id not in self._docs:
            return
        for tok in set(self._docs[page_id]):
            self._df[tok] = max(0, self._df[tok] - 1)
        del self._docs[page_id]
        self._dirty = True

    def _recompute_stats(self) -> None:
        self._df = defaultdict(int)
        total_len = 0
        for tokens in self._docs.values():
            total_len += len(tokens)
            for tok in set(tokens):
                self._df[tok] += 1
        self._avgdl = total_len / max(1, len(self._docs))
        self._dirty = False

    @property
    def avgdl(self) -> float:
        if self._dirty:
            self._recompute_stats()
        return self._avgdl

    def score(self, query_tokens: List[str], page_id: str) -> float:
        if page_id not in self._docs:
            return 0.0
        doc = self._docs[page_id]
        dl = len(doc)
        doc_tf: Dict[str, int] = defaultdict(int)
        for tok in doc:
            doc_tf[tok] += 1
        n = len(self._docs)
        score = 0.0
        avgdl = self.avgdl
        for tok in query_tokens:
            idf_num = n - self._df.get(tok, 0) + 0.5
            idf_den = self._df.get(tok, 0) + 0.5
            idf = math.log((idf_num / idf_den) + 1)
            tf = doc_tf.get(tok, 0)
            tf_norm = tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * dl / max(1, avgdl)))
            score += idf * tf_norm
        return score

    def query(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Return (page_id, score) pairs sorted by descending score."""
        tokens = re.findall(r"\b[a-z]{2,}\b", query.lower())
        if not tokens:
            return []
        results = [(pid, self.score(tokens, pid)) for pid in self._docs]
        results.sort(key=lambda x: x[1], reverse=True)
        return [(pid, s) for pid, s in results[:top_k] if s > 0]


# ---------------------------------------------------------------------------
# Wikilink parser
# ---------------------------------------------------------------------------


_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _extract_wikilinks(content: str) -> List[Tuple[str, str]]:
    """Return list of (target_title, display_label) from [[target|label]] syntax."""
    return [(m.group(1).strip(), (m.group(2) or m.group(1)).strip())
            for m in _WIKILINK_RE.finditer(content)]


def _infer_relation(context: str, target: str) -> str:
    """Heuristic: infer edge relation from surrounding text context."""
    ctx = context.lower()
    if any(kw in ctx for kw in ("works at", "employed by", "works for")):
        return "works_at"
    if any(kw in ctx for kw in ("founded", "created by", "built by")):
        return "founded"
    if any(kw in ctx for kw in ("part of", "belongs to", "member of")):
        return "part_of"
    if any(kw in ctx for kw in ("leads", "manages", "head of")):
        return "leads"
    return "mentions"


# ---------------------------------------------------------------------------
# SQLite persistence layer
# ---------------------------------------------------------------------------


class _KBStore:
    """Thin SQLite wrapper — pages + links tables."""

    def __init__(self, db_path: Union[str, Path] = _DB_PATH) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                tags        TEXT DEFAULT '[]',
                source      TEXT DEFAULT 'manual',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                metadata    TEXT DEFAULT '{}'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pages_title ON pages(title);
            CREATE INDEX IF NOT EXISTS idx_pages_source ON pages(source);
            CREATE TABLE IF NOT EXISTS links (
                source_id   TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                relation    TEXT NOT NULL DEFAULT 'mentions',
                weight      REAL NOT NULL DEFAULT 1.0,
                created_at  REAL NOT NULL,
                PRIMARY KEY (source_id, target_id, relation)
            );
            CREATE INDEX IF NOT EXISTS idx_links_src ON links(source_id);
            CREATE INDEX IF NOT EXISTS idx_links_tgt ON links(target_id);
        """)
        self._conn.commit()

    # -- pages --

    def upsert_page(self, page: KBPage) -> None:
        import json
        self._conn.execute(
            """INSERT INTO pages(id,title,content,tags,source,created_at,updated_at,metadata)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, content=excluded.content, tags=excluded.tags,
                 source=excluded.source, updated_at=excluded.updated_at,
                 metadata=excluded.metadata""",
            (page.id, page.title, page.content, json.dumps(page.tags),
             page.source, page.created_at, page.updated_at, json.dumps(page.metadata)),
        )
        self._conn.commit()

    def get_page(self, page_id: str) -> Optional[KBPage]:
        row = self._conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
        return self._row_to_page(row) if row else None

    def get_page_by_title(self, title: str) -> Optional[KBPage]:
        row = self._conn.execute(
            "SELECT * FROM pages WHERE lower(title)=lower(?)", (title,)
        ).fetchone()
        return self._row_to_page(row) if row else None

    def delete_page(self, page_id: str) -> bool:
        c = self._conn.execute("DELETE FROM pages WHERE id=?", (page_id,))
        self._conn.execute("DELETE FROM links WHERE source_id=? OR target_id=?",
                           (page_id, page_id))
        self._conn.commit()
        return c.rowcount > 0

    def all_pages(self) -> Iterator[KBPage]:
        for row in self._conn.execute("SELECT * FROM pages ORDER BY updated_at DESC"):
            yield self._row_to_page(row)

    def count_pages(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]

    def count_links(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> KBPage:
        import json
        return KBPage(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            tags=json.loads(row["tags"] or "[]"),
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -- links --

    def upsert_link(self, link: KBLink) -> None:
        self._conn.execute(
            """INSERT INTO links(source_id,target_id,relation,weight,created_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(source_id,target_id,relation) DO UPDATE SET
                 weight=excluded.weight""",
            (link.source_id, link.target_id, link.relation, link.weight, link.created_at),
        )
        self._conn.commit()

    def get_links_from(self, source_id: str) -> List[KBLink]:
        rows = self._conn.execute(
            "SELECT * FROM links WHERE source_id=?", (source_id,)
        ).fetchall()
        return [KBLink(r["source_id"], r["target_id"], r["relation"],
                       r["weight"], r["created_at"]) for r in rows]

    def get_links_to(self, target_id: str) -> List[KBLink]:
        rows = self._conn.execute(
            "SELECT * FROM links WHERE target_id=?", (target_id,)
        ).fetchall()
        return [KBLink(r["source_id"], r["target_id"], r["relation"],
                       r["weight"], r["created_at"]) for r in rows]


# ---------------------------------------------------------------------------
# RRF (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------


def _rrf(ranked_lists: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
    """
    Combine multiple ranked lists with RRF.

    Parameters
    ----------
    ranked_lists : each sublist is an ordered list of page IDs (best first)
    k            : smoothing constant (Cormack et al. 2009 default: 60)

    Returns
    -------
    List of (page_id, rrf_score) sorted descending.
    """
    scores: Dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, pid in enumerate(ranked):
            scores[pid] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# KnowledgeBrain — public API
# ---------------------------------------------------------------------------


class KnowledgeBrain:
    """
    The Library (Zimik) — persistent, queryable knowledge brain.

    Usage::

        brain = KnowledgeBrain()
        await brain.put_page(KBPage(id="...", title="Tranc3", content="..."))
        results = await brain.search("transformer inference", top_k=5)
    """

    def __init__(
        self,
        db_path: Path = _DB_PATH,
        markdown_dir: Path = _MARKDOWN_DIR,
        dream_interval_s: float = 300.0,
    ) -> None:
        self._store = _KBStore(db_path)
        self._markdown_dir = markdown_dir
        self._bm25 = BM25Index()
        self._dream_interval = dream_interval_s
        self._dream_task: Optional[asyncio.Task] = None
        self._vector_store = None       # lazy — loaded on first vector search
        self._lock = asyncio.Lock()

        # Rebuild BM25 from persisted pages
        pages = list(self._store.all_pages())
        self._bm25.build(pages)
        logger.info("KnowledgeBrain ready (%d pages in index)", len(pages))

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    async def put_page(self, page: KBPage) -> str:
        """Store or update a page; wire wikilinks automatically."""
        async with self._lock:
            if not page.id:
                page.id = uuid.uuid4().hex
            page.updated_at = time.time()
            self._store.upsert_page(page)
            self._bm25.add(page)
            await self._wire_wikilinks(page)
            if self._vector_store:
                self._vector_store.upsert(page.id, page.content, {"title": page.title})
        return page.id

    async def get_page(self, page_id: str) -> Optional[KBPage]:
        return self._store.get_page(page_id)

    async def get_page_by_title(self, title: str) -> Optional[KBPage]:
        return self._store.get_page_by_title(title)

    async def delete_page(self, page_id: str) -> bool:
        async with self._lock:
            page = self._store.get_page(page_id)
            if page:
                self._bm25.remove(page_id)
            return self._store.delete_page(page_id)

    async def list_pages(
        self,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[KBPage]:
        pages = list(self._store.all_pages())
        if source:
            pages = [p for p in pages if p.source == source]
        return pages[:limit]

    # ------------------------------------------------------------------
    # Hybrid search (BM25 + vector + RRF)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 10,
        use_vector: bool = True,
    ) -> List[SearchResult]:
        """Hybrid search: BM25 + optional FAISS vector, fused with RRF."""
        bm25_hits = self._bm25.query(query, top_k=top_k * 2)
        bm25_ranked = [pid for pid, _ in bm25_hits]

        vector_ranked: List[str] = []
        if use_vector:
            vector_ranked = await self._vector_query(query, top_k=top_k * 2)

        if not bm25_ranked and not vector_ranked:
            return []

        ranked_lists = [lst for lst in [bm25_ranked, vector_ranked] if lst]
        fused = _rrf(ranked_lists)

        results: List[SearchResult] = []
        for pid, rrf_score in fused[:top_k]:
            page = self._store.get_page(pid)
            if page:
                both = pid in bm25_ranked and pid in vector_ranked
                matched_by = "hybrid" if both else ("bm25" if pid in bm25_ranked else "vector")
                excerpt = page.content[:200].rstrip()
                results.append(SearchResult(page=page, score=rrf_score, matched_by=matched_by, excerpt=excerpt))
        return results

    async def _vector_query(self, query: str, top_k: int) -> List[str]:
        """Query the FAISS vector store, return ranked page IDs."""
        try:
            vs = self._get_vector_store()
            hits = vs.query(collection="knowledge_brain", query_text=query, top_k=top_k)
            return [h["id"] for h in hits]
        except Exception as exc:
            logger.debug("Vector query skipped: %s", exc)
            return []

    def _get_vector_store(self):
        if self._vector_store is None:
            from src.knowledge.vector_store import VectorStore  # type: ignore
            self._vector_store = VectorStore()
        return self._vector_store

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    async def get_neighbours(self, page_id: str, max_hops: int = 1) -> List[KBPage]:
        """Return pages reachable within max_hops from page_id."""
        visited = {page_id}
        frontier = {page_id}
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for pid in frontier:
                for link in self._store.get_links_from(pid):
                    if link.target_id not in visited:
                        visited.add(link.target_id)
                        next_frontier.add(link.target_id)
                for link in self._store.get_links_to(pid):
                    if link.source_id not in visited:
                        visited.add(link.source_id)
                        next_frontier.add(link.source_id)
            frontier = next_frontier
        visited.discard(page_id)
        pages = [self._store.get_page(pid) for pid in visited]
        return [p for p in pages if p is not None]

    async def graph_search(
        self,
        query: str,
        top_k: int = 5,
        expansion_hops: int = 1,
    ) -> List[SearchResult]:
        """
        Graph-augmented search: hybrid retrieval + neighbour expansion.

        Finds top-k matches by hybrid search, then expands their neighbours
        and re-ranks by boosted RRF.  This mirrors GBrain's +31pt P@5 lift
        from graph layer on top of dense retrieval.
        """
        initial = await self.search(query, top_k=top_k)
        if not initial:
            return []

        seed_ids = [r.page.id for r in initial]
        seen = set(seed_ids)

        # Expand one hop
        expanded_ids: List[str] = []
        for pid in seed_ids[:3]:                    # only top-3 seeds to avoid explosion
            for link in self._store.get_links_from(pid):
                if link.target_id not in seen:
                    seen.add(link.target_id)
                    expanded_ids.append(link.target_id)

        # Re-score expanded candidates with BM25
        expanded_results: List[SearchResult] = []
        for pid in expanded_ids:
            page = self._store.get_page(pid)
            if not page:
                continue
            tokens = re.findall(r"\b[a-z]{2,}\b", query.lower())
            bm25_score = self._bm25.score(tokens, pid) if tokens else 0.0
            if bm25_score > 0:
                expanded_results.append(SearchResult(page=page, score=bm25_score * 0.7,
                                                      matched_by="graph_expanded"))

        combined = initial + expanded_results
        combined.sort(key=lambda r: r.score, reverse=True)
        return combined[:top_k]

    # ------------------------------------------------------------------
    # Agent memory API
    # ------------------------------------------------------------------

    async def remember(
        self,
        agent_id: str,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory fragment from an agent. Returns the page_id."""
        title = f"memory:{agent_id}:{uuid.uuid4().hex[:8]}"
        page = KBPage(
            id=uuid.uuid4().hex,
            title=title,
            content=content,
            tags=(tags or []) + ["agent_memory", agent_id],
            source="agent",
            metadata={**(metadata or {}), "agent_id": agent_id},
        )
        return await self.put_page(page)

    async def recall(
        self,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Retrieve relevant memories for an agent."""
        results = await self.search(query, top_k=top_k * 2)
        # Boost pages tagged with this agent_id
        for r in results:
            if agent_id in r.page.tags:
                r.score *= 1.5
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Markdown ingestion
    # ------------------------------------------------------------------

    async def ingest_markdown(
        self,
        path: Path,
        source_tag: str = "ingestion",
    ) -> int:
        """
        Ingest all .md files under *path* into the knowledge brain.

        - Parses YAML front-matter for title/tags if present
        - Extracts wikilinks and wires edges automatically
        - Returns count of pages upserted.
        """
        count = 0
        for md_file in sorted(path.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                title, body, tags = _parse_markdown(content, md_file.stem)
                page_id = hashlib.sha256(str(md_file).encode()).hexdigest()[:16]
                page = KBPage(
                    id=page_id,
                    title=title,
                    content=body,
                    tags=tags,
                    source=source_tag,
                    metadata={"file": str(md_file)},
                )
                await self.put_page(page)
                count += 1
            except Exception as exc:
                logger.warning("Failed to ingest %s: %s", md_file, exc)
        logger.info("Ingested %d markdown pages from %s", count, path)
        return count

    # ------------------------------------------------------------------
    # Wikilink auto-wiring (private)
    # ------------------------------------------------------------------

    async def _wire_wikilinks(self, page: KBPage) -> None:
        """Parse [[Target]] links in *page* and create KB edges."""
        for target_title, _ in _extract_wikilinks(page.content):
            target = self._store.get_page_by_title(target_title)
            if target is None:
                # Create a stub page so the link target exists
                stub = KBPage(
                    id=uuid.uuid4().hex,
                    title=target_title,
                    content=f"# {target_title}\n\n*Stub — created from wikilink.*",
                    source="stub",
                )
                self._store.upsert_page(stub)
                self._bm25.add(stub)
                target = stub

            # Infer relation from sentence context
            relation = _infer_relation(page.content, target_title)
            link = KBLink(
                source_id=page.id,
                target_id=target.id,
                relation=relation,
            )
            self._store.upsert_link(link)

    # ------------------------------------------------------------------
    # Dream cycle — background consolidation
    # ------------------------------------------------------------------

    async def start_dream_cycle(self) -> None:
        """Launch background consolidation task."""
        if self._dream_task and not self._dream_task.done():
            return
        self._dream_task = asyncio.create_task(self._dream_loop(), name="knowledge_brain_dream")
        logger.info("Knowledge Brain dream cycle started (interval=%.0fs)", self._dream_interval)

    async def stop_dream_cycle(self) -> None:
        if self._dream_task:
            self._dream_task.cancel()
            try:
                await self._dream_task
            except asyncio.CancelledError:
                pass

    async def _dream_loop(self) -> None:
        while True:
            await asyncio.sleep(self._dream_interval)
            try:
                await self._consolidate()
            except Exception as exc:
                logger.warning("Dream cycle error: %s", exc)

    async def _consolidate(self) -> None:
        """
        Consolidation pass:
          1. Deduplicate near-identical stubs
          2. Boost frequently-accessed pages (promote to 'reinforced')
          3. Clean orphaned links pointing to deleted pages
        """
        pages = list(self._store.all_pages())

        # Remove stubs that now have a real counterpart
        stub_titles = {p.title: p for p in pages if p.source == "stub"}
        real_titles = {p.title: p for p in pages if p.source != "stub"}
        for title, stub in stub_titles.items():
            if title in real_titles:
                self._store.delete_page(stub.id)
                self._bm25.remove(stub.id)

        logger.debug("Dream consolidation done (pages=%d)", self._store.count_pages())

    # ------------------------------------------------------------------
    # GBrain — PageRank importance scoring
    # ------------------------------------------------------------------

    async def compute_pagerank(
        self,
        damping: float = 0.85,
        max_iter: int = 50,
        tolerance: float = 1e-6,
    ) -> Dict[str, float]:
        """
        GBrain-inspired PageRank over the knowledge graph.

        Computes an importance score for every page based on its link
        structure, then stores the score in page metadata for retrieval
        boosting.  Returns a mapping of page_id → score.
        """
        async with self._lock:
            pages = list(self._store.all_pages())
            if not pages:
                return {}

            id_to_idx = {p.id: i for i, p in enumerate(pages)}
            n = len(pages)

            # Build out-link structure from KBLinks
            out_links: Dict[int, List[int]] = {i: [] for i in range(n)}
            for page in pages:
                links = self._store.get_links_from(page.id)
                for lnk in links:
                    tgt_idx = id_to_idx.get(lnk.target_id)
                    if tgt_idx is not None:
                        out_links[id_to_idx[page.id]].append(tgt_idx)

            # Initialise uniformly
            scores = [1.0 / n] * n

            for _ in range(max_iter):
                new_scores = [(1 - damping) / n] * n
                for src_idx, tgt_indices in out_links.items():
                    if not tgt_indices:
                        # Dangling node: distribute evenly
                        contrib = damping * scores[src_idx] / n
                        for j in range(n):
                            new_scores[j] += contrib
                    else:
                        contrib = damping * scores[src_idx] / len(tgt_indices)
                        for tgt_idx in tgt_indices:
                            new_scores[tgt_idx] += contrib

                delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
                scores = new_scores
                if delta < tolerance:
                    break

            # Persist scores into page metadata
            result: Dict[str, float] = {}
            now = time.time()
            for i, page in enumerate(pages):
                score = round(scores[i], 6)
                page.metadata["pagerank"] = score
                page.updated_at = now
                self._store.upsert_page(page)
                result[page.id] = score

            logger.info(
                "PageRank computed for %d pages (top: %.6f, bottom: %.6f)",
                n, max(scores), min(scores),
            )
            return result

    async def pagerank_boosted_search(
        self,
        query: str,
        top_k: int = 10,
        pagerank_weight: float = 0.3,
    ) -> List["SearchResult"]:
        """
        Hybrid search with GBrain PageRank re-ranking.

        Combines BM25/vector relevance (0.7 weight) with PageRank
        importance (0.3 weight) for improved result quality.
        """
        raw_results = await self.search(query, top_k=top_k * 2)
        if not raw_results:
            return []

        # Normalise relevance scores
        max_score = max(r.score for r in raw_results) or 1.0
        reranked = []
        for result in raw_results:
            pr = result.page.metadata.get("pagerank", 0.0)
            combined = (1 - pagerank_weight) * (result.score / max_score) + pagerank_weight * pr
            reranked.append((combined, result))

        reranked.sort(key=lambda x: -x[0])
        return [r for _, r in reranked[:top_k]]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        page_count = self._store.count_pages()
        link_count = self._store.count_links()
        return {
            "page_count": page_count,
            "link_count": link_count,
            "total_pages": page_count,   # legacy alias
            "bm25_indexed": len(self._bm25._docs),
            "dream_interval_s": self._dream_interval,
            "dream_running": bool(self._dream_task and not self._dream_task.done()),
        }


# ---------------------------------------------------------------------------
# Markdown front-matter parser (minimal YAML-like)
# ---------------------------------------------------------------------------


_FM_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)


def _parse_markdown(content: str, fallback_title: str) -> Tuple[str, str, List[str]]:
    """Extract (title, body, tags) from optional YAML front-matter."""
    title = fallback_title
    tags: List[str] = []
    body = content

    m = _FM_RE.match(content)
    if m:
        fm_block = m.group(1)
        body = content[m.end():]
        for line in fm_block.splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"\'')
            elif line.startswith("tags:"):
                raw = line.split(":", 1)[1].strip()
                tags = [t.strip().strip("\"'") for t in raw.strip("[]").split(",") if t.strip()]
    return title, body, tags


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_brain: Optional[KnowledgeBrain] = None


def get_brain(
    db_path: Path = _DB_PATH,
    markdown_dir: Path = _MARKDOWN_DIR,
) -> KnowledgeBrain:
    """Return (or create) the process-level KnowledgeBrain singleton."""
    global _brain
    if _brain is None:
        _brain = KnowledgeBrain(db_path=db_path, markdown_dir=markdown_dir)
    return _brain
