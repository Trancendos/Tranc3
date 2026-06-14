"""
Swarm Coordinator — continuous manifest runner (The Citadel)
=============================================================
Reads YAML manifests from config/swarm/manifests/ on an interval and
executes proactive tasks (health probes, registry audits, N-1 checks).

Port: 8053
Zero-cost: subprocess + local scripts only (no paid APIs).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.entities.health_metadata import health_entity_block
from src.errors.error_catalog import ErrorCode

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

WORKER_PORT = int(os.environ.get("SWARM_COORDINATOR_PORT", "8053"))
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
WORKER_NAME = "swarm-coordinator"
ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = Path(os.environ.get("SWARM_MANIFEST_DIR", ROOT / "config/swarm/manifests"))
POLL_SECONDS = float(os.environ.get("SWARM_POLL_INTERVAL_SECONDS", "300"))
LOG_PATH = ROOT / "logs" / "swarm-coordinator.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

app = FastAPI(title="Swarm Coordinator", version="1.0.0")

# OpenTelemetry instrumentation
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    from src.observability.otel import init_otel

    init_otel(service_name="tranc3.swarm-coordinator-service")
    FastAPIInstrumentor.instrument_app(app)
except Exception:
    pass  # OTel is optional — never block startup
STARTED_AT = datetime.now(timezone.utc)

_run_lock = asyncio.Lock()
_last_run: dict[str, Any] | None = None
_running = False


def _load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if yaml is None:
        raise RuntimeError("PyYAML required for swarm manifests")
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def _run_task(task: dict[str, Any]) -> dict[str, Any]:
    script = task.get("script")
    if not script:
        return {"id": task.get("id"), "status": "skipped", "reason": "no script"}
    script_path = ROOT / script
    if not script_path.is_file():
        return {"id": task.get("id"), "status": "failed", "reason": f"missing {script}"}
    args = [sys.executable, str(script_path)] + list(task.get("args") or [])
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    return {
        "id": task.get("id"),
        "bot": task.get("bot"),
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def _run_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_manifest(path)
    results = [_run_task(t) for t in manifest.get("tasks") or []]
    report = {
        "run_id": str(uuid.uuid4()),
        "manifest": str(path.relative_to(ROOT))
        if path.is_absolute() and str(path).startswith(str(ROOT))
        else str(path),
        "orchestrator": manifest.get("orchestrator"),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(report) + "\n")
    failed = sum(1 for r in results if r.get("status") == "failed")
    report["failed_count"] = failed
    report["status"] = "ok" if failed == 0 else "degraded"
    return report


async def _poll_loop() -> None:
    global _last_run, _running
    while True:
        await asyncio.sleep(POLL_SECONDS)
        async with _run_lock:
            if _running:
                continue
            _running = True
            try:
                manifests = sorted(MANIFEST_DIR.glob("*.yaml"))
                if not manifests:
                    logger.warning("No manifests in %s", MANIFEST_DIR)
                    continue
                combined: list[dict[str, Any]] = []
                for mf in manifests:
                    try:
                        combined.append(_run_manifest(mf))
                    except Exception as exc:
                        logger.exception("Manifest %s failed: %s", mf, exc)
                        combined.append(
                            {
                                "manifest": str(mf),
                                "status": "failed",
                                "error": str(exc),
                            },
                        )
                _last_run = {
                    "run_at": datetime.now(timezone.utc).isoformat(),
                    "manifests": combined,
                }
            finally:
                _running = False


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_poll_loop())
    logger.info(
        "Swarm coordinator started port=%s poll=%ss dir=%s",
        WORKER_PORT,
        POLL_SECONDS,
        MANIFEST_DIR,
    )


async def _require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if not hmac.compare_digest(x_internal_secret, _INTERNAL_SECRET):
        raise HTTPException(status_code=401, detail=ErrorCode.AUTH_TOKEN_INVALID.value)


class RunRequest(BaseModel):
    manifest: str | None = Field(
        default=None,
        description="Relative path under config/swarm/manifests/",
    )


@app.get("/health")
async def health():
    return {
        "entity": health_entity_block(8053, "swarm-coordinator"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "manifest_dir": str(MANIFEST_DIR),
        "poll_interval_seconds": POLL_SECONDS,
        "last_run": _last_run,
    }


@app.get("/status")
async def status():
    return {
        "service": WORKER_NAME,
        "running": _running,
        "last_run": _last_run,
        "manifests": [p.name for p in sorted(MANIFEST_DIR.glob("*.yaml"))],
    }


@app.post("/run", dependencies=[Depends(_require_internal_auth)])
async def run_now(body: RunRequest | None = None):
    """Trigger an immediate manifest run (all or one file)."""
    async with _run_lock:
        global _last_run, _running
        if _running:
            return {"status": "busy"}
        _running = True
        try:
            if body and body.manifest:
                path = MANIFEST_DIR / body.manifest
                if not path.is_file():
                    path = ROOT / body.manifest
                reports = [_run_manifest(path)]
            else:
                reports = [_run_manifest(p) for p in sorted(MANIFEST_DIR.glob("*.yaml"))]
            _last_run = {
                "run_at": datetime.now(timezone.utc).isoformat(),
                "manifests": reports,
            }
            return _last_run
        finally:
            _running = False


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
