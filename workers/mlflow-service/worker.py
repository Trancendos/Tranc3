"""
Trancendos mlflow-service — Self-Hosted ML Experiment Tracking
===============================================================
MLflow-compatible experiment tracking for Turing's Hub (3D AI entity builder,
port 8035) and Luminous (AI brain, src/bio_neural/ + src/core/).

Architecture
------------
  Storage  : SQLite for run metadata + params/metrics/tags; local filesystem
             for artifact blobs (Parquet, model weights, plots).
  Protocol : MLflow REST API v2 (subset) — clients using mlflow.set_tracking_uri
             pointing to this service work without modification.
  Design   : Zero-cost self-hosted; no paid MLflow hosted service required.

Port: 8039 (reserved in CLAUDE.md self-hosted worker map)

Integrations
------------
  Turing's Hub  (port 8035) — logs per-entity build experiments: personality
                               matrix iterations, voice model tuning, memory
                               consolidation scores, 3D mesh quality metrics.
  Luminous      (src/bio_neural/) — logs neural architecture search, IIT
                               consciousness scores, training loss curves.

Endpoints (MLflow REST API compatible subset)
---------------------------------------------
  POST /api/2.0/mlflow/experiments/create
  GET  /api/2.0/mlflow/experiments/get
  GET  /api/2.0/mlflow/experiments/get-by-name
  GET  /api/2.0/mlflow/experiments/list
  POST /api/2.0/mlflow/runs/create
  POST /api/2.0/mlflow/runs/update
  POST /api/2.0/mlflow/runs/log-metric
  POST /api/2.0/mlflow/runs/log-batch
  POST /api/2.0/mlflow/runs/log-parameter
  POST /api/2.0/mlflow/runs/set-tag
  GET  /api/2.0/mlflow/runs/get
  POST /api/2.0/mlflow/runs/search
  GET  /api/2.0/mlflow/metrics/get-history
  POST /api/2.0/mlflow/artifacts/list
  PUT  /api/2.0/mlflow/artifacts/upload      (custom — not part of MLflow std)
  GET  /api/2.0/mlflow/artifacts/download    (custom)

Trancendos-native endpoints
----------------------------
  GET  /health
  GET  /experiments              shortcut listing
  GET  /runs/{run_id}/summary    human-readable run card
  POST /runs/compare             side-by-side metric comparison
  GET  /runs/leaderboard         best run per experiment ranked by metric
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from Dimensional.path_validation import PathTraversalError, list_validated_children, validate_path

# ── Configuration ──────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("MLFLOW_DATA_DIR", "/data/mlflow-service"))
DB_PATH = DATA_DIR / "mlflow.db"
ARTIFACT_ROOT = DATA_DIR / "artifacts"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")

logger = logging.getLogger("mlflow-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# ── Database ───────────────────────────────────────────────────────────────────

_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    db = _db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id   TEXT PRIMARY KEY,
            name            TEXT UNIQUE NOT NULL,
            artifact_location TEXT NOT NULL,
            lifecycle_stage TEXT NOT NULL DEFAULT 'active',
            creation_time   INTEGER NOT NULL,
            last_update_time INTEGER NOT NULL,
            tags            TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id          TEXT PRIMARY KEY,
            experiment_id   TEXT NOT NULL REFERENCES experiments(experiment_id),
            run_name        TEXT,
            status          TEXT NOT NULL DEFAULT 'RUNNING',
            start_time      INTEGER NOT NULL,
            end_time        INTEGER,
            artifact_uri    TEXT NOT NULL,
            lifecycle_stage TEXT NOT NULL DEFAULT 'active',
            user_id         TEXT,
            source_name     TEXT,
            source_type     TEXT,
            tags            TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS run_params (
            run_id  TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            key     TEXT NOT NULL,
            value   TEXT NOT NULL,
            PRIMARY KEY (run_id, key)
        );

        CREATE TABLE IF NOT EXISTS run_metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            key         TEXT NOT NULL,
            value       REAL NOT NULL,
            timestamp   INTEGER NOT NULL,
            step        INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_run_key ON run_metrics(run_id, key);

        CREATE TABLE IF NOT EXISTS run_tags (
            run_id  TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            key     TEXT NOT NULL,
            value   TEXT NOT NULL,
            PRIMARY KEY (run_id, key)
        );

        -- Default experiment (id "0") — created on init
        INSERT OR IGNORE INTO experiments
            (experiment_id, name, artifact_location, creation_time, last_update_time)
        VALUES ('0', 'Default', '/data/mlflow-service/artifacts/0',
                strftime('%s','now') * 1000,
                strftime('%s','now') * 1000);
    """)
    db.commit()
    logger.info("mlflow-service DB ready at %s", DB_PATH)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _run_to_dict(row: sqlite3.Row, db: sqlite3.Connection) -> Dict[str, Any]:
    """Return a run in MLflow REST API v2 format.

    The spec requires params, tags, and metrics as lists of {key, value[, ...]}
    objects — NOT as plain dicts.  Returning dicts breaks all mlflow client SDK
    parsing (mlflow.get_run(), mlflow.search_runs(), etc.).
    """
    run_id = row["run_id"]

    # params → list of {key, value}
    params_list = [
        {"key": r["key"], "value": r["value"]}
        for r in db.execute("SELECT key, value FROM run_params WHERE run_id = ?", (run_id,))
    ]

    # tags → list of {key, value}
    tags_list = [
        {"key": r["key"], "value": r["value"]}
        for r in db.execute("SELECT key, value FROM run_tags WHERE run_id = ?", (run_id,))
    ]

    # metrics → list of latest {key, value, step, timestamp} per key
    metrics_seen: set = set()
    metrics_list = []
    for r in db.execute(
        "SELECT key, value, step, timestamp FROM run_metrics "
        "WHERE run_id = ? ORDER BY step DESC, id DESC",
        (run_id,),
    ):
        if r["key"] not in metrics_seen:
            metrics_seen.add(r["key"])
            metrics_list.append(
                {
                    "key": r["key"],
                    "value": r["value"],
                    "step": r["step"],
                    "timestamp": r["timestamp"],
                }
            )

    return {
        "run_id": run_id,
        "experiment_id": row["experiment_id"],
        "run_name": row["run_name"],
        "status": row["status"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "artifact_uri": row["artifact_uri"],
        "lifecycle_stage": row["lifecycle_stage"],
        "user_id": row["user_id"],
        "params": params_list,
        "metrics": metrics_list,
        "tags": tags_list,
    }


def _experiment_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "experiment_id": row["experiment_id"],
        "name": row["name"],
        "artifact_location": row["artifact_location"],
        "lifecycle_stage": row["lifecycle_stage"],
        "creation_time": row["creation_time"],
        "last_update_time": row["last_update_time"],
        "tags": json.loads(row["tags"]),
    }


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class CreateExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    artifact_location: Optional[str] = None
    tags: Optional[List[Dict[str, str]]] = None


