"""
Trancendos Fabulousa Service — Port 8048
=========================================
Styling, UX, UI & design centre. Bridges the Penpot self-hosted design platform
to the Trancendos ecosystem.

Adaptive fallback chain: Penpot → Figma API (free) → offline stub
Zero-cost mandate: all providers are free/self-hosted.

Port: 8048
Entity: Fabulousa
Lead AI: Baron Von Hilton
Foundation: Penpot (self-hosted)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = int(os.getenv("PORT", "8048"))
WORKER_NAME = "fabulousa-service"
VERSION = "1.0.0"

PENPOT_URL = os.getenv("PENPOT_URL", "http://localhost:9001").rstrip("/")
PENPOT_TOKEN = os.getenv("PENPOT_TOKEN", "")
FIGMA_TOKEN = os.getenv("FIGMA_TOKEN", "")

STARTED_AT = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# In-memory cache for degraded mode
# ---------------------------------------------------------------------------
_cache: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""


class ExportRequest(BaseModel):
    project_id: str
    file_id: Optional[str] = None
    format: str = "png"  # png, svg, pdf


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_http_timeout = httpx.Timeout(10.0, connect=5.0)


async def _penpot_get(path: str) -> Any:
    """Async GET against the Penpot API. Raises httpx.HTTPError on failure."""
    headers = {}
    if PENPOT_TOKEN:
        headers["Authorization"] = f"Token {PENPOT_TOKEN}"
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{PENPOT_URL}{path}", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _penpot_post(path: str, payload: dict[str, Any]) -> Any:
    headers = {"Content-Type": "application/json"}
    if PENPOT_TOKEN:
        headers["Authorization"] = f"Token {PENPOT_TOKEN}"
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.post(f"{PENPOT_URL}{path}", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _figma_get(path: str) -> Any:
    """Fallback: call Figma REST API (read-only free tier)."""
    if not FIGMA_TOKEN:
        raise RuntimeError("FIGMA_TOKEN not set")
    headers = {"X-Figma-Token": FIGMA_TOKEN}
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"https://api.figma.com/v1{path}", headers=headers)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Fabulousa Service",
    description="Styling, UX, UI & design centre — Penpot bridge",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {"status": "ok", "service": WORKER_NAME, "version": VERSION, "uptime_seconds": uptime}


# ---------------------------------------------------------------------------
# /fabulousa/status — service + Penpot reachability
# ---------------------------------------------------------------------------


@app.get("/fabulousa/status")
async def fabulousa_status() -> dict[str, Any]:
    penpot_ok = False
    penpot_error = None
    try:
        await _penpot_get("/api/rpc/command/get-profile")
        penpot_ok = True
    except Exception as exc:
        logger.warning("Penpot status check failed: %s", exc)
        penpot_error = "Penpot unreachable"

    figma_ok = bool(FIGMA_TOKEN)

    return {
        "service": WORKER_NAME,
        "entity": "Fabulousa",
        "lead_ai": "Baron Von Hilton",
        "version": VERSION,
        "penpot_reachable": penpot_ok,
        "penpot_url": PENPOT_URL,
        "penpot_error": penpot_error,
        "figma_fallback_configured": figma_ok,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# ---------------------------------------------------------------------------
# /fabulousa/projects — list + create
# ---------------------------------------------------------------------------


@app.get("/fabulousa/projects")
async def list_projects() -> dict[str, Any]:
    """List Penpot projects. Degrades gracefully when Penpot is unavailable."""
    degraded = False

    # Primary: Penpot
    try:
        data = await _penpot_get("/api/rpc/command/get-teams")
        projects: list[dict[str, Any]] = []
        if isinstance(data, list):
            for team in data:
                try:
                    team_files = await _penpot_get(
                        f"/api/rpc/command/get-files?team-id={team.get('id', '')}"
                    )
                    if isinstance(team_files, list):
                        for f in team_files:
                            projects.append(
                                {
                                    "id": f.get("id"),
                                    "name": f.get("name"),
                                    "team_id": team.get("id"),
                                    "team_name": team.get("name"),
                                    "modified_at": f.get("modifiedAt"),
                                    "source": "penpot",
                                }
                            )
                except Exception as exc:
                    logger.debug("Failed to get files for team %s: %s", team.get("id"), exc)
        _cache["projects"] = projects
        return {"projects": projects, "total": len(projects), "degraded": False}
    except Exception as exc:
        logger.warning("Penpot unavailable: %s — trying Figma fallback", exc)

    # Fallback: Figma
    if FIGMA_TOKEN:
        try:
            data = await _figma_get("/me")
            projects_figma: list[dict[str, Any]] = []
            # Figma /me doesn't list files; return profile stub
            projects_figma.append(
                {
                    "id": data.get("id"),
                    "name": f"Figma user: {data.get('handle')}",
                    "source": "figma",
                }
            )
            _cache["projects"] = projects_figma
            return {"projects": projects_figma, "total": len(projects_figma), "degraded": False}
        except Exception as exc2:
            logger.warning("Figma fallback failed: %s", exc2)

    # Offline stub — return cached data with degraded flag
    cached = _cache.get("projects", [])
    degraded = True
    return {"projects": cached, "total": len(cached), "degraded": degraded}


@app.post("/fabulousa/projects")
async def create_project(body: ProjectCreate) -> dict[str, Any]:
    """Create a new Penpot project/file."""
    try:
        result = await _penpot_post(
            "/api/rpc/command/create-file",
            {"name": body.name},
        )
        return {"created": True, "project": result, "source": "penpot"}
    except Exception as exc:
        logger.error("Failed to create Penpot project: %s", exc)
        raise HTTPException(status_code=503, detail=f"Penpot unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# /fabulousa/assets
# ---------------------------------------------------------------------------


@app.get("/fabulousa/assets")
async def list_assets() -> dict[str, Any]:
    """List design assets from Penpot."""
    try:
        data = await _penpot_get("/api/rpc/command/get-libraries")
        assets = data if isinstance(data, list) else []
        _cache["assets"] = assets
        return {"assets": assets, "total": len(assets), "degraded": False}
    except Exception as exc:
        logger.warning("Assets unavailable (Penpot): %s", exc)
        cached = _cache.get("assets", [])
        return {"assets": cached, "total": len(cached), "degraded": True}


# ---------------------------------------------------------------------------
# /fabulousa/export
# ---------------------------------------------------------------------------


@app.post("/fabulousa/export")
async def trigger_export(body: ExportRequest) -> dict[str, Any]:
    """Trigger a Penpot export job."""
    try:
        payload: dict[str, Any] = {
            "file-id": body.file_id or body.project_id,
            "format": body.format,
        }
        result = await _penpot_post("/api/rpc/command/export-binfile", payload)
        return {"job_id": result.get("id"), "status": "queued", "format": body.format}
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"Export unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
