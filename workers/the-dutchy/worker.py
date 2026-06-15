"""
Trancendos the-dutchy — Intelligence & Market Analysis
======================================================
RSS/news ingestion, trend scoring, market intelligence reports.
Zero-cost: feedparser for RSS, no paid news APIs.

Port: 8061  Entity: The Dutchy  Lead AI: Predictive lore
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8061
WORKER_NAME = "the-dutchy"
DB_PATH = Path(__file__).parent / "data" / "dutchy.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

# Default free RSS feeds for market intelligence
DEFAULT_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "tech"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "category": "tech"},
    {
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "category": "business",
    },
    {
        "name": "BBC Technology",
        "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "category": "tech",
    },
]

# Trend keywords and weights for scoring
TREND_KEYWORDS = {
    "ai": 2.0,
    "machine learning": 1.8,
    "artificial intelligence": 2.0,
    "blockchain": 1.5,
    "crypto": 1.3,
    "quantum": 1.7,
    "startup": 1.2,
    "funding": 1.4,
    "acquisition": 1.5,
    "ipo": 1.6,
    "gdpr": 1.2,
    "regulation": 1.1,
    "compliance": 1.0,
    "cloud": 1.1,
    "saas": 1.2,
    "api": 1.0,
    "security": 1.3,
    "breach": 1.5,
    "vulnerability": 1.4,
    "market": 1.0,
    "revenue": 1.1,
    "growth": 1.2,
    "decline": 1.1,
}


def score_article(title: str, summary: str) -> float:
    """Score article relevance/trend weight."""
    text = (title + " " + summary).lower()
    score = 0.0
    for kw, weight in TREND_KEYWORDS.items():
        if kw in text:
            score += weight
    return round(min(score, 10.0), 2)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feeds (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                url         TEXT UNIQUE NOT NULL,
                category    TEXT DEFAULT 'general',
                active      INTEGER DEFAULT 1,
                last_fetched REAL,
                article_count INTEGER DEFAULT 0,
                added_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                url         TEXT UNIQUE,
                summary     TEXT,
                author      TEXT,
                published_at REAL,
                fetched_at  REAL NOT NULL,
                trend_score REAL DEFAULT 0.0,
                category    TEXT,
                tags        TEXT DEFAULT '[]',
                FOREIGN KEY(feed_id) REFERENCES feeds(id)
            );
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                category    TEXT,
                content     TEXT NOT NULL,
                article_ids TEXT DEFAULT '[]',
                generated_at REAL NOT NULL,
                generated_by TEXT DEFAULT 'system'
            );
            CREATE INDEX IF NOT EXISTS idx_articles_feed ON articles(feed_id);
            CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(trend_score DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_ts ON articles(fetched_at);
        """)
        # Seed default feeds
        for feed in DEFAULT_FEEDS:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO feeds (name, url, category, added_at) VALUES (?,?,?,?)",
                    (feed["name"], feed["url"], feed["category"], time.time()),
                )
            except Exception:
                pass
        conn.commit()


async def _fetch_feed(feed_id: int, feed_url: str, feed_category: str) -> dict:
    """Fetch and parse an RSS feed, store articles."""
    try:
        import feedparser

        parsed = feedparser.parse(feed_url)
    except ImportError:
        # Fallback: minimal HTTP fetch
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(feed_url)
                resp.raise_for_status()
            return {"fetched": 0, "error": "feedparser not installed, raw fetch only"}
        except Exception as exc:
            return {"fetched": 0, "error": str(exc)}

    now = time.time()
    inserted = 0
    with get_conn() as conn:
        for entry in parsed.entries[:50]:
            title = entry.get("title", "")[:500]
            url = entry.get("link", "")[:1000]
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:2000]
            author = entry.get("author", "")[:200]
            pub_struct = entry.get("published_parsed")
            pub_ts = time.mktime(pub_struct) if pub_struct else now
            trend = score_article(title, summary)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO articles (feed_id, title, url, summary, author, published_at, fetched_at, trend_score, category) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        feed_id,
                        title,
                        url or None,
                        summary,
                        author,
                        pub_ts,
                        now,
                        trend,
                        feed_category,
                    ),
                )
                inserted += 1
            except Exception:
                pass
        conn.execute(
            "UPDATE feeds SET last_fetched=?, article_count=article_count+? WHERE id=?",
            (now, inserted, feed_id),
        )
        conn.commit()
    return {"fetched": inserted}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="The Dutchy — Market Intelligence", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class FeedIn(BaseModel):
    name: str
    url: str
    category: str = "general"