class CreateRunIn(BaseModel):
    experiment_id: str
    run_name: Optional[str] = None
    start_time: Optional[int] = None
    tags: Optional[List[Dict[str, str]]] = None
    user_id: Optional[str] = None


class UpdateRunIn(BaseModel):
    run_id: str
    status: Optional[str] = None
    end_time: Optional[int] = None
    run_name: Optional[str] = None


class LogMetricIn(BaseModel):
    run_id: str
    key: str = Field(min_length=1, max_length=250)
    value: float
    timestamp: Optional[int] = None
    step: int = 0


class LogParamIn(BaseModel):
    run_id: str
    key: str = Field(min_length=1, max_length=250)
    value: str = Field(max_length=6000)


class SetTagIn(BaseModel):
    run_id: str
    key: str = Field(min_length=1, max_length=250)
    value: str = Field(max_length=6000)


class Metric(BaseModel):
    key: str
    value: float
    timestamp: int
    step: int = 0


class Param(BaseModel):
    key: str
    value: str


class RunTag(BaseModel):
    key: str
    value: str


class LogBatchIn(BaseModel):
    run_id: str
    metrics: List[Metric] = []
    params: List[Param] = []
    tags: List[RunTag] = []


class SearchRunsIn(BaseModel):
    experiment_ids: Optional[List[str]] = None
    filter_string: Optional[str] = ""
    run_view_type: Optional[str] = "ACTIVE_ONLY"
    max_results: int = Field(default=200, ge=1, le=5000)
    order_by: Optional[List[str]] = None
    page_token: Optional[str] = None


class CompareRunsIn(BaseModel):
    run_ids: List[str] = Field(min_length=2, max_length=20)
    metric_keys: Optional[List[str]] = None


