"""
Trancendos imind — Sensitivity to Emotion Engine
================================================
Emotion detection from text using keyword sentiment analysis.
Zero-cost: no external NLP APIs, pure Python keyword matching.

Port: 8075  Entity: I-Mind  Lead AI: Elouise
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT") or "8075")
WORKER_NAME = "imind"
DB_PATH = Path(__file__).parent / "data" / "imind.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_internal_secret_raw = os.getenv("INTERNAL_SECRET")
if (
    not _internal_secret_raw
    or not _internal_secret_raw.strip()
    or _internal_secret_raw.strip() == "dev-secret"
):
    raise RuntimeError(
        "INTERNAL_SECRET is not set (or still the default). "
        "This worker cannot start without a strong unique internal secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
INTERNAL_SECRET: str = _internal_secret_raw.strip()

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


# ---------------------------------------------------------------------------
# Crisis / self-harm / mental-health sensitivity detection — SAFEGUARDING PATH
#
# Ported from src/imind/protocol.py's IMind.assess() (2026-08-09) — the
# in-process router's actual crisis-detection logic, which this worker never
# had (detect_emotions() above only does generic keyword sentiment scoring,
# with no crisis-pattern matching at all). The router's in-process mount
# stays authoritative for the live request-time gate for now — this is a
# safeguarding path with real users; swapping the router to actually
# delegate here is a deliberate follow-up decision, not bundled into this
# change. Standalone by design, matching this worker's existing
# architecture (own SQLite DB, own INTERNAL_SECRET, no `src.*` imports —
# its Docker build context is `./workers/imind`, not the repo root, so
# `src.observability.observatory` isn't importable here). CRITICAL/HIGH/
# MEDIUM assessments are durably recorded in this worker's own
# `sensitivity_assessments` table rather than Observatory's in-process ring
# buffer.
# ---------------------------------------------------------------------------

_CRISIS_PATTERNS = [
    re.compile(r"\b(suicide|suicidal|end my life|kill myself|want to die)\b", re.I),
    re.compile(r"\b(self[- ]harm|cut myself|hurt myself)\b", re.I),
    re.compile(r"\b(no reason to live|can't go on|give up on life)\b", re.I),
]

_MENTAL_HEALTH_PATTERNS = [
    re.compile(r"\b(depressed|depression|anxiety|anxious|panic attack|ptsd)\b", re.I),
    re.compile(r"\b(mental health|therapy|therapist|psychiatrist|medication for)\b", re.I),
]


def assess_sensitivity(text: str, actor: str | None = None) -> dict:
    """Crisis/self-harm/mental-health pattern scan. Returns the same shape
    as src/imind/protocol.py's SensitivityAssessment.to_dict()."""
    categories: list[str] = []
    level = "none"

    # Crisis detection — highest priority
    if _CRISIS_PATTERNS[0].search(text):
        categories.append("crisis")
        level = "critical"

    # Self-harm
    if "crisis" not in categories:
        for pat in _CRISIS_PATTERNS[1:]:
            if pat.search(text):
                categories.append("self_harm")
                level = "high"
                break

    # Mental health
    for pat in _MENTAL_HEALTH_PATTERNS:
        if pat.search(text):
            if "mental_health" not in categories:
                categories.append("mental_health")
            if level == "none":
                level = "medium"
            break

    escalate = level in ("critical", "high")

    modifier = ""
    if level == "critical":
        modifier = (
            "IMPORTANT: The user may be in crisis. Respond with empathy, "
            "provide crisis helpline numbers (UK: 116 123 Samaritans, "
            "US: 988 Suicide & Crisis Lifeline), and encourage professional help. "
            "Do not minimise their feelings."
        )
    elif level == "high":
        modifier = (
            "The user has mentioned self-harm. Respond with care and empathy. "
            "Provide mental health resources. Do not provide harmful information."
        )
    elif level == "medium":
        modifier = (
            "The user has mentioned mental health topics. "
            "Respond with warmth and empathy. Suggest professional support if appropriate."
        )

    assessment = {
        "id": str(uuid.uuid4()),
        "level": level,
        "categories": categories,
        "escalate": escalate,
        "response_modifier": modifier,
    }

    if level != "none":
        _record_assessment(assessment, actor)

    return assessment


def _record_assessment(assessment: dict, actor: str | None) -> None:
    """Durably persist a non-NONE assessment to this worker's own DB — there
    is no Observatory ring buffer reachable from this process. Never raises;
    a persistence failure must not block the caller from getting their
    assessment result back."""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO sensitivity_assessments "
                "(assessment_id, actor, level, categories, escalate, assessed_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    assessment["id"],
                    actor,
                    assessment["level"],
                    json.dumps(assessment["categories"]),
                    int(assessment["escalate"]),
                    time.time(),
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.error("imind: failed to persist sensitivity assessment: %s", exc)


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
            CREATE TABLE IF NOT EXISTS sensitivity_assessments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id   TEXT NOT NULL,
                actor           TEXT,
                level           TEXT NOT NULL,
                categories      TEXT,
                escalate        INTEGER NOT NULL DEFAULT 0,
                assessed_at     REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
            CREATE INDEX IF NOT EXISTS idx_profiles_user ON emotion_profiles(user_id);
            CREATE INDEX IF NOT EXISTS idx_assessments_level ON sensitivity_assessments(level);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="I-Mind — Emotion Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        ).split(",")
        if o.strip() and o.strip() != "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
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


class AssessIn(BaseModel):
    text: str
    actor: str | None = None


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


@_router.get("/status")
async def status(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total_assessments = conn.execute("SELECT COUNT(*) FROM sensitivity_assessments").fetchone()[
            0
        ]
        total_escalations = conn.execute(
            "SELECT COUNT(*) FROM sensitivity_assessments WHERE escalate=1"
        ).fetchone()[0]
    return {
        "service": WORKER_NAME,
        "status": "active",
        "total_assessments": total_assessments,
        "total_escalations": total_escalations,
    }


@_router.post("/assess")
async def assess(body: AssessIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text required")
    return assess_sensitivity(body.text, actor=body.actor)


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
