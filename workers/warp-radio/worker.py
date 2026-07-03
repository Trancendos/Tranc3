"""
Trancendos warp-radio — Music & Audio Streaming Hub
====================================================
Playlist and stream metadata management.
Zero-cost: no streaming provider required. Manages metadata,
integrates with free sources (YouTube Music metadata, SoundCloud, etc.).

Port: 8057  Entity: Warp Radio  Lead AI: Rocking Ricki
"""

from __future__ import annotations

import json
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

WORKER_PORT = int(os.getenv("PORT", "8057"))
WORKER_NAME = "warp-radio"
DB_PATH = Path(__file__).parent / "data" / "radio.db"
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
            CREATE TABLE IF NOT EXISTS playlists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                owner       TEXT DEFAULT 'system',
                genre       TEXT DEFAULT 'mixed',
                is_public   INTEGER DEFAULT 1,
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                artist      TEXT,
                album       TEXT,
                duration_s  INTEGER DEFAULT 0,
                source_url  TEXT,
                source_type TEXT DEFAULT 'url',
                genre       TEXT,
                bpm         INTEGER,
                key_sig     TEXT,
                tags        TEXT DEFAULT '[]',
                added_by    TEXT DEFAULT 'system',
                added_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                track_id    INTEGER NOT NULL,
                position    INTEGER DEFAULT 0,
                added_at    REAL NOT NULL,
                UNIQUE(playlist_id, track_id),
                FOREIGN KEY(playlist_id) REFERENCES playlists(id),
                FOREIGN KEY(track_id)    REFERENCES tracks(id)
            );
            CREATE TABLE IF NOT EXISTS play_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id    INTEGER NOT NULL,
                playlist_id INTEGER,
                user_id     TEXT DEFAULT 'anonymous',
                played_at   REAL NOT NULL,
                duration_played_s INTEGER DEFAULT 0,
                FOREIGN KEY(track_id) REFERENCES tracks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pt_playlist ON playlist_tracks(playlist_id);
            CREATE INDEX IF NOT EXISTS idx_history_track ON play_history(track_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Warp Radio — Audio Hub", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class PlaylistIn(BaseModel):
    name: str
    description: Optional[str] = None
    owner: str = "system"
    genre: str = "mixed"
    is_public: bool = True


class TrackIn(BaseModel):
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    duration_s: int = 0
    source_url: Optional[str] = None
    source_type: str = "url"
    genre: Optional[str] = None
    bpm: Optional[int] = None
    key_sig: Optional[str] = None
    tags: list[str] = []
    added_by: str = "system"


class PlayEventIn(BaseModel):
    track_id: int
    playlist_id: Optional[int] = None
    user_id: str = "anonymous"
    duration_played_s: int = 0


@_router.get("/health")
async def health():
    with get_conn() as conn:
        playlists = conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]
        tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "Warp Radio", "lead_ai": "Rocking Ricki"},
        "playlists": playlists,
        "tracks": tracks,
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


@_router.post("/playlists", status_code=201)
async def create_playlist(body: PlaylistIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO playlists (name, description, owner, genre, is_public, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (body.name, body.description, body.owner, body.genre, int(body.is_public), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM playlists WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/playlists")
async def list_playlists(
    genre: Optional[str] = None,
    owner: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if genre:
        clauses.append("genre=?")
        params.append(genre)
    if owner:
        clauses.append("owner=?")
        params.append(owner)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM playlists {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM playlists {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "playlists": [dict(r) for r in rows]}


@_router.get("/playlists/{playlist_id}")
async def get_playlist(playlist_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Playlist not found")
        tracks = conn.execute(
            "SELECT t.*, pt.position FROM tracks t "
            "JOIN playlist_tracks pt ON t.id=pt.track_id "
            "WHERE pt.playlist_id=? ORDER BY pt.position",
            (playlist_id,),
        ).fetchall()
    return {**dict(row), "tracks": [dict(t) for t in tracks], "track_count": len(tracks)}


@_router.post("/tracks", status_code=201)
async def add_track(body: TrackIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tracks (title, artist, album, duration_s, source_url, source_type, genre, bpm, key_sig, tags, added_by, added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                body.title,
                body.artist,
                body.album,
                body.duration_s,
                body.source_url,
                body.source_type,
                body.genre,
                body.bpm,
                body.key_sig,
                json.dumps(body.tags),
                body.added_by,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/tracks")
async def list_tracks(
    genre: Optional[str] = None,
    artist: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if genre:
        clauses.append("genre=?")
        params.append(genre)
    if artist:
        clauses.append("artist=?")
        params.append(artist)
    if q:
        clauses.append("(title LIKE ? OR artist LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM tracks {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM tracks {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "tracks": [dict(r) for r in rows]}


@_router.post("/playlists/{playlist_id}/tracks")
async def add_track_to_playlist(
    playlist_id: int,
    payload: dict,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    track_id = payload.get("track_id")
    position = payload.get("position", 0)
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")
    now = time.time()
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position, added_at) VALUES (?,?,?,?)",
                (playlist_id, track_id, position, now),
            )
            conn.execute("UPDATE playlists SET updated_at=? WHERE id=?", (now, playlist_id))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Track already in playlist") from exc
    return {"playlist_id": playlist_id, "track_id": track_id, "position": position}


@_router.delete("/playlists/{playlist_id}/tracks/{track_id}", status_code=204)
async def remove_track_from_playlist(
    playlist_id: int, track_id: int, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?",
            (playlist_id, track_id),
        )
        conn.commit()


@_router.post("/play")
async def record_play(body: PlayEventIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO play_history (track_id, playlist_id, user_id, played_at, duration_played_s) VALUES (?,?,?,?,?)",
            (body.track_id, body.playlist_id, body.user_id, now, body.duration_played_s),
        )
        conn.commit()
    return {"track_id": body.track_id, "played_at": now}


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total_plays = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
        top_tracks = conn.execute(
            "SELECT t.title, t.artist, COUNT(*) plays FROM play_history h "
            "JOIN tracks t ON t.id=h.track_id "
            "GROUP BY h.track_id ORDER BY plays DESC LIMIT 10"
        ).fetchall()
    return {"total_plays": total_plays, "top_tracks": [dict(r) for r in top_tracks]}


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