# ── FastAPI app ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("mlflow-service ready — tracking URI: sqlite:///%s", DB_PATH)
    yield


app = FastAPI(
    title="Trancendos MLflow Service",
    description="Self-hosted MLflow-compatible experiment tracking for Turing's Hub and Luminous",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Health ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    db = _db()
    exp_count = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    run_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    return {
        "status": "healthy",
        "service": "mlflow-service",
        "port": 8039,
        "experiments": exp_count,
        "runs": run_count,
        "db_path": str(DB_PATH),
        "artifact_root": str(ARTIFACT_ROOT),
    }


# ── Experiments ────────────────────────────────────────────────────────────────


@app.post("/api/2.0/mlflow/experiments/create")
async def create_experiment(body: CreateExperimentIn):
    db = _db()
    existing = db.execute(
        "SELECT experiment_id FROM experiments WHERE name = ?", (body.name,)
    ).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail=f"Experiment '{body.name}' already exists")

    exp_id = str(uuid.uuid4().hex[:8])
    artifact_location = body.artifact_location or str(ARTIFACT_ROOT / exp_id)
    now = _now_ms()
    tags_json = json.dumps({t["key"]: t["value"] for t in (body.tags or [])})

    db.execute(
        "INSERT INTO experiments (experiment_id, name, artifact_location, creation_time, last_update_time, tags) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (exp_id, body.name, artifact_location, now, now, tags_json),
    )
    db.commit()
    return {"experiment_id": exp_id}


@app.get("/api/2.0/mlflow/experiments/get")
async def get_experiment(experiment_id: str):
    db = _db()
    row = db.execute(
        "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment": _experiment_to_dict(row)}


@app.get("/api/2.0/mlflow/experiments/get-by-name")
async def get_experiment_by_name(experiment_name: str):
    db = _db()
    row = db.execute("SELECT * FROM experiments WHERE name = ?", (experiment_name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment": _experiment_to_dict(row)}


@app.get("/api/2.0/mlflow/experiments/list")
async def list_experiments(view_type: str = "ACTIVE_ONLY"):
    db = _db()
    rows = db.execute("SELECT * FROM experiments ORDER BY creation_time DESC").fetchall()
    experiments = [_experiment_to_dict(r) for r in rows]
    if view_type == "ACTIVE_ONLY":
        experiments = [e for e in experiments if e["lifecycle_stage"] == "active"]
    return {"experiments": experiments}


@app.get("/experiments")
async def list_experiments_shortcut():
    db = _db()
    rows = db.execute(
        "SELECT * FROM experiments WHERE lifecycle_stage = 'active' ORDER BY creation_time DESC"
    ).fetchall()
    return {"experiments": [_experiment_to_dict(r) for r in rows]}


# ── Runs ───────────────────────────────────────────────────────────────────────


@app.post("/api/2.0/mlflow/runs/create")
async def create_run(body: CreateRunIn):
    db = _db()
    exp = db.execute(
        "SELECT experiment_id, artifact_location FROM experiments WHERE experiment_id = ?",
        (body.experiment_id,),
    ).fetchone()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    run_id = uuid.uuid4().hex
    now = body.start_time or _now_ms()
    artifact_uri = str(Path(exp["artifact_location"]) / run_id)
    tags = {t["key"]: t["value"] for t in (body.tags or [])}

    db.execute(
        "INSERT INTO runs (run_id, experiment_id, run_name, status, start_time, artifact_uri, user_id, tags) "
        "VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, ?)",
        (
            run_id,
            body.experiment_id,
            body.run_name,
            now,
            artifact_uri,
            body.user_id,
            json.dumps(tags),
        ),
    )
    for key, value in tags.items():
        db.execute(
            "INSERT OR REPLACE INTO run_tags (run_id, key, value) VALUES (?, ?, ?)",
            (run_id, key, value),
        )
    db.commit()

    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return {"run": _run_to_dict(row, db)}


@app.post("/api/2.0/mlflow/runs/update")
async def update_run(body: UpdateRunIn):
    db = _db()
    run = db.execute("SELECT run_id FROM runs WHERE run_id = ?", (body.run_id,)).fetchone()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    updates: list = []
    params: list = []
    if body.status is not None:
        updates.append("status = ?")
        params.append(body.status)
    if body.end_time is not None:
        updates.append("end_time = ?")
        params.append(body.end_time)
    if body.run_name is not None:
        updates.append("run_name = ?")
        params.append(body.run_name)

    if updates:
        params.append(body.run_id)
        db.execute(f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?", params)
        db.commit()

    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (body.run_id,)).fetchone()
    return {"run_info": _run_to_dict(row, db)}


@app.post("/api/2.0/mlflow/runs/log-metric")
async def log_metric(body: LogMetricIn):
    db = _db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id = ?", (body.run_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Run not found")
    db.execute(
        "INSERT INTO run_metrics (run_id, key, value, timestamp, step) VALUES (?, ?, ?, ?, ?)",
        (body.run_id, body.key, body.value, body.timestamp or _now_ms(), body.step),
    )
    db.commit()
    return {}


@app.post("/api/2.0/mlflow/runs/log-parameter")
async def log_parameter(body: LogParamIn):
    db = _db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id = ?", (body.run_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Run not found")
    db.execute(
        "INSERT OR REPLACE INTO run_params (run_id, key, value) VALUES (?, ?, ?)",
        (body.run_id, body.key, body.value),
    )
    db.commit()
    return {}


