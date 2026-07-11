"""
Trancendos the-academy — Learning Management System
====================================================
Courses, lessons, progress tracking, enrolment management.
Zero-cost: FastAPI + SQLite. No external LMS dependencies.

Port: 8056  Entity: The Academy  Lead AI: Shimshi
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT") or "8056")
WORKER_NAME = "the-academy"
DB_PATH = Path(__file__).parent / "data" / "academy.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS courses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                category    TEXT DEFAULT 'general',
                difficulty  TEXT DEFAULT 'beginner',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                published   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id   INTEGER NOT NULL,
                title       TEXT NOT NULL,
                content     TEXT,
                position    INTEGER DEFAULT 0,
                duration_min INTEGER DEFAULT 0,
                lesson_type TEXT DEFAULT 'text',
                created_at  REAL NOT NULL,
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );
            CREATE TABLE IF NOT EXISTS enrolments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                course_id   INTEGER NOT NULL,
                enrolled_at REAL NOT NULL,
                completed_at REAL,
                UNIQUE(user_id, course_id),
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );
            CREATE TABLE IF NOT EXISTS progress (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                lesson_id   INTEGER NOT NULL,
                course_id   INTEGER NOT NULL,
                completed   INTEGER DEFAULT 0,
                completed_at REAL,
                score       REAL,
                UNIQUE(user_id, lesson_id),
                FOREIGN KEY(lesson_id) REFERENCES lessons(id)
            );
            CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
            CREATE INDEX IF NOT EXISTS idx_enrol_user ON enrolments(user_id);
            CREATE INDEX IF NOT EXISTS idx_progress_user ON progress(user_id);
            CREATE TABLE IF NOT EXISTS badges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                description TEXT NOT NULL,
                criteria_type  TEXT NOT NULL,
                criteria_value REAL NOT NULL,
                reward_type TEXT NOT NULL DEFAULT 'badge',
                reward_description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS user_badges (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                badge_id   INTEGER NOT NULL,
                awarded_at REAL NOT NULL,
                course_id  INTEGER,
                UNIQUE(user_id, badge_id),
                FOREIGN KEY(badge_id) REFERENCES badges(id)
            );
            CREATE INDEX IF NOT EXISTS idx_user_badges_user ON user_badges(user_id);
        """)
        conn.commit()
        _seed_badges(conn)


# code, name, description, criteria_type, criteria_value, reward_type, reward_description
#
# `reward_type` ("badge" | "easter_egg" | "enhancement") is the machine-readable
# entitlement signal this worker *publishes* — earned rows are returned by
# `GET /users/{user_id}/badges`, and a downstream profile/recommendations surface
# is expected to consume `reward_type` to actually render a title or toggle a
# feature. This worker only records and exposes the entitlement; it does not
# itself own a profile-title or recommendation subsystem to flip. The
# `reward_description` text is therefore written to state what the user has
# *achieved* and what the entitlement grants once a consuming surface honors it,
# rather than asserting a title/feature has been switched on here and now.
_DEFAULT_BADGES = [
    (
        "first_steps",
        "First Steps",
        "Complete your first course.",
        "courses_completed",
        1,
        "badge",
        "",
    ),
    (
        "dedicated_learner",
        "Dedicated Learner",
        "Complete 5 courses.",
        "courses_completed",
        5,
        "easter_egg",
        "You've completed 5 courses — this grants the 'Veteran Learner' profile "
        "title (reward_type='easter_egg') for profile surfaces to display.",
    ),
    (
        "perfectionist",
        "Perfectionist",
        "Score 100% on a lesson.",
        "perfect_score",
        100,
        "badge",
        "",
    ),
    (
        "well_rounded",
        "Well Rounded",
        "Complete courses in 3 different categories.",
        "distinct_categories_completed",
        3,
        "enhancement",
        "You've completed courses across 3 categories — this grants a "
        "cross-category recommendations entitlement (reward_type='enhancement') "
        "for recommendation surfaces to honor.",
    ),
]


def _seed_badges(conn: sqlite3.Connection) -> None:
    # Upsert (not INSERT OR IGNORE) so that edits to a seed badge's text or
    # criteria in _DEFAULT_BADGES propagate to databases created before the
    # change on the next startup — otherwise a pre-existing row keeps returning
    # stale description/reward_description text forever. `badges.code` is the
    # UNIQUE key; the row id (and any user_badges FK to it) is preserved by the
    # UPDATE, so re-seeding never orphans awarded badges.
    for (
        code,
        name,
        description,
        criteria_type,
        criteria_value,
        reward_type,
        reward_desc,
    ) in _DEFAULT_BADGES:
        conn.execute(
            "INSERT INTO badges "
            "(code, name, description, criteria_type, criteria_value, reward_type, "
            "reward_description) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET "
            "name = excluded.name, description = excluded.description, "
            "criteria_type = excluded.criteria_type, criteria_value = excluded.criteria_value, "
            "reward_type = excluded.reward_type, reward_description = excluded.reward_description",
            (code, name, description, criteria_type, criteria_value, reward_type, reward_desc),
        )
    conn.commit()