class ReportIn(BaseModel):
    title: str
    category: Optional[str] = None
    content: str
    article_ids: list[int] = []
    generated_by: str = "system"


@_router.get("/health")
async def health():
    with get_conn() as conn:
        feeds = conn.execute("SELECT COUNT(*) FROM feeds WHERE active=1").fetchone()[0]
        articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Dutchy", "lead_ai": "Predictive lore"},
        "active_feeds": feeds,
        "total_articles": articles,
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.get("/feeds")
async def list_feeds(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM feeds ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@_router.post("/feeds", status_code=201)
async def add_feed(body: FeedIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO feeds (name, url, category, added_at) VALUES (?,?,?,?)",
                (body.name, body.url, body.category, now),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": body.name, "url": body.url}
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Feed URL already exists") from exc


@_router.post("/feeds/{feed_id}/fetch")
async def fetch_feed(
    feed_id: int, background_tasks: BackgroundTasks, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        feed = conn.execute("SELECT * FROM feeds WHERE id=?", (feed_id,)).fetchone()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    background_tasks.add_task(_fetch_feed, feed_id, feed["url"], feed["category"])
    return {"feed_id": feed_id, "status": "fetching"}


@_router.post("/fetch/all")
async def fetch_all_feeds(
    background_tasks: BackgroundTasks, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        feeds = conn.execute("SELECT * FROM feeds WHERE active=1").fetchall()
    for feed in feeds:
        background_tasks.add_task(_fetch_feed, feed["id"], feed["url"], feed["category"])
    return {"fetching": len(feeds)}


@_router.get("/articles")
async def list_articles(
    category: Optional[str] = None,
    min_score: Optional[float] = None,
    since: Optional[float] = None,
    q: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if category:
        clauses.append("category=?")
        params.append(category)
    if min_score is not None:
        clauses.append("trend_score>=?")
        params.append(min_score)
    if since:
        clauses.append("fetched_at>=?")
        params.append(since)
    if q:
        clauses.append("(title LIKE ? OR summary LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM articles {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM articles {where} ORDER BY trend_score DESC, fetched_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "articles": [dict(r) for r in rows]}


@_router.get("/trending")
async def trending_articles(
    hours: int = Query(24, le=168),
    limit: int = Query(20, le=100),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    since = time.time() - hours * 3600
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE fetched_at>=? ORDER BY trend_score DESC LIMIT ?",
            (since, limit),
        ).fetchall()
    return {"hours": hours, "count": len(rows), "articles": [dict(r) for r in rows]}


@_router.post("/reports", status_code=201)
async def create_report(body: ReportIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reports (title, category, content, article_ids, generated_at, generated_by) VALUES (?,?,?,?,?,?)",
            (
                body.title,
                body.category,
                body.content,
                json.dumps(body.article_ids),
                now,
                body.generated_by,
            ),
        )
        conn.commit()
    return {"id": cur.lastrowid, "title": body.title, "generated_at": now}


@_router.get("/reports")
async def list_reports(limit: int = Query(20, le=200), x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        by_category = conn.execute(
            "SELECT category, COUNT(*) c, AVG(trend_score) avg_score FROM articles GROUP BY category ORDER BY c DESC"
        ).fetchall()
        top_scoring = conn.execute(
            "SELECT title, trend_score FROM articles ORDER BY trend_score DESC LIMIT 5"
        ).fetchall()
    return {
        "total_articles": total_articles,
        "by_category": [dict(r) for r in by_category],
        "top_scoring": [dict(r) for r in top_scoring],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
