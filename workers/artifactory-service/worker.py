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
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from Dimensional.service_auth_fastapi import guard_internal_secret

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = int(os.getenv("PORT", "8047"))
WORKER_NAME = "artifactory-service"
VERSION = "1.1.0"

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


def _require_internal_auth(x_internal_secret: str = Header(default="")) -> None:
    # Delegated to Dimensional.service_auth, which this worker now reaches
    # through the `sharedcore` named build context. It compares with
    # compare_digest and refuses when the secret is unset.
    guard_internal_secret(
        x_internal_secret, INTERNAL_SECRET, mismatch_status=403, detail="Forbidden"
    )


ZOT_URL = os.getenv("ZOT_URL", "http://localhost:5000").rstrip("/")
GITEA_URL = os.getenv("GITEA_URL", "http://localhost:3000").rstrip("/")
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
LOCAL_ARTIFACT_PATH = Path(os.getenv("LOCAL_ARTIFACT_PATH", "/tmp/artifacts"))
ARTIFACT_CUSTODY_DB = Path(os.getenv("ARTIFACT_CUSTODY_DB", "/app/data/custody.db"))

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


class CustodyBase(str, Enum):
    INTERNAL_USER = "internal-user"
    INTERNAL_ADMIN = "internal-admin"
    EXTERNAL = "external"


class ExternalHold(str, Enum):
    INCOMER = "incomer"
    ICE_BOX = "ice-box"
    STORE = "store"


class CustodyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExternalArtifactIntake(CustodyRequest):
    name: str = Field(..., min_length=1, max_length=200)
    sha256: str = Field(..., pattern=r"^[a-fA-F0-9]{64}$")
    artifact_type: str = Field("generic", min_length=1, max_length=80)
    submitted_by: str = Field(..., min_length=1, max_length=120)
    source_reference: str = Field(..., min_length=1, max_length=500)


class InternalUserArtifact(CustodyRequest):
    name: str = Field(..., min_length=1, max_length=200)
    sha256: str = Field(..., pattern=r"^[a-fA-F0-9]{64}$")
    artifact_type: str = Field("generic", min_length=1, max_length=80)
    owner_id: str = Field(..., min_length=1, max_length=120)


class ScanEvidence(CustodyRequest):
    scanner: str = Field(..., min_length=1, max_length=120)
    scan_reference: str = Field(..., min_length=1, max_length=200)
    disposition: Literal["clean", "suspicious", "malicious"]


class InternalPromotionEvidence(CustodyRequest):
    assessor: str = Field(..., min_length=1, max_length=120)
    assessment_reference: str = Field(..., min_length=1, max_length=200)
    rationale: str = Field(..., min_length=16, max_length=2000)


class ThinkTankReview(CustodyRequest):
    reviewer: str = Field(..., min_length=1, max_length=120)
    decision: Literal["approved", "rejected"]
    notes: str = Field(..., min_length=1, max_length=2000)


