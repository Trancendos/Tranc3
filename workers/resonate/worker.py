"""
Trancendos resonate — Empathy Engine
=====================================
Conversation empathy scoring and interpersonal communication analysis.
Zero-cost: keyword-based empathy signal detection, no external APIs.

Port: 8076  Entity: Resonate  Lead AI: Magdalena
"""

from __future__ import annotations

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

from Dimensional.service_auth_fastapi import guard_internal_secret

WORKER_PORT = int(os.environ.get("PORT", "8076"))
WORKER_NAME = "resonate"
DB_PATH = Path(__file__).parent / "data" / "resonate.db"
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

# Empathy signal lexicon (positive/negative)
EMPATHY_SIGNALS: dict[str, dict] = {
    "acknowledge": {
        "keywords": [
            "understand",
            "hear you",
            "feel",
            "know how",
            "appreciate",
            "recognize",
            "see that",
            "i get it",
            "makes sense to me",
            "i hear",
        ],
        "weight": 1.0,
        "polarity": "positive",
    },
    "validate": {
        "keywords": [
            "valid",
            "makes sense",
            "reasonable",
            "of course",
            "naturally",
            "that's fair",
            "understandable",
            "totally fair",
            "i can see why",
            "legitimate",
        ],
        "weight": 1.0,
        "polarity": "positive",
    },
    "support": {
        "keywords": [
            "here for you",
            "support",
            "help",
            "together",
            "with you",
            "got you",
            "care",
            "concerned",
            "by your side",
            "not alone",
        ],
        "weight": 1.0,
        "polarity": "positive",
    },
    "curiosity": {
        "keywords": [
            "tell me more",
            "how are you",
            "what happened",
            "can you share",
            "would you like",
            "how do you feel",
            "what's going on",
            "how so",
        ],
        "weight": 0.8,
        "polarity": "positive",
    },
    "dismissal": {
        "keywords": [
            "just",
            "simply",
            "calm down",
            "overreacting",
            "not a big deal",
            "move on",
            "forget it",
            "whatever",
            "get over it",
            "stop being",
        ],
        "weight": 1.5,
        "polarity": "negative",
    },
    "blame": {
        "keywords": [
            "your fault",
            "you always",
            "you never",
            "because of you",
            "you made",
            "you should have",
            "you caused",
            "fault of yours",
            "your problem",
        ],
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


# ---------------------------------------------------------------------------
# Response wrapping + human escalation
#
# Ported from src/resonate/empathy.py's Resonate class (2026-08-09) so this
# worker has genuine feature parity with the in-process router, not just
# scoring — the router's in-process mount stays authoritative for now (this
# is a safety-relevant path with live users; swapping the router to actually
# delegate here is a deliberate follow-up decision, not bundled into this
# change). Standalone by design, matching this worker's existing
# architecture (own SQLite DB, own INTERNAL_SECRET, no `src.*` imports —
# its Docker build context is `./workers/resonate`, not the repo root, so
# `src.observability.observatory` isn't importable here the way it is from
# workers that build with context `.`, e.g. infinity-ws). Escalations are
# durably recorded in this worker's own `escalations` table rather than
# Observatory's in-process ring buffer.
# ---------------------------------------------------------------------------

NOTIFICATIONS_URL = os.environ.get("NOTIFICATIONS_URL", "http://notifications:8008").rstrip("/")
# If set, escalations are dispatched as a real outbound webhook via the
# notifications worker's webhook channel — the only channel there with
# genuine pass/fail delivery semantics (every other channel is a zero-cost
# logging stub that always reports success, so it can't be used to justify
# telling a user "a human was notified").
_ESCALATION_WEBHOOK_URL = os.environ.get("RESONATE_ESCALATION_WEBHOOK_URL", "")

_EMPATHY_PREFIXES = [
    "I hear you, and what you're feeling is completely valid.",
    "Thank you for sharing that with me.",
    "That sounds genuinely difficult, and I want you to know you're not alone.",
    "I appreciate you trusting me with this.",
]

_VALIDATION_PHRASES = [
    "Your feelings matter.",
    "It's okay to not be okay.",
    "You're doing better than you think.",
    "Taking it one step at a time is enough.",
]


def wrap_response(
    response: str,
    sensitivity_level: str = "none",
    user_mood: Optional[int] = None,
    crisis_resources: bool = False,
) -> str:
    """Wrap an AI response with empathetic framing based on context. Returns
    the original response unchanged if no empathy wrapping is needed."""
    if sensitivity_level == "none" and (user_mood is None or user_mood >= 3):
        return response

    import random

    parts = []

    if sensitivity_level in ("critical", "high"):
        parts.append(
            random.choice(_EMPATHY_PREFIXES)
        )  # nosec B311 — non-cryptographic random usage
    elif sensitivity_level == "medium" or (user_mood is not None and user_mood <= 2):
        parts.append(
            random.choice(_EMPATHY_PREFIXES[:2])
        )  # nosec B311 — non-cryptographic empathy variation

    parts.append(response)

    if crisis_resources:
        parts.append(
            "\n\n---\n**If you're in crisis, please reach out:**\n"
            "- **UK**: Samaritans — 116 123 (free, 24/7)\n"
            "- **US**: 988 Suicide & Crisis Lifeline — call or text 988\n"
            "- **International**: [findahelpline.com](https://findahelpline.com)\n"
            "You don't have to face this alone. \U0001f499"
        )
    elif sensitivity_level in ("medium", "high"):
        parts.append(
            f"\n\n*{random.choice(_VALIDATION_PHRASES)}*"
        )  # nosec B311 — non-cryptographic phrase variation

    return "\n\n".join(p.strip() for p in parts if p.strip())


async def dispatch_escalation_notification(user_id: str, context: str) -> bool:
    """Best-effort real dispatch via the notifications worker. Never raises.

    Only returns True if RESONATE_ESCALATION_WEBHOOK_URL is configured and
    the notifications worker's webhook channel confirms genuine delivery
    (`{"ok": true}` in the response body). Without a configured webhook
    target there is no channel available with a real delivery guarantee, so
    this always returns False in that case rather than reporting a false
    positive.
    """
    if not _ESCALATION_WEBHOOK_URL:
        logger.warning(
            "resonate: no RESONATE_ESCALATION_WEBHOOK_URL configured — "
            "escalation cannot be confirmed delivered to a human"
        )
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            resp = await client.post(
                f"{NOTIFICATIONS_URL}/notifications/send",
                json={
                    "user_id": user_id,
                    "channel": "webhook",
                    "priority": "urgent",
                    "subject": "Resonate human escalation",
                    "body": context[:500],
                    "metadata": {
                        "source": "resonate",
                        "user_id": user_id,
                        "webhook_url": _ESCALATION_WEBHOOK_URL,
                    },
                },
                headers={"X-Internal-Secret": INTERNAL_SECRET},
            )
            return bool(resp.json().get("ok", False))
    except Exception as exc:
        logger.warning("resonate: notification dispatch failed: %s", exc)
        return False


async def escalate_to_human(user_id: str, context: str) -> dict:
    """Record a human-support escalation and attempt real dispatch. The
    returned message reflects what actually happened — it must never claim
    a human was notified unless dispatch genuinely succeeded, since this
    path is reached from crisis-support contexts."""
    logger.warning("resonate: human escalation triggered for user=%s", user_id)
    dispatched = await dispatch_escalation_notification(user_id, context)

    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO escalations (user_id, context_preview, notification_dispatched, escalated_at) "
            "VALUES (?,?,?,?)",
            (user_id, context[:500], int(dispatched), now),
        )
        conn.commit()

    if dispatched:
        return {
            "escalated": True,
            "escalated_at": now,
            "message": (
                "Your message has been flagged for urgent review by the support team. "
                "You are not alone."
            ),
        }
    return {
        "escalated": True,
        "escalated_at": now,
        "notification_dispatched": False,
        "message": (
            "Your message has been logged and flagged internally, but we could not "
            "confirm live delivery to a support team member right now. If you are in "
            "immediate danger, please contact emergency services or a crisis line "
            "directly — see the resources below."
        ),
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
            CREATE TABLE IF NOT EXISTS escalations (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id               TEXT NOT NULL,
                context_preview       TEXT,
                notification_dispatched INTEGER NOT NULL DEFAULT 0,
                escalated_at          REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_scores_user ON scores(user_id);
            CREATE INDEX IF NOT EXISTS idx_scores_conv ON scores(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_escalations_user ON escalations(user_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Resonate — Empathy Engine", version="1.0.0", lifespan=lifespan)
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
    try:
        guard_internal_secret(
            x_internal_secret, INTERNAL_SECRET, mismatch_status=401, detail="Unauthorized"
        )
    except HTTPException:
        _err_count += 1
        raise


class ScoreIn(BaseModel):
    text: str
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None
    store: bool = True


class ConversationScoreIn(BaseModel):
    messages: list[str]
    user_id: str = "anonymous"
    conversation_id: Optional[str] = None


class WrapIn(BaseModel):
    response: str
    sensitivity_level: str = "none"  # none|medium|high|critical
    user_mood: Optional[int] = None
    crisis_resources: bool = False


class EscalateIn(BaseModel):
    context: str = ""


@_router.get("/status")
async def status(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total_scored = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        total_escalations = conn.execute("SELECT COUNT(*) FROM escalations").fetchone()[0]
    return {
        "service": WORKER_NAME,
        "status": "active",
        "total_scored": total_scored,
        "total_escalations": total_escalations,
    }


@_router.post("/wrap")
async def wrap(body: WrapIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not body.response.strip():
        raise HTTPException(status_code=400, detail="response text is required")
    wrapped = wrap_response(
        response=body.response,
        sensitivity_level=body.sensitivity_level,
        user_mood=body.user_mood,
        crisis_resources=body.crisis_resources,
    )
    return {"wrapped_response": wrapped}


@_router.post("/escalate/{user_id}")
async def escalate(user_id: str, body: EscalateIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return await escalate_to_human(user_id=user_id, context=body.context)


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
                (
                    body.user_id,
                    body.conversation_id,
                    body.text[:500],
                    result["empathy_score"],
                    result["empathy_level"],
                    result["positive_score"],
                    result["negative_score"],
                    now,
                ),
            )
            score_id = cur.lastrowid
            if body.conversation_id:
                conv = conn.execute(
                    "SELECT * FROM conversations WHERE conversation_id=?", (body.conversation_id,)
                ).fetchone()
                if conv:
                    new_count = conv["message_count"] + 1
                    new_avg = (
                        conv["avg_empathy"] * conv["message_count"] + result["empathy_score"]
                    ) / new_count
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
async def score_conversation(
    body: ConversationScoreIn, x_internal_secret: str = Header(default="")
):
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
        conv = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id=?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = conn.execute(
            "SELECT * FROM scores WHERE conversation_id=? ORDER BY analysed_at ASC",
            (conversation_id,),
        ).fetchall()
    return {**dict(conv), "messages": [dict(m) for m in messages]}


@_router.get("/history/{user_id}")
async def user_history(
    user_id: str, limit: int = Query(50, le=500), x_internal_secret: str = Header(default="")
):
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

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
