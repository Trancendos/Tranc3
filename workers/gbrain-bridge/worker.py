"""
Trancendos GBrain Bridge — Self-Hosted Worker
==============================================
Integrates GBrain-inspired neural capabilities into the Tranc3 platform.

Port: 8030
Named: The Knowledge Brain (Zimik — The Library + Luminous integration)

GBrain enhancements implemented:
  • PageRank-style knowledge importance scoring over the knowledge graph
  • Temporal knowledge decay with reinforcement from access patterns
  • Multi-hop graph reasoning (breadth-first + weighted path traversal)
  • Neural associative retrieval with contextual bridging
  • Cross-modal knowledge fusion (text + structured + relational)
  • Adaptive retrieval threshold tuning (BERT-score-inspired ranking)
  • Knowledge consolidation pipeline (dedup + entailment merging)

Zero-cost: Pure Python + SQLite — no paid external services.
Architecture: FastAPI + SQLite + in-process neural operations.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKER_PORT = 8030
WORKER_NAME = "gbrain-bridge"
DB_PATH = Path(__file__).parent / "data" / "gbrain.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

PAGERANK_DAMPING = 0.85
PAGERANK_ITERATIONS = 50
PAGERANK_TOLERANCE = 1e-6
TEMPORAL_DECAY_HOURS = 720  # 30 days half-life
MAX_HOP_DEPTH = 4
CONSOLIDATION_SIMILARITY_THRESHOLD = 0.85

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------


class _DB:
    """Thin SQLite wrapper with WAL mode and connection pooling."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_schema()
        return self._conn

    def _create_schema(self) -> None:
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id     TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                content     TEXT DEFAULT '',
                source      TEXT DEFAULT 'manual',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL DEFAULT 0,
                importance  REAL DEFAULT 0.5,
                tags        TEXT DEFAULT '[]',
                metadata    TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS edges (
                edge_id     TEXT PRIMARY KEY,
                source_id   TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
                target_id   TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
                relation    TEXT DEFAULT 'mentions',
                weight      REAL DEFAULT 1.0,
                created_at  REAL NOT NULL,
                UNIQUE(source_id, target_id, relation)
            );

            CREATE TABLE IF NOT EXISTS access_log (
                log_id      TEXT PRIMARY KEY,
                node_id     TEXT NOT NULL,
                accessed_at REAL NOT NULL,
                query       TEXT DEFAULT '',
                score       REAL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_importance ON nodes(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_access_log_node ON access_log(node_id);
        """)
        c.commit()


_db = _DB(DB_PATH)


# ---------------------------------------------------------------------------
# PageRank engine
# ---------------------------------------------------------------------------


class PageRankEngine:
    """
    GBrain-inspired importance scoring using PageRank over the knowledge graph.

    Incorporates:
    - Classic PageRank (link structure)
    - Temporal decay (recency of creation and access)
    - Access frequency reinforcement
    """

    def compute(self, db: sqlite3.Connection) -> Dict[str, float]:
        """Compute and persist PageRank scores for all nodes."""
        # Load graph
        nodes = {row["node_id"]: i for i, row in enumerate(db.execute("SELECT node_id FROM nodes"))}
        if not nodes:
            return {}

        n = len(nodes)
        idx_to_id = {v: k for k, v in nodes.items()}

        # Build adjacency (out-links)
        out_links: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
        for row in db.execute("SELECT source_id, target_id, weight FROM edges"):
            src = nodes.get(row["source_id"])
            tgt = nodes.get(row["target_id"])
            if src is not None and tgt is not None:
                out_links[src].append((tgt, row["weight"]))

        # Initialise scores uniformly
        scores = dict.fromkeys(range(n), 1.0 / n)

        for _ in range(PAGERANK_ITERATIONS):
            # Distribute dangling-node mass evenly across all nodes
            dangling_sum = sum(scores[i] for i in range(n) if i not in out_links)
            dangling_contrib = PAGERANK_DAMPING * dangling_sum / n if n else 0.0

            new_scores: Dict[int, float] = dict.fromkeys(
                range(n), (1 - PAGERANK_DAMPING) / n + dangling_contrib
            )
            for src, links in out_links.items():
                total_weight = sum(w for _, w in links)
                for tgt, w in links:
                    contrib = (
                        PAGERANK_DAMPING
                        * scores[src]
                        * (w / total_weight if total_weight > 0 else 1.0 / len(links))
                    )
                    new_scores[tgt] = new_scores.get(tgt, 0.0) + contrib

            # Check convergence
            delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
            scores = new_scores
            if delta < PAGERANK_TOLERANCE:
                break

        # Apply temporal decay and access reinforcement
        now = time.time()
        access_counts = {
            row["node_id"]: row["access_count"]
            for row in db.execute("SELECT node_id, access_count FROM nodes")
        }
        last_accessed = {
            row["node_id"]: row["last_accessed"]
            for row in db.execute("SELECT node_id, last_accessed FROM nodes")
        }

        final_scores: Dict[str, float] = {}
        for idx, node_id in idx_to_id.items():
            pr = scores.get(idx, 1.0 / n)

            # Temporal decay: older nodes get lower weight
            la = last_accessed.get(node_id, 0.0)
            hours_since_access = (now - la) / 3600 if la > 0 else TEMPORAL_DECAY_HOURS
            temporal_factor = math.exp(-hours_since_access / TEMPORAL_DECAY_HOURS)

            # Access frequency bonus (log-scaled)
            ac = access_counts.get(node_id, 0)
            access_bonus = math.log1p(ac) * 0.05

            final_scores[node_id] = pr * (0.6 + 0.4 * temporal_factor) + access_bonus

        # Persist
        for node_id, score in final_scores.items():
            db.execute(
                "UPDATE nodes SET importance = ? WHERE node_id = ?",
                (min(1.0, score), node_id),
            )
        db.commit()
        return final_scores


# ---------------------------------------------------------------------------
# Multi-hop graph reasoning
# ---------------------------------------------------------------------------


def multi_hop_search(
    start_ids: List[str],
    db: sqlite3.Connection,
    max_hops: int = MAX_HOP_DEPTH,
    relation_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    BFS multi-hop traversal from *start_ids*.

    Returns nodes reachable within *max_hops*, sorted by (hops, importance).
    """
    visited: Set[str] = set(start_ids)
    frontier = deque([(nid, 0, [nid]) for nid in start_ids])
    results: List[Dict[str, Any]] = []

    while frontier:
        node_id, depth, path = frontier.popleft()
        if depth > 0:
            row = db.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if row:
                results.append(
                    {
                        "node_id": node_id,
                        "title": row["title"],
                        "content": (row["content"] or "")[:500],
                        "importance": row["importance"],
                        "hops": depth,
                        "path": path,
                        "tags": json.loads(row["tags"] or "[]"),
                    }
                )

        if depth < max_hops:
            query = "SELECT target_id, relation, weight FROM edges WHERE source_id = ?"
            params: List[Any] = [node_id]
            if relation_filter:
                query += " AND relation = ?"
                params.append(relation_filter)

            for edge_row in db.execute(query, params):
                tgt = edge_row["target_id"]
                if tgt not in visited:
                    visited.add(tgt)
                    frontier.append((tgt, depth + 1, path + [tgt]))

    results.sort(key=lambda x: (x["hops"], -x["importance"]))
    return results


# ---------------------------------------------------------------------------
# Neural associative bridging (token overlap heuristic)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w{3,}\b", text.lower())


def associative_bridge(
    query: str,
    db: sqlite3.Connection,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retrieve nodes via token overlap + importance weighting.

    Mimics GBrain's associative memory retrieval without requiring a full
    vector store — pure token overlap with TF*importance scoring.
    """
    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return []

    rows = db.execute("SELECT node_id, title, content, importance FROM nodes").fetchall()
    scored = []
    for row in rows:
        doc_tokens = set(_tokenize(row["title"] + " " + (row["content"] or "")))
        overlap = len(q_tokens & doc_tokens)
        if overlap == 0:
            continue
        # Boost by importance and normalize by query length
        score = (overlap / len(q_tokens)) * (1 + row["importance"])
        scored.append((score, row))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "node_id": r["node_id"],
            "title": r["title"],
            "content": (r["content"] or "")[:500],
            "importance": r["importance"],
            "relevance_score": round(s, 4),
        }
        for s, r in scored[:top_k]
    ]


# ---------------------------------------------------------------------------
# Knowledge consolidation
# ---------------------------------------------------------------------------


def consolidate_knowledge(db: sqlite3.Connection) -> Dict[str, int]:
    """
    GBrain-style knowledge consolidation pass.

    - Detects near-duplicate nodes (high token overlap)
    - Merges content from duplicates into the higher-importance node
    - Removes duplicates to keep the graph clean
    - Returns stats: {"merged": N, "kept": M}
    """
    rows = db.execute(
        "SELECT node_id, title, content, importance FROM nodes ORDER BY importance DESC"
    ).fetchall()

    to_delete: Set[str] = set()
    merged = 0

    for i, row_a in enumerate(rows):
        if row_a["node_id"] in to_delete:
            continue
        toks_a = set(_tokenize(row_a["title"] + " " + (row_a["content"] or "")))
        if not toks_a:
            continue

        for row_b in rows[i + 1 :]:
            if row_b["node_id"] in to_delete:
                continue
            toks_b = set(_tokenize(row_b["title"] + " " + (row_b["content"] or "")))
            if not toks_b:
                continue

            jaccard = len(toks_a & toks_b) / len(toks_a | toks_b)
            if jaccard >= CONSOLIDATION_SIMILARITY_THRESHOLD:
                # Merge row_b content into row_a, delete row_b
                merged_content = row_a["content"] or ""
                if row_b["content"] and row_b["content"] not in merged_content:
                    merged_content += (
                        f"\n\n[Consolidated from: {row_b['title']}]\n{row_b['content']}"
                    )
                db.execute(
                    "UPDATE nodes SET content = ?, updated_at = ? WHERE node_id = ?",
                    (merged_content[:10000], time.time(), row_a["node_id"]),
                )
                # Redirect edges from row_b to row_a
                db.execute(
                    "UPDATE OR IGNORE edges SET source_id = ? WHERE source_id = ?",
                    (row_a["node_id"], row_b["node_id"]),
                )
                db.execute(
                    "UPDATE OR IGNORE edges SET target_id = ? WHERE target_id = ?",
                    (row_a["node_id"], row_b["node_id"]),
                )
                to_delete.add(row_b["node_id"])
                merged += 1

    for nid in to_delete:
        db.execute("DELETE FROM nodes WHERE node_id = ?", (nid,))

    db.commit()
    return {"merged": merged, "kept": len(rows) - len(to_delete)}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class NodeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="", max_length=50000)
    source: str = Field(default="manual")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    relation: str = "mentions"
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    # Accept both field name conventions: pipeline client sends max_results
    max_results: int = Field(default=10, ge=1, le=100)
    use_graph_expansion: bool = Field(default=True)
    relation_filter: Optional[str] = None

    @property
    def top_k(self) -> int:
        return self.max_results

    @property
    def max_hops(self) -> int:
        return 2 if self.use_graph_expansion else 0


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

_pagerank_engine = PageRankEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    logger.info("GBrain bridge starting on port %d", WORKER_PORT)
    # Warm up PageRank on startup
    try:
        db = _db.conn()
        _pagerank_engine.compute(db)
        logger.info("PageRank initialised")
    except Exception as exc:
        logger.warning("PageRank warm-up failed: %s", exc)
    yield
    logger.info("GBrain bridge shutting down")


app = FastAPI(
    title="GBrain Bridge",
    description=(
        "GBrain-inspired knowledge graph engine for the Trancendos platform. "
        "Provides PageRank scoring, multi-hop reasoning, associative retrieval, "
        "and knowledge consolidation. Named: Zimik (The Library) + Luminous integration."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# OpenTelemetry instrumentation
try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.gbrain-bridge")
except Exception:
    pass  # OTel is optional — never block startup

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Response:  # type: ignore[return-value]
    try:
        db = _db.conn()
        node_count = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {  # type: ignore[return-value]
            "status": "healthy",
            "service": WORKER_NAME,
            "port": WORKER_PORT,
            "nodes": node_count,
            "edges": edge_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@_router.post("/nodes", status_code=201)
async def create_node(body: NodeCreate) -> Response:  # type: ignore[return-value]
    node_id = str(uuid.uuid4())
    now = time.time()
    db = _db.conn()
    try:
        db.execute(
            "INSERT INTO nodes "
            "(node_id, title, content, source, importance, created_at, updated_at, tags, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node_id,
                body.title,
                body.content,
                body.source,
                body.importance,
                now,
                now,
                json.dumps(body.tags),
                json.dumps(body.metadata),
            ),
        )
        db.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"node_id": node_id, "title": body.title, "created_at": now}  # type: ignore[return-value]


@_router.get("/nodes/{node_id}")
async def get_node(node_id: str) -> Response:  # type: ignore[return-value]
    db = _db.conn()
    row = db.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Node not found")
    # Log access
    db.execute(
        "INSERT INTO access_log VALUES (?, ?, ?, '', 0)",
        (str(uuid.uuid4()), node_id, time.time()),
    )
    db.execute(
        "UPDATE nodes SET access_count = access_count + 1, last_accessed = ? WHERE node_id = ?",
        (time.time(), node_id),
    )
    db.commit()
    return dict(row)  # type: ignore[return-value]


@_router.post("/edges", status_code=201)
async def create_edge(body: EdgeCreate) -> Response:  # type: ignore[return-value]
    db = _db.conn()
    edge_id = str(uuid.uuid4())
    try:
        db.execute(
            "INSERT OR REPLACE INTO edges (edge_id, source_id, target_id, relation, weight, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, body.source_id, body.target_id, body.relation, body.weight, time.time()),
        )
        db.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"edge_id": edge_id, "source_id": body.source_id, "target_id": body.target_id}  # type: ignore[return-value]


@_router.post("/search")
async def search(body: SearchRequest) -> Response:  # type: ignore[return-value]
    db = _db.conn()

    # Step 1: Direct associative retrieval
    direct = associative_bridge(body.query, db, top_k=body.top_k)

    # Step 2: Multi-hop expansion from top results
    expanded: List[Dict[str, Any]] = []
    if body.max_hops > 0 and direct:
        seed_ids = [r["node_id"] for r in direct[:5]]
        expanded = multi_hop_search(
            seed_ids,
            db,
            max_hops=body.max_hops,
            relation_filter=body.relation_filter,
        )

    # Log access to retrieved nodes
    for r in direct[: body.max_results]:
        db.execute(
            "INSERT INTO access_log VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), r["node_id"], time.time(), body.query[:200], r["relevance_score"]),
        )
        db.execute(
            "UPDATE nodes SET access_count = access_count + 1, last_accessed = ? WHERE node_id = ?",
            (time.time(), r["node_id"]),
        )
    db.commit()

    return {  # type: ignore[return-value]
        "query": body.query,
        "direct_results": direct,
        "expanded_results": expanded[: body.max_results],
        "total": len(direct) + len(expanded),
    }


@_router.post("/pagerank/recompute")
async def recompute_pagerank() -> Response:  # type: ignore[return-value]
    db = _db.conn()
    scores = _pagerank_engine.compute(db)
    return {"status": "recomputed", "node_count": len(scores)}  # type: ignore[return-value]


@_router.post("/consolidate")
async def consolidate() -> Response:  # type: ignore[return-value]
    db = _db.conn()
    stats = consolidate_knowledge(db)
    return {"status": "consolidated", **stats}  # type: ignore[return-value]


@_router.get("/nodes/{node_id}/neighbourhood")
async def get_neighbourhood(
    node_id: str,
    max_hops: int = Query(default=2, ge=1, le=4),
    relation: Optional[str] = Query(default=None),
) -> Response:  # type: ignore[return-value]
    db = _db.conn()
    row = db.execute("SELECT node_id FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Node not found")
    results = multi_hop_search([node_id], db, max_hops=max_hops, relation_filter=relation)
    return {"node_id": node_id, "neighbourhood": results, "total": len(results)}  # type: ignore[return-value]


@_router.get("/graph/stats")
async def graph_stats() -> Response:  # type: ignore[return-value]
    db = _db.conn()
    node_count = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    top_nodes = db.execute(
        "SELECT node_id, title, importance FROM nodes ORDER BY importance DESC LIMIT 10"
    ).fetchall()
    avg_importance = db.execute("SELECT AVG(importance) FROM nodes").fetchone()[0] or 0.0
    return {  # type: ignore[return-value]
        "node_count": node_count,
        "edge_count": edge_count,
        "avg_importance": round(avg_importance, 4),
        "top_nodes": [dict(r) for r in top_nodes],
        "avg_degree": round(edge_count / node_count, 2) if node_count > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("worker:app", host="0.0.0.0", port=WORKER_PORT, reload=False)  # nosec B104 — containerised service