def _check_and_award_badges(conn: sqlite3.Connection, user_id: str, now: float) -> list[dict]:
    """Evaluate every badge's criteria for `user_id` and award any not yet
    earned. Returns the list of newly-awarded badge dicts (empty if none)."""
    courses_completed = conn.execute(
        "SELECT COUNT(*) FROM enrolments WHERE user_id=? AND completed_at IS NOT NULL",
        (user_id,),
    ).fetchone()[0]
    best_score = conn.execute(
        "SELECT MAX(score) FROM progress WHERE user_id=? AND score IS NOT NULL",
        (user_id,),
    ).fetchone()[0]
    distinct_categories = conn.execute(
        "SELECT COUNT(DISTINCT c.category) FROM enrolments e "
        "JOIN courses c ON c.id = e.course_id "
        "WHERE e.user_id=? AND e.completed_at IS NOT NULL",
        (user_id,),
    ).fetchone()[0]

    metrics = {
        "courses_completed": courses_completed,
        "perfect_score": best_score or 0,
        "distinct_categories_completed": distinct_categories,
    }

    already_earned = {
        row["badge_id"]
        for row in conn.execute(
            "SELECT badge_id FROM user_badges WHERE user_id=?", (user_id,)
        ).fetchall()
    }

    newly_awarded = []
    for badge in conn.execute("SELECT * FROM badges").fetchall():
        if badge["id"] in already_earned:
            continue
        metric_value = metrics.get(badge["criteria_type"])
        if metric_value is None or metric_value < badge["criteria_value"]:
            continue
        # INSERT OR IGNORE + rowcount so a concurrent /progress request that
        # already awarded this badge (racing past the already_earned check
        # above) doesn't raise an unhandled IntegrityError → 500. Only count
        # the badge as "newly awarded" if this call actually inserted it.
        cur = conn.execute(
            "INSERT OR IGNORE INTO user_badges (user_id, badge_id, awarded_at, course_id) "
            "VALUES (?,?,?,NULL)",
            (user_id, badge["id"], now),
        )
        if cur.rowcount:
            newly_awarded.append(dict(badge))
    if newly_awarded:
        conn.commit()
    return newly_awarded


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="The Academy — LMS", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class CourseIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "general"
    difficulty: str = "beginner"
    created_by: str = "system"


class LessonIn(BaseModel):
    title: str
    content: Optional[str] = None
    position: int = 0
    duration_min: int = 0
    lesson_type: str = "text"


class EnrolIn(BaseModel):
    user_id: str
    course_id: int


class ProgressIn(BaseModel):
    user_id: str
    lesson_id: int
    score: Optional[float] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        enrolments = conn.execute("SELECT COUNT(*) FROM enrolments").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Academy", "lead_ai": "Shimshi"},
        "courses": courses,
        "enrolments": enrolments,
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


# --- Courses ---


