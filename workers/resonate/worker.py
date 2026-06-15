"""
Trancendos resonate — Empathy Engine
=====================================
Conversation empathy scoring and interpersonal communication analysis.
Zero-cost: keyword-based empathy signal detection, no external APIs.

Port: 8060  Entity: Resonate  Lead AI: Magdalena
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

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8060
WORKER_NAME = "resonate"
DB_PATH = Path(__file__).parent / "data" / "resonate.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

# Empathy signal lexicon (positive/negative)
EMPATHY_SIGNALS: dict[str, dict] = {
    "acknowledge": {
        "keywords": ["understand", "hear you", "feel", "know how", "appreciate", "recognize",
                     "see that", "i get it", "makes sense to me", "i hear"],
        "weight": 1.0,
        "polarity": "positive",
    },
    "validate": {
        "keywords": ["valid", "makes sense", "reasonable", "of course", "naturally", "that's fair",
                     "understandable", "totally fair", "i can see why", "legitimate"],
        "weight": 1.0,
        "polarity": "positive",
    },
    "support": {
        "keywords": ["here for you", "support", "help", "together", "with you", "got you",
                     "care", "concerned", "by your side", "not alone"],
        "weight": 1.0,
        "polarity": "positive",
    },
    "curiosity": {
        "keywords": ["tell me more", "how are you", "what happened", "can you share",
                     "would you like", "how do you feel", "what's going on", "how so"],
        "weight": 0.8,
        "polarity": "positive",
    },
    "dismissal": {
        "keywords": ["just", "simply", "calm down", "overreacting", "not a big deal", "move on",
                     "forget it", "whatever", "get over it", "stop being"],
        "weight": 1.5,
        "polarity": "negative",
    },
    "blame": {
        "keywords": ["your fault", "you always", "you never", "because of you", "you made",
                     "you should have", "you caused", "fault of yours", "your problem"],
        "weight": 1.5,
        "polarity": "negative",
    },
}


def score_empathy(text: str) -> dict:
    """Compute empathy score from -10 to 10 for a piece of text."""
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    phrase_text = lower  # for multi-word signals

    positive_hits: list[dict] = []
    negative_hits: list[dict] = []

    for signal_name, signal in EMPATHY_SIGNALS.items():
        found = []
        for kw in signal["keywords"]:
            if " " in kw:  # phrase match
                if kw in phrase_text:
                    found.append(kw)
            else:
                if kw in words:
                    found.append(kw)
        if found:
            hit = {"signal": signal_name, "keywords": found, "weight": signal["weight"]}
            if signal["polarity"] == "positive":
                positive_hits.append(hit)
            else:
                negative_hits.append(hit)

    positive_score = sum(h["weight"] * len(h["keywords"]) for h in positive_hits)
    negative_score = sum(h["weight"] * len(h["keywords"]) for h in negative_hits)

    raw = positive_score - negative_score
    # Clamp to -10..10
    empathy_score = round(max(-10, min(10, raw)), 2)

    if empathy_score >= 6:
        level = "highly_empathetic"
    elif empathy_score >= 3:
        level = "empathetic"
    elif empathy_score >= 0:
        level = "neutral"
    elif empathy_score >= -3:
        level = "low_empathy"
    else:
        level = "dismissive"

    return {
        "empathy_score": empathy_score,
        "empathy_level": level,
        "positive_signals": positive_hits,
        "negative_signals": negative_hits,
        "positive_score": round(positive_score, 2),
        "negative_score": round(negative_score, 2),
        "word_count": len(words),
    }


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT DEFAULT 'anonymous',
                conversation_id TEXT,
                text_snippet    TEXT NOT NULL,
                empathy_score   REAL NOT NULL,
                empathy_level   TEXT NOT NULL,
                positive_score  REAL,
                negative_score  REAL,
                analysed_at     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT UNIQUE NOT NULL,
                user_id         TEXT DEFAULT 'anonymous',
                avg_empathy     REAL DEFAULT 0.0,
                message_count   INTEGER DEFAULT 0,
                started_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_scores_user ON scores(user_id);
            CREATE INDEX IF NOT EXISTS idx_scores_conv ON scores(conversation_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Resonate — Empathy Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class ScoreIn(BaseModel):
    text: str
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None
    store: bool = True


class ConversationScoreIn(BaseModel):
    messages: list[str]
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "Resonate", "lead_ai": "Magdalena"},
        "total_scored": total,
        "conversations": convs,
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


@_router.post("/score")
async def score_text(body: ScoreIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text required")
    result = score_empathy(body.text)
    now = time.time()
    score_id = None
    if body.store:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO scores (user_id, conversation_id, text_snippet, empathy_score, empathy_level, positive_score, negative_score, analysed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (body.user_id, body.conversation_id, body.text[:500],
                 result["empathy_score"], result["empathy_level"],
                 result["positive_score"], result["negative_score"], now),
            )
            score_id = cur.lastrowid
            if body.conversation_id:
                conv = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id=?", (body.conversation_id,)
                ).fetchone()
                if conv:
                    new_count = conv["message_count"] + 1
                    new_avg = (conv["avg_empathy"] * conv["message_count"] + result["empathy_score"]) / new_count
                    conn.execute(
                        "UPDATE conversations SET avg_empathy=?, message_count=?, updated_at=? WHERE conversation_id=?",
                        (round(new_avg, 2), new_count, now, body.conversation_id),
                    )
                else:
                    conn.execute(
                        "INSERT INTO conversations (conversation_id, user_id, avg_empathy, message_count, started_at, updated_at) "
                        "VALUES (?,?,?,1,?,?)",
                        (body.conversation_id, body.user_id, result["empathy_score"], now, now),
                    )
            conn.commit()
    return {"score_id": score_id, "analysed_at": now, **result}


@_router.post("/score/conversation")
async def score_conversation(body: ConversationScoreIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages required")
    results = [score_empathy(msg) for msg in body.messages]
    avg_score = sum(r["empathy_score"] for r in results) / len(results)
    return {
        "conversation_id": body.conversation_id,
        "message_count": len(results),
        "avg_empathy_score": round(avg_score, 2),
        "messages": [{"text": body.messages[i][:100], **results[i]} for i in range(len(results))],
    }


@_router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
        if not conv: raise HTTPException(status_code=404, detail="Conversation not found")
        messages = conn.execute(
            "SELECT * FROM scores WHERE conversation_id=? ORDER BY analysed_at ASC",
            (conversation_id,),
        ).fetchall()
    return {**dict(conv), "messages": [dict(m) for m in messages]}


@_router.get("/history/{user_id}")
async def user_history(user_id: str, limit: int = Query(50, le=500),
                        x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scores WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