class ArtifactCustodyLedger:
    """Durable, metadata-only custody records for the Artifactory bases.

    The ledger never accepts, fetches, or executes artifact bytes. A custody
    transition records what a separate storage or sandbox integration must
    prove; it does not falsely represent that integration as complete.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifact_custody (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    base TEXT NOT NULL,
                    hold TEXT,
                    status TEXT NOT NULL,
                    owner_or_submitter TEXT NOT NULL,
                    source_reference TEXT,
                    assessment_reference TEXT,
                    assessment_rationale TEXT,
                    scan_reference TEXT,
                    scanner TEXT,
                    scan_disposition TEXT,
                    think_tank_reviewer TEXT,
                    think_tank_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def _get_row(self, custody_id: str) -> Optional[sqlite3.Row]:
        with self._connection() as connection:
            return connection.execute(
                "SELECT * FROM artifact_custody WHERE id = ?", (custody_id,)
            ).fetchone()

    def get(self, custody_id: str) -> Optional[dict[str, Any]]:
        row = self._get_row(custody_id)
        return self._record(row) if row else None

    def list(self, base: Optional[CustodyBase] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM artifact_custody"
        parameters: tuple[str, ...] = ()
        if base:
            query += " WHERE base = ?"
            parameters = (base.value,)
        query += " ORDER BY updated_at DESC"
        with self._connection() as connection:
            return [self._record(row) for row in connection.execute(query, parameters).fetchall()]

    def counts(self) -> dict[str, int]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT base || COALESCE(':' || hold, '') AS location, COUNT(*) AS count "
                "FROM artifact_custody GROUP BY base, hold"
            ).fetchall()
        return {row["location"]: row["count"] for row in rows}

    def register_external(self, request: ExternalArtifactIntake) -> dict[str, Any]:
        custody_id = str(uuid.uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO artifact_custody (
                    id, name, sha256, artifact_type, base, hold, status,
                    owner_or_submitter, source_reference, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    custody_id,
                    request.name,
                    request.sha256.lower(),
                    request.artifact_type,
                    CustodyBase.EXTERNAL.value,
                    ExternalHold.INCOMER.value,
                    "received",
                    request.submitted_by,
                    request.source_reference,
                    now,
                    now,
                ),
            )
        return self.get(custody_id)  # type: ignore[return-value]

    def register_internal_user(self, request: InternalUserArtifact) -> dict[str, Any]:
        custody_id = str(uuid.uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO artifact_custody (
                    id, name, sha256, artifact_type, base, status,
                    owner_or_submitter, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    custody_id,
                    request.name,
                    request.sha256.lower(),
                    request.artifact_type,
                    CustodyBase.INTERNAL_USER.value,
                    "available",
                    request.owner_id,
                    now,
                    now,
                ),
            )
        return self.get(custody_id)  # type: ignore[return-value]

    def move_to_ice_box(self, custody_id: str) -> dict[str, Any]:
        self._transition(
            custody_id,
            expected=(CustodyBase.EXTERNAL.value, ExternalHold.INCOMER.value, "received"),
            updates={"hold": ExternalHold.ICE_BOX.value, "status": "awaiting_scan"},
        )
        return self.get(custody_id)  # type: ignore[return-value]

    def record_scan(self, custody_id: str, evidence: ScanEvidence) -> dict[str, Any]:
        status = "cleared" if evidence.disposition == "clean" else "quarantined"
        self._transition(
            custody_id,
            expected=(CustodyBase.EXTERNAL.value, ExternalHold.ICE_BOX.value, "awaiting_scan"),
            updates={
                "status": status,
                "scanner": evidence.scanner,
                "scan_reference": evidence.scan_reference,
                "scan_disposition": evidence.disposition,
            },
        )
        return self.get(custody_id)  # type: ignore[return-value]

    def store_external(self, custody_id: str) -> dict[str, Any]:
        self._transition(
            custody_id,
            expected=(CustodyBase.EXTERNAL.value, ExternalHold.ICE_BOX.value, "cleared"),
            updates={"hold": ExternalHold.STORE.value, "status": "admitted"},
        )
        return self.get(custody_id)  # type: ignore[return-value]

    def promote_to_internal_admin(
        self, custody_id: str, evidence: InternalPromotionEvidence
    ) -> dict[str, Any]:
        self._transition(
            custody_id,
            expected=(CustodyBase.INTERNAL_USER.value, None, "available"),
            updates={
                "base": CustodyBase.INTERNAL_ADMIN.value,
                "status": "think-tank-review",
                "assessment_reference": evidence.assessment_reference,
                "assessment_rationale": evidence.rationale,
                "scanner": evidence.assessor,
            },
        )
        return self.get(custody_id)  # type: ignore[return-value]

    def record_think_tank_review(self, custody_id: str, review: ThinkTankReview) -> dict[str, Any]:
        status = "available" if review.decision == "approved" else "rejected"
        self._transition(
            custody_id,
            expected=(CustodyBase.INTERNAL_ADMIN.value, None, "think-tank-review"),
            updates={
                "status": status,
                "think_tank_reviewer": review.reviewer,
                "think_tank_notes": review.notes,
            },
        )
        return self.get(custody_id)  # type: ignore[return-value]

    def _transition(
        self,
        custody_id: str,
        expected: tuple[str, Optional[str], str],
        updates: dict[str, str],
    ) -> None:
        current = self._get_row(custody_id)
        if current is None:
            raise LookupError("custody record not found")
        expected_base, expected_hold, expected_status = expected
        if (
            current["base"] != expected_base
            or current["hold"] != expected_hold
            or current["status"] != expected_status
        ):
            raise ValueError("custody transition is not permitted from the current state")
        assignments = list(updates)
        values = [updates[column] for column in assignments]
        assignments.append("updated_at")
        values.append(self._now())
        values.append(custody_id)
        with self._connection() as connection:
            connection.execute(
                f"UPDATE artifact_custody SET {', '.join(f'{column} = ?' for column in assignments)} "
                "WHERE id = ?",
                values,
            )


custody_ledger = ArtifactCustodyLedger(ARTIFACT_CUSTODY_DB)


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
        "custody_counts": custody_ledger.counts(),
        "custody_mode": "metadata-only",
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# ---------------------------------------------------------------------------
# /artifactory/custody -- three-base artifact custody ledger
# ---------------------------------------------------------------------------


def _transition_response(operation):
    try:
        return operation()
    except LookupError:
        return JSONResponse({"error": "Custody record not found"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)


@app.get("/artifactory/custody", dependencies=[Depends(_require_internal_auth)])
async def list_custody(base: Optional[CustodyBase] = None) -> dict[str, Any]:
    records = custody_ledger.list(base)
    return {"records": records, "total": len(records), "mode": "metadata-only"}


@app.get("/artifactory/custody/{custody_id}", dependencies=[Depends(_require_internal_auth)])
async def get_custody(custody_id: str) -> dict[str, Any]:
    record = custody_ledger.get(custody_id)
    if record is None:
        return JSONResponse({"error": "Custody record not found"}, status_code=404)
    return record


@app.post("/artifactory/custody/external", dependencies=[Depends(_require_internal_auth)])
async def receive_external_artifact(request: ExternalArtifactIntake) -> dict[str, Any]:
    """Record external intake in Hold 1; artifact bytes are never accepted here."""
    return custody_ledger.register_external(request)


@app.post("/artifactory/custody/internal-user", dependencies=[Depends(_require_internal_auth)])
async def register_internal_user_artifact(request: InternalUserArtifact) -> dict[str, Any]:
    """Record a Base 1 user artifact without moving or reading its bytes."""
    return custody_ledger.register_internal_user(request)


@app.post(
    "/artifactory/custody/{custody_id}/ice-box",
    dependencies=[Depends(_require_internal_auth)],
)
async def queue_for_ice_box(custody_id: str) -> dict[str, Any]:
    """Move Hold 1 intake to Hold 2 awaiting independently verifiable scan evidence."""
    return _transition_response(lambda: custody_ledger.move_to_ice_box(custody_id))


@app.post(
    "/artifactory/custody/{custody_id}/scan",
    dependencies=[Depends(_require_internal_auth)],
)
async def record_ice_box_scan(custody_id: str, evidence: ScanEvidence) -> dict[str, Any]:
    """Record a scan result; only clean evidence can later enter Hold 3."""
    return _transition_response(lambda: custody_ledger.record_scan(custody_id, evidence))


@app.post(
    "/artifactory/custody/{custody_id}/store",
    dependencies=[Depends(_require_internal_auth)],
)
async def admit_to_external_store(custody_id: str) -> dict[str, Any]:
    """Move a clean Hold 2 record to Hold 3. Quarantined records cannot advance."""
    return _transition_response(lambda: custody_ledger.store_external(custody_id))


@app.post(
    "/artifactory/custody/{custody_id}/promote-to-admin",
    dependencies=[Depends(_require_internal_auth)],
)
async def promote_to_internal_admin(
    custody_id: str, evidence: InternalPromotionEvidence
) -> dict[str, Any]:
    """Create a Base 2 Think Tank review candidate from assessed Base 1 value."""
    return _transition_response(
        lambda: custody_ledger.promote_to_internal_admin(custody_id, evidence)
    )


@app.post(
    "/artifactory/custody/{custody_id}/think-tank-review",
    dependencies=[Depends(_require_internal_auth)],
)
async def record_internal_admin_review(custody_id: str, review: ThinkTankReview) -> dict[str, Any]:
    """Record the accountable Think Tank decision; no AI self-approves promotion."""
    return _transition_response(lambda: custody_ledger.record_think_tank_review(custody_id, review))


# ---------------------------------------------------------------------------
# /artifactory/repositories
# ---------------------------------------------------------------------------


@app.get("/artifactory/repositories", dependencies=[Depends(_require_internal_auth)])
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


@app.get(
    "/artifactory/repositories/{repo:path}/tags", dependencies=[Depends(_require_internal_auth)]
)
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


@app.post("/artifactory/repositories", dependencies=[Depends(_require_internal_auth)])
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


@app.get("/artifactory/search", dependencies=[Depends(_require_internal_auth)])
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


@app.post("/artifactory/pull", dependencies=[Depends(_require_internal_auth)])
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