@_router.post("/courses", status_code=201)
async def create_course(body: CourseIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses (title, description, category, difficulty, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (body.title, body.description, body.category, body.difficulty, body.created_by, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM courses WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/courses")
async def list_courses(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    published: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if category:
        clauses.append("category=?")
        params.append(category)
    if difficulty:
        clauses.append("difficulty=?")
        params.append(difficulty)
    if published is not None:
        clauses.append("published=?")
        params.append(int(published))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM courses {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM courses {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "courses": [dict(r) for r in rows]}


@_router.get("/courses/{course_id}")
async def get_course(course_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Course not found")
        lessons = conn.execute(
            "SELECT * FROM lessons WHERE course_id=? ORDER BY position", (course_id,)
        ).fetchall()
    return {**dict(row), "lessons": [dict(ln) for ln in lessons]}


@_router.patch("/courses/{course_id}/publish")
async def publish_course(course_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        conn.execute("UPDATE courses SET published=1 WHERE id=?", (course_id,))
        conn.commit()
    return {"course_id": course_id, "published": True}


# --- Lessons ---


@_router.post("/courses/{course_id}/lessons", status_code=201)
async def add_lesson(course_id: int, body: LessonIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM courses WHERE id=?", (course_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Course not found")
        cur = conn.execute(
            "INSERT INTO lessons (course_id, title, content, position, duration_min, lesson_type, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                course_id,
                body.title,
                body.content,
                body.position,
                body.duration_min,
                body.lesson_type,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM lessons WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


# --- Enrolments ---


@_router.post("/enrolments", status_code=201)
async def enrol(body: EnrolIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM courses WHERE id=?", (body.course_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Course not found")
        try:
            cur = conn.execute(
                "INSERT INTO enrolments (user_id, course_id, enrolled_at) VALUES (?,?,?)",
                (body.user_id, body.course_id, now),
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "user_id": body.user_id,
                "course_id": body.course_id,
                "enrolled_at": now,
            }
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT * FROM enrolments WHERE user_id=? AND course_id=?",
                (body.user_id, body.course_id),
            ).fetchone()
            return {**dict(row), "already_enrolled": True}


@_router.get("/enrolments")
async def list_enrolments(
    user_id: Optional[str] = None,
    course_id: Optional[int] = None,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if user_id:
        clauses.append("user_id=?")
        params.append(user_id)
    if course_id:
        clauses.append("course_id=?")
        params.append(course_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM enrolments {where} ORDER BY enrolled_at DESC", params
        ).fetchall()
    return [dict(r) for r in rows]


# --- Progress ---


@_router.post("/progress", status_code=201)
async def mark_progress(body: ProgressIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (body.lesson_id,)).fetchone()
        if not lesson:
            raise HTTPException(status_code=404, detail="Lesson not found")
        try:
            conn.execute(
                "INSERT INTO progress (user_id, lesson_id, course_id, completed, completed_at, score) VALUES (?,?,?,1,?,?)",
                (body.user_id, body.lesson_id, lesson["course_id"], now, body.score),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE progress SET completed=1, completed_at=?, score=? WHERE user_id=? AND lesson_id=?",
                (now, body.score, body.user_id, body.lesson_id),
            )
            conn.commit()
        # Check if course complete
        total_lessons = conn.execute(
            "SELECT COUNT(*) FROM lessons WHERE course_id=?", (lesson["course_id"],)
        ).fetchone()[0]
        completed_lessons = conn.execute(
            "SELECT COUNT(*) FROM progress WHERE user_id=? AND course_id=? AND completed=1",
            (body.user_id, lesson["course_id"]),
        ).fetchone()[0]
        if total_lessons > 0 and completed_lessons >= total_lessons:
            conn.execute(
                "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                (now, body.user_id, lesson["course_id"]),
            )
            conn.commit()
        # Re-evaluate badge criteria on every progress update, not just on
        # course completion — e.g. "Perfectionist" (a single 100% lesson
        # score) can be earned mid-course, before any course finishes.
        newly_awarded_badges = _check_and_award_badges(conn, body.user_id, now)
    return {
        "user_id": body.user_id,
        "lesson_id": body.lesson_id,
        "course_id": lesson["course_id"],
        "completed": True,
        "score": body.score,
        "course_progress_pct": round(completed_lessons / total_lessons * 100, 1)
        if total_lessons
        else 0,
        "newly_awarded_badges": _serialize_awarded(newly_awarded_badges),
    }


@_router.get("/progress/{user_id}")
async def get_user_progress(
    user_id: str, course_id: Optional[int] = None, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    clauses = ["user_id=?"]
    params: list = [user_id]
    if course_id:
        clauses.append("course_id=?")
        params.append(course_id)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM progress {where}", params).fetchall()
    return [dict(r) for r in rows]


# --- Badges & Achievements ---


@_router.get("/badges")
async def list_badges(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM badges ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@_router.get("/users/{user_id}/badges")
async def get_user_badges(user_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT b.code, b.name, b.description, b.reward_type, b.reward_description, "
            "ub.awarded_at FROM user_badges ub JOIN badges b ON b.id = ub.badge_id "
            "WHERE ub.user_id=? ORDER BY ub.awarded_at",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _serialize_awarded(badges: list[dict]) -> list[dict]:
    return [
        {
            "code": b["code"],
            "name": b["name"],
            "description": b["description"],
            "reward_type": b["reward_type"],
            "reward_description": b["reward_description"],
        }
        for b in badges
    ]


@_router.post("/users/{user_id}/badges/reevaluate")
async def reevaluate_user_badges(user_id: str, x_internal_secret: str = Header(default="")):
    """Re-run every badge criterion for one user and award any now-earned but
    not-yet-granted badges. Badge evaluation otherwise only happens on a
    /progress call, so a learner who completed courses *before* the badge
    feature existed (or before a new badge was added) would never receive
    their earned badges without this. Idempotent — already-earned badges are
    skipped by _check_and_award_badges."""
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        newly = _check_and_award_badges(conn, user_id, now)
    return {"user_id": user_id, "newly_awarded_badges": _serialize_awarded(newly)}


@_router.post("/badges/backfill")
async def backfill_all_badges(x_internal_secret: str = Header(default="")):
    """One-shot backfill across all existing learners — re-evaluates badge
    criteria for every user who has any enrolment or progress history, so a
    deploy of this feature retroactively grants badges historical completions
    already qualify for. Idempotent and safe to re-run."""
    _auth(x_internal_secret)
    now = time.time()
    awarded_by_user: dict[str, list[dict]] = {}
    with get_conn() as conn:
        user_rows = conn.execute(
            "SELECT user_id FROM enrolments UNION SELECT user_id FROM progress"
        ).fetchall()
        for row in user_rows:
            newly = _check_and_award_badges(conn, row["user_id"], now)
            if newly:
                awarded_by_user[row["user_id"]] = _serialize_awarded(newly)
    total = sum(len(v) for v in awarded_by_user.values())
    return {
        "users_evaluated": len(user_rows),
        "users_awarded": len(awarded_by_user),
        "badges_awarded": total,
        "awarded_by_user": awarded_by_user,
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
