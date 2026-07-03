"""
Trancendos imind — Sensitivity to Emotion Engine
================================================
Emotion detection from text using keyword sentiment analysis.
Zero-cost: no external NLP APIs, pure Python keyword matching.

Port: 8059  Entity: I-Mind  Lead AI: Elouise
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

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT") or "8059")
WORKER_NAME = "imind"
DB_PATH = Path(__file__).parent / "data" / "imind.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

# Emotion keyword lexicon (zero-cost alternative to VADER/spaCy)
EMOTION_LEXICON: dict[str, list[str]] = {
    "joy": [
        "happy",
        "joyful",
        "elated",
        "excited",
        "delighted",
        "wonderful",
        "amazing",
        "great",
        "fantastic",
        "love",
        "celebrate",
        "thrilled",
        "euphoric",
        "bliss",
        "cheerful",
    ],
    "sadness": [
        "sad",
        "unhappy",
        "depressed",
        "miserable",
        "grief",
        "sorrow",
        "cry",
        "tears",
        "heartbroken",
        "lonely",
        "hopeless",
        "despair",
        "gloomy",
        "melancholy",
        "devastated",
    ],
    "anger": [
        "angry",
        "furious",
        "rage",
        "hate",
        "annoyed",
        "frustrated",
        "outraged",
        "livid",
        "infuriated",
        "hostile",
        "bitter",
        "resent",
        "mad",
        "irate",
        "wrath",
    ],
    "fear": [
        "scared",
        "afraid",
        "terrified",
        "anxious",
        "worried",
        "nervous",
        "panic",
        "dread",
        "phobia",
        "horror",
        "alarmed",
        "frightened",
        "uneasy",
        "apprehensive",
        "trembling",
    ],
    "surprise": [
        "surprised",
        "shocked",
        "astonished",
        "amazed",
        "unexpected",
        "stunned",
        "wow",
        "incredible",
        "unbelievable",
        "astounding",
        "startled",
        "taken aback",
    ],
    "disgust": [
        "disgusting",
        "revolting",
        "gross",
        "repulsive",
        "nauseating",
        "awful",
        "horrible",
        "vile",
        "repugnant",
        "loathe",
        "detest",
        "abhor",
        "yuck",
        "sick",
    ],
    "trust": [
        "trust",
        "believe",
        "confident",
        "reliable",
        "honest",
        "loyal",
        "faithful",
        "secure",
        "certain",
        "dependable",
        "genuine",
        "sincere",
        "authentic",
    ],
    "anticipation": [
        "excited",
        "looking forward",
        "eager",
        "hopeful",
        "expect",
        "anticipate",
        "await",
        "prospect",
        "upcoming",
        "soon",
        "ready",
        "prepared",
    ],
}

INTENSIFIERS = {"very", "extremely", "incredibly", "absolutely", "totally", "completely", "deeply"}
NEGATORS = {"not", "never", "no", "neither", "nor", "barely", "hardly", "scarcely", "without"}


def detect_emotions(text: str) -> dict:
    """Analyse text and return emotion scores + dominant emotion."""
    words = re.findall(r"\b\w+\b", text.lower())
    scores: dict[str, float] = dict.fromkeys(EMOTION_LEXICON, 0.0)
    matched_words: dict[str, list[str]] = {emotion: [] for emotion in EMOTION_LEXICON}

    # Check negation context (simple window-based)
    negated_positions: set[int] = set()
    for i, w in enumerate(words):
        if w in NEGATORS:
            for j in range(i + 1, min(i + 4, len(words))):
                negated_positions.add(j)

    for i, word in enumerate(words):
        for emotion, keywords in EMOTION_LEXICON.items():
            if word in keywords:
                score = 1.0
                # Boost for intensifier nearby
                if i > 0 and words[i - 1] in INTENSIFIERS:
                    score = 1.5
                # Negate if in negation window
                if i in negated_positions:
                    score = -score * 0.5
                scores[emotion] += score
                if word not in matched_words[emotion]:
                    matched_words[emotion].append(word)

    total = sum(max(0, s) for s in scores.values())
    if total == 0:
        dominant = "neutral"
        normalised = dict.fromkeys(scores, 0.0)
        confidence = 0.0
    else:
        normalised = {e: round(max(0, s) / total, 4) for e, s in scores.items()}
        dominant = max(normalised, key=lambda e: normalised[e])
        confidence = round(normalised[dominant], 4)

    # Sentiment polarity
    positive_sum = sum(scores.get(e, 0) for e in ["joy", "trust", "anticipation", "surprise"])
    negative_sum = sum(abs(scores.get(e, 0)) for e in ["sadness", "anger", "fear", "disgust"])
    if positive_sum > negative_sum:
        sentiment = "positive"
        polarity = round(positive_sum / (positive_sum + negative_sum + 1e-6), 4)
    elif negative_sum > positive_sum:
        sentiment = "negative"
        polarity = round(-negative_sum / (positive_sum + negative_sum + 1e-6), 4)
    else:
        sentiment = "neutral"
        polarity = 0.0

    return {
        "dominant_emotion": dominant,
        "confidence": confidence,
        "sentiment": sentiment,
        "polarity": polarity,
        "emotion_scores": normalised,
        "matched_keywords": {e: kws for e, kws in matched_words.items() if kws},
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
            CREATE TABLE IF NOT EXISTS analyses (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT DEFAULT 'anonymous',
                text_snippet    TEXT NOT NULL,
                dominant_emotion TEXT NOT NULL,
                confidence      REAL,
                sentiment       TEXT,
                polarity        REAL,
                emotion_scores  TEXT,
                analysed_at     REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS emotion_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT UNIQUE NOT NULL,
                avg_polarity    REAL DEFAULT 0.0,
                dominant_emotion TEXT DEFAULT 'neutral',
                total_analyses  INTEGER DEFAULT 0,
                updated_at      REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
            CREATE INDEX IF NOT EXISTS idx_profiles_user ON emotion_profiles(user_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="I-Mind — Emotion Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class AnalyseIn(BaseModel):
    text: str
    user_id: str = "anonymous"
    store: bool = True


class BatchAnalyseIn(BaseModel):
    texts: list[str]
    user_id: str = "anonymous"


@_router.get("/health")
async def health():
    with get_conn() as conn:
        analyses = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        profiles = conn.execute("SELECT COUNT(*) FROM emotion_profiles").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "I-Mind", "lead_ai": "Elouise"},
        "total_analyses": analyses,
        "user_profiles": profiles,
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


@_router.post("/analyse")
async def analyse_text(body: AnalyseIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text required")
    result = detect_emotions(body.text)
    now = time.time()
    analysis_id = None
    if body.store:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO analyses (user_id, text_snippet, dominant_emotion, confidence, sentiment, polarity, emotion_scores, analysed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    body.user_id,
                    body.text[:500],
                    result["dominant_emotion"],
                    result["confidence"],
                    result["sentiment"],
                    result["polarity"],
                    json.dumps(result["emotion_scores"]),
                    now,
                ),
            )
            conn.commit()
            analysis_id = cur.lastrowid
            # Update profile
            profile = conn.execute(
                "SELECT * FROM emotion_profiles WHERE user_id=?", (body.user_id,)
            ).fetchone()
            if profile:
                new_total = profile["total_analyses"] + 1
                new_polarity = (
                    profile["avg_polarity"] * profile["total_analyses"] + result["polarity"]
                ) / new_total
                conn.execute(
                    "UPDATE emotion_profiles SET avg_polarity=?, dominant_emotion=?, total_analyses=?, updated_at=? WHERE user_id=?",
                    (
                        round(new_polarity, 4),
                        result["dominant_emotion"],
                        new_total,
                        now,
                        body.user_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO emotion_profiles (user_id, avg_polarity, dominant_emotion, total_analyses, updated_at) VALUES (?,?,?,?,?)",
                    (body.user_id, result["polarity"], result["dominant_emotion"], 1, now),
                )
            conn.commit()
    return {"analysis_id": analysis_id, "analysed_at": now, **result}


@_router.post("/analyse/batch")
async def analyse_batch(body: BatchAnalyseIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.texts:
        raise HTTPException(status_code=400, detail="texts required")
    if len(body.texts) > 100:
        raise HTTPException(status_code=400, detail="Max 100 texts per batch")
    results = []
    for text in body.texts:
        results.append({"text": text[:100], **detect_emotions(text)})
    return {"count": len(results), "results": results}


@_router.get("/profile/{user_id}")
async def get_profile(user_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        profile = conn.execute(
            "SELECT * FROM emotion_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        recent = conn.execute(
            "SELECT dominant_emotion, confidence, sentiment, polarity, analysed_at FROM analyses "
            "WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    return {**dict(profile), "recent_analyses": [dict(r) for r in recent]}


@_router.get("/history/{user_id}")
async def get_history(
    user_id: str, limit: int = Query(50, le=500), x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/emotions")
async def list_emotions(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return {
        "emotions": list(EMOTION_LEXICON.keys()),
        "keyword_counts": {e: len(kws) for e, kws in EMOTION_LEXICON.items()},
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
