"""
Trancendos tateking — Video Creation & Editing Platform
========================================================
Video project management, FFmpeg job scheduling, clip metadata store.
Zero-cost: FFmpeg integration (must be installed), no paid video APIs.

Port: 8066  Entity: TateKing  Lead AI: Benji Tate (+ Sam King)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from Dimensional.path_validation import PathTraversalError, safe_join
from Dimensional.service_auth_fastapi import guard_internal_secret

WORKER_PORT = int(os.getenv("PORT") or "8066")
WORKER_NAME = "tateking"
# Env-overridable, matching `VAULT_DB_PATH` and the other workers. Not
# cosmetic: these two lines run at IMPORT, so anything that imports this module
# -- the test suite included -- created `workers/tateking/data/media/` inside
# the checkout. A test that writes into the repository to prove a containment
# guard works is not a contained test. Reported by cubic on PR #1150.
DB_PATH = Path(os.getenv("TATEKING_DB_PATH") or Path(__file__).parent / "data" / "tateking.db")
MEDIA_DIR = Path(os.getenv("TATEKING_MEDIA_DIR") or Path(__file__).parent / "data" / "media")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _contained_media(raw: str) -> Path:
    r"""Resolve a clip's `file_path` to somewhere inside this worker's media root.

    SEC-012. `py/command-line-injection`, CodeQL security-severity 9.8 -- the
    highest score in the estate's SARIF -- at the `subprocess.run(cmd)` in
    `run_ffmpeg_job`. `shell=False` and a list argv, so there is no shell to
    inject into; what is injected is an *argument*, and it is the input file:

        POST /clips  {"title": "x", "file_path": "/etc/passwd"}
        POST /jobs   {"clip_id": <that>, "operation": "extract_audio"}
        POST /jobs/<id>/run

    `ClipIn.file_path` is a free-form `Optional[str]` on a JSON body. It went to
    SQLite unexamined and came back out as `ffmpeg -i <input_path>`. The only
    check between the two was `Path(input_path).exists()`, which is a check that
    the attacker's chosen file is *there* -- the opposite of a containment
    check. Any file on the host that ffmpeg can decode could be transcoded into
    the served media directory and fetched; any it cannot gets up to 1000 bytes
    of ffmpeg's stderr returned in the 500 body.

    Containment is the fix, not a denylist of bad paths, and `safe_join` from
    the shared core is the same helper SEC-009 used for storage-service --
    deliberately, because a second copy of a path validator is a second thing to
    keep right. It rejects `..`, NUL, and absolute components, then confirms the
    resolved path is under the base, which also resolves symlinks planted inside
    the root.

    Absolute paths that are ALREADY under the media root are accepted and
    rewritten as relative before the join, because that is a shape existing rows
    legitimately have -- refusing it would have made the guard a breaking change
    dressed as a security fix. Everything else is refused.

    A resolved path is also always absolute, which closes the other half of an
    argument-injection worry for free: no value reaching argv can begin with `-`
    and be read by ffmpeg as an option.
    """
    if not raw or not raw.strip():
        raise ValueError("empty clip file_path")
    root = MEDIA_DIR.resolve()
    candidate = Path(raw)
    if candidate.is_absolute():
        # LEXICALLY relative, with no `.resolve()` on the raw value. The first
        # version of this guard wrote `candidate.resolve().relative_to(root)`,
        # and CodeQL kept reporting `py/path-injection` here -- correctly. The
        # containment verdict was right, but `resolve()` is a filesystem
        # operation performed ON the attacker's string before anything has
        # checked it, so the fix for a path-injection alert contained a path
        # expression built from uncontrolled data. Reported by cubic and by
        # CodeQL itself on PR #1150.
        #
        # Nothing is lost by dropping it, and that was measured rather than
        # assumed: `safe_join` resolves the JOINED path and re-checks
        # containment, so every case still lands the same way -- including a
        # symlink planted inside the root and pointing out of it, which is the
        # one people expect the early `resolve()` to be carrying.
        #
        # One behaviour does narrow, deliberately: a path outside the root that
        # merely symlinks back in is now refused. Accepting an arbitrary
        # filesystem path because of where it happens to point is not a
        # property worth keeping.
        try:
            parts = candidate.relative_to(root).parts
        except ValueError:
            raise PathTraversalError(
                f"clip file_path is outside the media root: {raw!r} is not under {root}"
            ) from None
    else:
        parts = candidate.parts
    if not parts:
        raise PathTraversalError(f"clip file_path names the media root itself: {raw!r}")
    return safe_join(root, *parts)


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

ALLOWED_FFMPEG_OPS = {
    "convert": "Convert video format",
    "trim": "Trim video to start/end timestamps",
    "compress": "Compress video (reduce file size)",
    "extract_audio": "Extract audio track",
    "thumbnail": "Extract thumbnail at timestamp",
    "concat": "Concatenate video files",
    "resize": "Resize video resolution",
}


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'draft',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS clips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER,
                title       TEXT NOT NULL,
                file_path   TEXT,
                source_url  TEXT,
                duration_s  REAL,
                resolution  TEXT,
                format      TEXT,
                file_size   INTEGER DEFAULT 0,
                tags        TEXT DEFAULT '[]',
                added_at    REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id     INTEGER,
                project_id  INTEGER,
                operation   TEXT NOT NULL,
                params      TEXT DEFAULT '{}',
                status      TEXT DEFAULT 'pending',
                output_path TEXT,
                error       TEXT,
                duration_ms INTEGER,
                created_at  REAL NOT NULL,
                completed_at REAL,
                FOREIGN KEY(clip_id) REFERENCES clips(id)
            );
            CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ffmpeg_ok = _ffmpeg_available()
    logger.info(
        "%s starting on port %d — FFmpeg: %s",
        WORKER_NAME,
        WORKER_PORT,
        "available" if ffmpeg_ok else "NOT FOUND",
    )
    yield


app = FastAPI(title="TateKing — Video Platform", version="1.0.0", lifespan=lifespan)
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


class ProjectIn(BaseModel):
    title: str
    description: Optional[str] = None
    created_by: str = "system"


class ClipIn(BaseModel):
    title: str
    project_id: Optional[int] = None
    source_url: Optional[str] = None
    file_path: Optional[str] = None
    duration_s: Optional[float] = None
    resolution: Optional[str] = None
    format: Optional[str] = None
    tags: list[str] = []


class FFmpegJobIn(BaseModel):
    clip_id: int
    operation: str
    params: dict = {}


@_router.get("/health")
async def health():
    with get_conn() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {
            "name": "TateKing",
            "lead_ai": "Benji Tate",
            "lead_ais": ["Benji Tate", "Sam King"],
        },
        "ffmpeg_available": _ffmpeg_available(),
        "projects": projects,
        "clips": clips,
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


@_router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (title, description, created_by, created_at, updated_at) VALUES (?,?,?,?,?)",
            (body.title, body.description, body.created_by, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/projects")
async def list_projects(
    limit: int = Query(50, le=500), x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@_router.post("/clips", status_code=201)
async def add_clip(body: ClipIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    # SEC-012. Refuse at the boundary, loudly, so the caller learns why rather
    # than discovering it when a job they queued fails. `run_ffmpeg_job` checks
    # again with the same function: this is the message, that is the guarantee.
    if body.file_path:
        try:
            _contained_media(body.file_path)
        except (PathTraversalError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"file_path must name a file inside the media root: {exc}",
            ) from None
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO clips (project_id, title, source_url, file_path, duration_s, resolution, format, tags, added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                body.project_id,
                body.title,
                body.source_url,
                body.file_path,
                body.duration_s,
                body.resolution,
                body.format,
                json.dumps(body.tags),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM clips WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/clips")
async def list_clips(
    project_id: Optional[int] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if project_id:
        clauses.append("project_id=?")
        params.append(project_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM clips {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.post("/jobs", status_code=201)
async def create_ffmpeg_job(body: FFmpegJobIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.operation not in ALLOWED_FFMPEG_OPS:
        raise HTTPException(
            status_code=400, detail=f"Unknown operation. Allowed: {list(ALLOWED_FFMPEG_OPS)}"
        )
    now = time.time()
    with get_conn() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id=?", (body.clip_id,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        cur = conn.execute(
            "INSERT INTO jobs (clip_id, project_id, operation, params, status, created_at) VALUES (?,?,?,?,?,?)",
            (
                body.clip_id,
                clip["project_id"],
                body.operation,
                json.dumps(body.params),
                "queued",
                now,
            ),
        )
        conn.commit()
        job_id = cur.lastrowid
    return {
        "id": job_id,
        "clip_id": body.clip_id,
        "operation": body.operation,
        "status": "queued",
        "created_at": now,
        "note": "FFmpeg job queued. Execute via POST /jobs/{id}/run",
    }


@_router.post("/jobs/{job_id}/run")
async def run_ffmpeg_job(job_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="FFmpeg not available — install ffmpeg")
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        clip = conn.execute("SELECT * FROM clips WHERE id=?", (job["clip_id"],)).fetchone()

    op = job["operation"]
    params = json.loads(job["params"])
    # Re-derived here and not trusted from the row. The boundary check on
    # `POST /clips` is the loud refusal; this is the structural one, because the
    # database is not a trust boundary -- rows predate the boundary check, and a
    # future writer to `clips` would not inherit it.
    raw_path = clip["file_path"] if clip["file_path"] else None
    input_path = None
    if raw_path:
        try:
            input_path = str(_contained_media(raw_path))
        except (PathTraversalError, ValueError) as exc:
            logger.warning("tateking refused a clip path outside the media root: %s", exc)
            with get_conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='failed', error=? WHERE id=?",
                    ("Input file outside media root", job_id),
                )
                conn.commit()
            raise HTTPException(
                status_code=400, detail="Clip file_path is outside the media root"
            ) from None

    if not input_path or not Path(input_path).exists():
        with get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error=? WHERE id=?",
                ("Input file not found", job_id),
            )
            conn.commit()
        raise HTTPException(status_code=400, detail="Clip file_path not found on disk")

    # `int(job_id)` where `job_id: int` already is one. Not superstition: this
    # is the OTHER flow in this function, and the one still reported as
    # `py/command-line-injection` 9.8 after SEC-012 cleared the input-path flow
    # it targeted. CodeQL traces `job_id` -> `output_path` -> `cmd` ->
    # `subprocess.run` and does not model FastAPI's coercion of a declared `int`
    # path parameter, so it sees a request value reaching argv.
    #
    # Not exploitable — FastAPI answers 422 to anything that is not an integer,
    # so no separator, no leading `-`, nothing. But an explicit `int()` costs
    # one call, states the invariant at the point it matters instead of five
    # frames up in a decorator, and is a conversion the scanner can see. A
    # guard only the framework knows about is one the next reader has to take
    # on trust.
    output_path = str(MEDIA_DIR / f"job_{int(job_id)}_output")
    start = time.time()
    cmd = None

    # Sanitise all user-supplied FFmpeg params before use in subprocess argv.
    # Timestamps must match HH:MM:SS or plain seconds; CRF and dimensions are ints.
    import re as _re

    _TS_RE = _re.compile(r"^[\d:.]+$")

    def _safe_ts(val: str, default: str) -> str:
        v = str(val)
        return v if _TS_RE.match(v) else default

    def _safe_int(val, default: int, lo: int, hi: int) -> int:
        try:
            v = int(val)
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return default

    if op == "thumbnail":
        ts = _safe_ts(params.get("timestamp", "00:00:01"), "00:00:01")
        output_path += ".jpg"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-ss", ts, "-vframes", "1", output_path]
    elif op == "extract_audio":
        output_path += ".mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            output_path,
        ]
    elif op == "compress":
        output_path += ".mp4"
        crf = str(_safe_int(params.get("crf", 28), 28, 0, 51))
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vcodec",
            "libx264",
            "-crf",
            crf,
            output_path,
        ]
    elif op == "trim":
        start_t = _safe_ts(params.get("start", "0"), "0")
        end_t = _safe_ts(params.get("end", "10"), "10")
        output_path += ".mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-ss",
            start_t,
            "-to",
            end_t,
            "-c",
            "copy",
            output_path,
        ]
    elif op == "resize":
        w = _safe_int(params.get("width", 1280), 1280, 1, 7680)
        h = _safe_int(params.get("height", 720), 720, 1, 4320)
        output_path += ".mp4"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"scale={w}:{h}", output_path]
    else:
        raise HTTPException(status_code=400, detail=f"FFmpeg command not implemented for: {op}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, shell=False)
        duration_ms = int((time.time() - start) * 1000)
        if result.returncode == 0:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='completed', output_path=?, duration_ms=?, completed_at=? WHERE id=?",
                    (output_path, duration_ms, time.time(), job_id),
                )
                conn.commit()
            return {
                "job_id": job_id,
                "status": "completed",
                "output_path": output_path,
                "duration_ms": duration_ms,
            }
        else:
            err = result.stderr[-1000:]
            with get_conn() as conn:
                conn.execute("UPDATE jobs SET status='failed', error=? WHERE id=?", (err, job_id))
                conn.commit()
            raise HTTPException(status_code=500, detail=f"FFmpeg failed: {err}")
    except subprocess.TimeoutExpired as exc:
        with get_conn() as conn:
            conn.execute("UPDATE jobs SET status='failed', error='Timeout' WHERE id=?", (job_id,))
            conn.commit()
        raise HTTPException(status_code=408, detail="FFmpeg job timed out") from exc


@_router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/operations")
async def list_operations(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return {"operations": [{"name": k, "description": v} for k, v in ALLOWED_FFMPEG_OPS.items()]}


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
