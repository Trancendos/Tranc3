"""
Trancendos Artifactory Service — Port 8047
==========================================
Central artifact repository library. Bridges the Zot OCI registry to the
Trancendos ecosystem.

Adaptive fallback chain: Zot → Gitea packages API → local filesystem scan
Zero-cost mandate: all backends are free/self-hosted.

Port: 8047
Entity: The Artifactory
Lead AI: Lunascene
Foundation: Zot (OCI registry)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = int(os.getenv("PORT", "8047"))
WORKER_NAME = "artifactory-service"
VERSION = "1.0.0"

ZOT_URL = os.getenv("ZOT_URL", "http://localhost:5000").rstrip("/")
GITEA_URL = os.getenv("GITEA_URL", "http://localhost:3000").rstrip("/")
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
LOCAL_ARTIFACT_PATH = Path(os.getenv("LOCAL_ARTIFACT_PATH", "/tmp/artifacts"))

STARTED_AT = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_http_timeout = httpx.Timeout(10.0, connect=5.0)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    public: bool = True


class PullRequest(BaseModel):
    image: str = Field(..., description="image:tag or digest")
    repo: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ZOT_ALLOWED_PATHS: frozenset[str] = frozenset(
    [
        "/v2/",
        "/v2/_catalog",
    ]
)

_GITEA_ALLOWED_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/repos/search",
    "/api/v1/user/repos",
    "/api/v1/packages",
)


def _validate_zot_path(path: str) -> None:
    """Restrict Zot API calls to known safe path prefixes (prevent SSRF)."""
    if ".." in path:
        raise ValueError(f"Zot path not permitted: {path}")
    if path in _ZOT_ALLOWED_PATHS:
        return
    if path.startswith("/v2/") and path.endswith("/tags/list"):
        return
    raise ValueError(f"Zot path not permitted: {path}")


def _validate_gitea_path(path: str) -> None:
    """Restrict Gitea API calls to known safe path prefixes (prevent SSRF)."""
    for prefix in _GITEA_ALLOWED_PATH_PREFIXES:
        if path.startswith(prefix):
            return
    raise ValueError(f"Gitea path not permitted: {path}")


async def _zot_get(path: str) -> Any:
    _validate_zot_path(path)
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{ZOT_URL}{path}")
        resp.raise_for_status()
        return resp.json()


# Strict allowlist for repo name characters — CodeQL recognises re.fullmatch as SSRF sanitizer.
_ZOT_REPO_RE = re.compile(r"[a-zA-Z0-9._/-]{1,200}")


async def _zot_list_tags(repo: str) -> Any:
    """Fetch tags for a Zot repository. repo is validated via regex before URL construction."""
    if not _ZOT_REPO_RE.fullmatch(repo):
        raise ValueError(f"Repo name not permitted: {repo}")
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{ZOT_URL}/v2/{repo}/tags/list")
        resp.raise_for_status()
        return resp.json()


async def _gitea_get(path: str) -> Any:
    _validate_gitea_path(path)
    headers = {}
    if GITEA_TOKEN:
        headers["Authorization"] = f"token {GITEA_TOKEN}"
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{GITEA_URL}{path}", headers=headers)
        resp.raise_for_status()
        return resp.json()


def _local_scan() -> list[dict[str, Any]]:
    """Scan local artifact path for files as last-resort fallback."""
    artifacts: list[dict[str, Any]] = []
    try:
        LOCAL_ARTIFACT_PATH.mkdir(parents=True, exist_ok=True)
        for p in LOCAL_ARTIFACT_PATH.rglob("*"):
            if p.is_file():
                artifacts.append(
                    {
                        "name": p.name,
                        "path": str(p.relative_to(LOCAL_ARTIFACT_PATH)),
                        "size": p.stat().st_size,
                        "source": "local",
                    }
                )
    except Exception as exc:
        logger.warning("Local scan failed: %s", exc)
    return artifacts


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Artifactory Service",
    description="Central artifact repository — Zot OCI registry bridge",
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
# /artifactory/status
# ---------------------------------------------------------------------------


@app.get("/artifactory/status")
async def artifactory_status() -> dict[str, Any]:
    zot_ok = False
    zot_error = None
    try:
        await _zot_get("/v2/")
        zot_ok = True
    except Exception as exc:
        logger.warning("Zot status check failed: %s", exc)
        zot_error = "Zot registry unreachable"

    return {
        "service": WORKER_NAME,
        "entity": "The Artifactory",
        "lead_ai": "Lunascene",
        "version": VERSION,
        "zot_reachable": zot_ok,
        "zot_url": ZOT_URL,
        "zot_error": zot_error,
        "gitea_url": GITEA_URL,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# ---------------------------------------------------------------------------
# /artifactory/repositories
# ---------------------------------------------------------------------------


@app.get("/artifactory/repositories")
async def list_repositories() -> dict[str, Any]:
    """List repositories: Zot → Gitea → local filesystem."""
    # Primary: Zot v2 catalog
    try:
        data = await _zot_get("/v2/_catalog")
        repos = [{"name": r, "source": "zot"} for r in data.get("repositories", [])]
        return {"repositories": repos, "total": len(repos), "source": "zot"}
    except Exception as exc:
        logger.warning("Zot unavailable: %s — trying Gitea", exc)

    # Fallback: Gitea packages
    if GITEA_URL and GITEA_URL != "http://localhost:3000":
        try:
            data = await _gitea_get("/api/v1/repos/search?limit=50&type=fork")
            repos = [
                {"name": r.get("name"), "full_name": r.get("full_name"), "source": "gitea"}
                for r in (data.get("data") or [])
            ]
            return {"repositories": repos, "total": len(repos), "source": "gitea"}
        except Exception as exc2:
            logger.warning("Gitea fallback failed: %s", exc2)

    # Last resort: local filesystem
    artifacts = _local_scan()
    dirs: set[str] = {Path(a["path"]).parts[0] for a in artifacts if "/" in a["path"]}
    repos = [{"name": d, "source": "local"} for d in sorted(dirs)]
    return {"repositories": repos, "total": len(repos), "source": "local"}


@app.get("/artifactory/repositories/{repo:path}/tags")
async def list_tags(repo: str) -> dict[str, Any]:
    """List tags for a repository in Zot."""
    safe_repo = repo.replace("\n", "").replace("\r", "")[:100]
    try:
        data = await _zot_list_tags(safe_repo)
        tags = data.get("tags") or []
        return {"repo": repo, "tags": tags, "total": len(tags)}
    except Exception as exc:
        logger.warning("Zot tags unavailable for %s: %s", safe_repo, exc)
        return {"repo": repo, "tags": [], "total": 0, "error": "Tags unavailable"}


@app.post("/artifactory/repositories")
async def create_repository(body: RepoCreate) -> dict[str, Any]:
    """Create a repository (Zot config API or Gitea)."""
    # Zot doesn't have a create-repo endpoint; repos are auto-created on push.
    # Fallback: create via Gitea if available.
    if GITEA_TOKEN:
        try:
            headers = {
                "Authorization": f"token {GITEA_TOKEN}",
                "Content-Type": "application/json",
            }
            payload = {
                "name": body.name,
                "description": body.description,
                "private": not body.public,
            }
            async with httpx.AsyncClient(timeout=_http_timeout) as client:
                resp = await client.post(
                    f"{GITEA_URL}/api/v1/user/repos", json=payload, headers=headers
                )
                resp.raise_for_status()
                return {"created": True, "repo": resp.json(), "source": "gitea"}
        except Exception as exc:
            logger.error("Gitea create repo failed: %s", exc)

    # Zot repos are auto-created on first image push — not created yet
    return {
        "created": False,
        "pending_push": True,
        "repo": {"name": body.name, "description": body.description},
        "source": "zot",
        "note": "Zot repos are created automatically on first image push.",
    }


# ---------------------------------------------------------------------------
# /artifactory/search
# ---------------------------------------------------------------------------


@app.get("/artifactory/search")
async def search_artifacts(q: str = "") -> dict[str, Any]:
    """Search artifacts across all available backends."""
    results: list[dict[str, Any]] = []

    try:
        data = await _zot_get("/v2/_catalog")
        for repo in data.get("repositories", []):
            if not q or q.lower() in repo.lower():
                results.append({"name": repo, "source": "zot"})
    except Exception as exc:
        logger.debug("Zot catalog search failed: %s", exc)

    if not results:
        local = _local_scan()
        results = [a for a in local if not q or q.lower() in a["name"].lower()]

    return {"query": q, "results": results, "total": len(results)}


# ---------------------------------------------------------------------------
# /artifactory/pull
# ---------------------------------------------------------------------------


def _sanitize_log(value: str) -> str:
    """Strip newlines and control chars to prevent log injection."""
    return value.replace("\r", "").replace("\n", "").replace("\t", " ")[:200]


@app.post("/artifactory/pull")
async def log_pull(body: PullRequest) -> dict[str, Any]:
    """Log an image pull request (audit trail). Does not execute docker pull."""
    safe_image = _sanitize_log(body.image)
    safe_repo = _sanitize_log(body.repo or "")
    logger.info("Artifact pull requested: image=%s repo=%s", safe_image, safe_repo)
    return {
        "logged": True,
        "image": body.image,
        "repo": body.repo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Pull logged. Execute 'docker pull' on host to fetch the image.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