@app.post("/api/2.0/mlflow/runs/set-tag")
async def set_tag(body: SetTagIn):
    db = _db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id = ?", (body.run_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Run not found")
    db.execute(
        "INSERT OR REPLACE INTO run_tags (run_id, key, value) VALUES (?, ?, ?)",
        (body.run_id, body.key, body.value),
    )
    db.commit()
    return {}


@app.post("/api/2.0/mlflow/runs/log-batch")
async def log_batch(body: LogBatchIn):
    db = _db()
    if not db.execute("SELECT 1 FROM runs WHERE run_id = ?", (body.run_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Run not found")
    now = _now_ms()
    for m in body.metrics:
        db.execute(
            "INSERT INTO run_metrics (run_id, key, value, timestamp, step) VALUES (?, ?, ?, ?, ?)",
            (body.run_id, m.key, m.value, m.timestamp or now, m.step),
        )
    for p in body.params:
        db.execute(
            "INSERT OR REPLACE INTO run_params (run_id, key, value) VALUES (?, ?, ?)",
            (body.run_id, p.key, p.value),
        )
    for t in body.tags:
        db.execute(
            "INSERT OR REPLACE INTO run_tags (run_id, key, value) VALUES (?, ?, ?)",
            (body.run_id, t.key, t.value),
        )
    db.commit()
    return {}


@app.get("/api/2.0/mlflow/runs/get")
async def get_run(run_id: str):
    db = _db()
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": _run_to_dict(row, db)}


@app.post("/api/2.0/mlflow/runs/search")
async def search_runs(body: SearchRunsIn):
    db = _db()
    conditions = ["r.lifecycle_stage != 'deleted'"]
    params: list = []

    if body.experiment_ids:
        placeholders = ",".join(["?"] * len(body.experiment_ids))
        conditions.append(f"r.experiment_id IN ({placeholders})")
        params.extend(body.experiment_ids)

    if body.run_view_type == "ACTIVE_ONLY":
        conditions.append("r.status != 'DELETED'")
    elif body.run_view_type == "DELETED_ONLY":
        conditions.append("r.status = 'DELETED'")

    where = " AND ".join(conditions)
    limit = int(body.max_results)
    rows = db.execute(
        f"SELECT * FROM runs r WHERE {where} ORDER BY r.start_time DESC LIMIT {limit}",
        params,
    ).fetchall()

    return {
        "runs": [_run_to_dict(r, db) for r in rows],
        "next_page_token": None,
    }


# ── Metrics ────────────────────────────────────────────────────────────────────


@app.get("/api/2.0/mlflow/metrics/get-history")
async def get_metric_history(run_id: str, metric_key: str):
    db = _db()
    rows = db.execute(
        "SELECT key, value, timestamp, step FROM run_metrics "
        "WHERE run_id = ? AND key = ? ORDER BY step ASC, id ASC",
        (run_id, metric_key),
    ).fetchall()
    return {
        "metrics": [
            {"key": r["key"], "value": r["value"], "timestamp": r["timestamp"], "step": r["step"]}
            for r in rows
        ]
    }


# ── Artifacts ─────────────────────────────────────────────────────────────────


@app.get("/api/2.0/mlflow/artifacts/list")
async def list_artifacts(run_id: str, path: str = ""):
    """List artifacts for a run.

    GET — matches the MLflow REST API spec (POST would break SDK clients).
    Path traversal is prevented by resolving the joined path and asserting it
    stays inside the run's artifact_uri root.
    """
    db = _db()
    row = db.execute("SELECT artifact_uri FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    root = Path(row["artifact_uri"]).resolve()
    subpath = path.lstrip("/") if path else ""

    try:
        validate_path(subpath or ".", root, must_exist=False, allow_create=False)
    except PathTraversalError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc

    try:
        children = list_validated_children(subpath or ".", root)
    except FileNotFoundError:
        return {"files": [], "root_uri": str(root)}

    files = []
    for entry in children:
        rel = f"{subpath}/{entry['name']}".strip("/") if subpath else entry["name"]
        files.append(
            {
                "path": rel,
                "is_dir": entry["is_dir"],
                "file_size": entry["file_size"],
            }
        )
    return {"files": files, "root_uri": str(root)}


# ── Trancendos-native endpoints ────────────────────────────────────────────────


@app.get("/runs/{run_id}/summary")
async def run_summary(run_id: str):
    """Human-readable run card with all params, latest metrics, and tags."""
    db = _db()
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _run_to_dict(row, db)

    exp_row = db.execute(
        "SELECT name FROM experiments WHERE experiment_id = ?", (row["experiment_id"],)
    ).fetchone()

    duration_s = None
    if run["start_time"] and run["end_time"]:
        duration_s = round((run["end_time"] - run["start_time"]) / 1000, 1)

    return {
        "run_id": run_id,
        "run_name": run["run_name"],
        "experiment_name": exp_row["name"] if exp_row else None,
        "status": run["status"],
        "duration_seconds": duration_s,
        "params": {p["key"]: p["value"] for p in run["params"]},
        "metrics": {m["key"]: m["value"] for m in run["metrics"]},
        "tags": {t["key"]: t["value"] for t in run["tags"]},
        "artifact_uri": run["artifact_uri"],
    }


@app.post("/runs/compare")
async def compare_runs(body: CompareRunsIn):
    """Side-by-side metric comparison across multiple runs."""
    db = _db()
    result: Dict[str, Any] = {"runs": {}, "metric_delta": {}}
    all_metric_keys: set = set()

    for run_id in body.run_ids:
        row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        run = _run_to_dict(row, db)
        # _run_to_dict returns metrics/params/tags as lists per MLflow REST spec;
        # convert to dicts for the comparison view (internal convenience format).
        metrics = {m["key"]: m["value"] for m in run["metrics"]}
        if body.metric_keys:
            metrics = {k: v for k, v in metrics.items() if k in body.metric_keys}
        result["runs"][run_id] = {
            "run_name": run["run_name"],
            "status": run["status"],
            "params": {p["key"]: p["value"] for p in run["params"]},
            "metrics": metrics,
        }
        all_metric_keys.update(metrics.keys())

    # Compute delta (max - min) for each metric across the compared runs
    for key in all_metric_keys:
        values = [
            result["runs"][rid]["metrics"][key]
            for rid in body.run_ids
            if key in result["runs"][rid]["metrics"]
        ]
        if len(values) >= 2:
            result["metric_delta"][key] = round(max(values) - min(values), 6)

    return result


@app.get("/runs/leaderboard")
async def leaderboard(
    experiment_id: str,
    metric: str,
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(20, ge=1, le=200),
):
    """Best run per experiment ranked by a single metric."""
    db = _db()
    direction = "DESC" if order == "desc" else "ASC"
    rows = db.execute(
        f"""
        SELECT r.run_id, r.run_name, r.status, r.start_time,
               m.value AS metric_value
        FROM runs r
        JOIN (
            SELECT run_id, MAX(value) AS value
            FROM run_metrics
            WHERE key = ?
            GROUP BY run_id
        ) m ON r.run_id = m.run_id
        WHERE r.experiment_id = ? AND r.lifecycle_stage = 'active'
        ORDER BY m.value {direction}
        LIMIT {int(limit)}
        """,
        (metric, experiment_id),
    ).fetchall()

    return {
        "experiment_id": experiment_id,
        "metric": metric,
        "order": order,
        "leaderboard": [
            {
                "rank": i + 1,
                "run_id": r["run_id"],
                "run_name": r["run_name"],
                "status": r["status"],
                "start_time": r["start_time"],
                "metric_value": r["metric_value"],
            }
            for i, r in enumerate(rows)
        ],
    }
