# src/artifactory/registry.py
# The Artifactory — Artefact repository for Trancendos.
#
# The Artifactory provides OCI-compatible artefact storage:
#   - Docker/OCI image registry (foundation: Zot self-hosted)
#   - Package registry (Python wheels, npm, generic files)
#   - Model artefacts (Tranc3Engine weights, ONNX exports)
#   - Build artefacts from The Workshop (Forgejo CI)
#   - Semantic versioning and tag management
#   - Retention policies (TTL-based cleanup)
#
# This scaffold tracks artefact metadata. Actual binary storage
# delegates to Zot OCI registry or local filesystem.

from __future__ import annotations

import logging

from shared_core.sanitize import sanitize_for_log

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ArtifactType(str, Enum):
    DOCKER      = "docker"       # OCI/Docker image
    PYTHON      = "python"       # Python wheel / sdist
    NPM         = "npm"          # Node.js package
    MODEL       = "model"        # ML model weights / ONNX
    GENERIC     = "generic"      # Raw file
    CLOUDFLARE  = "cloudflare"   # CF Worker bundle


class ArtifactStatus(str, Enum):
    AVAILABLE = "available"
    UPLOADING = "uploading"
    DELETED   = "deleted"
    EXPIRED   = "expired"


@dataclass
class ArtifactVersion:
    version: str
    digest: str = ""          # SHA-256 or OCI digest
    size_bytes: int = 0
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "tags": self.tags,
        }


@dataclass
class Artifact:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    namespace: str = "trancendos"
    artifact_type: ArtifactType = ArtifactType.GENERIC
    status: ArtifactStatus = ArtifactStatus.AVAILABLE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    versions: List[ArtifactVersion] = field(default_factory=list)
    description: str = ""
    ttl_days: Optional[int] = None   # None = retain forever

    def latest_version(self) -> Optional[ArtifactVersion]:
        if not self.versions:
            return None
        return sorted(self.versions, key=lambda v: v.created_at, reverse=True)[0]

    def to_dict(self) -> Dict[str, Any]:
        latest = self.latest_version()
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "type": self.artifact_type.value,
            "status": self.status.value,
            "description": self.description,
            "version_count": len(self.versions),
            "latest_version": latest.version if latest else None,
            "latest_digest": latest.digest if latest else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl_days": self.ttl_days,
        }


class TheArtifactory:
    """
    The Artifactory — OCI artefact repository.

    Production storage delegates to Zot self-hosted OCI registry.
    This layer manages metadata, versioning, and retention policy.
    """

    def __init__(self):
        self._artifacts: Dict[str, Artifact] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = [
            ("tranc3-backend", ArtifactType.DOCKER, "tranc3-backend FastAPI Docker image"),
            ("tranc3-bots", ArtifactType.DOCKER, "tranc3-bots 12-bot service Docker image"),
            ("tranc3-engine", ArtifactType.MODEL, "Tranc3Engine transformer weights (ONNX + PyTorch)"),
            ("tranc3-ai-worker", ArtifactType.CLOUDFLARE, "tranc3-ai CF Worker bundle"),
            ("infinity-void-worker", ArtifactType.CLOUDFLARE, "infinity-void CF Worker bundle"),
            ("trancendos-api-gateway", ArtifactType.CLOUDFLARE, "API Gateway CF Worker bundle"),
        ]
        for name, atype, desc in defaults:
            art = Artifact(name=name, artifact_type=atype, description=desc)
            self._artifacts[art.id] = art

    def create_artifact(
        self,
        name: str,
        artifact_type: ArtifactType,
        namespace: str = "trancendos",
        description: str = "",
        ttl_days: Optional[int] = None,
    ) -> Artifact:
        artifact = Artifact(
            name=name,
            namespace=namespace,
            artifact_type=artifact_type,
            description=description,
            ttl_days=ttl_days,
        )
        self._artifacts[artifact.id] = artifact
        self._emit("artifactory.artifact.created", {"artifact_id": artifact.id, "name": name})
        return artifact

    def push_version(
        self,
        artifact_id: str,
        version: str,
        digest: str = "",
        size_bytes: int = 0,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ArtifactVersion]:
        artifact = self._artifacts.get(artifact_id)
        if not artifact or artifact.status == ArtifactStatus.DELETED:
            return None
        ver = ArtifactVersion(
            version=version,
            digest=digest,
            size_bytes=size_bytes,
            tags=tags or [],
            metadata=metadata or {},
        )
        artifact.versions.append(ver)
        artifact.updated_at = time.time()
        self._emit("artifactory.version.pushed", {
            "artifact_id": artifact_id, "version": version, "digest": digest
        })
        logger.info("artifactory: pushed %s v%s digest=%s", sanitize_for_log(artifact.name), sanitize_for_log(version), sanitize_for_log(digest[:12]) if digest else "")
        return ver

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def find_by_name(self, name: str, namespace: str = "trancendos") -> Optional[Artifact]:
        for a in self._artifacts.values():
            if a.name == name and a.namespace == namespace:
                return a
        return None

    def list_artifacts(
        self,
        artifact_type: Optional[ArtifactType] = None,
        namespace: Optional[str] = None,
    ) -> List[Artifact]:
        arts = [a for a in self._artifacts.values() if a.status != ArtifactStatus.DELETED]
        if artifact_type:
            arts = [a for a in arts if a.artifact_type == artifact_type]
        if namespace:
            arts = [a for a in arts if a.namespace == namespace]
        return sorted(arts, key=lambda a: a.updated_at, reverse=True)

    def delete_artifact(self, artifact_id: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.status = ArtifactStatus.DELETED
        return True

    def apply_retention(self) -> int:
        """Remove expired versions per TTL policy. Returns count of versions removed."""
        removed = 0
        now = time.time()
        for artifact in self._artifacts.values():
            if artifact.ttl_days is None:
                continue
            ttl_secs = artifact.ttl_days * 86400
            before = len(artifact.versions)
            artifact.versions = [v for v in artifact.versions if (now - v.created_at) < ttl_secs]
            removed += before - len(artifact.versions)
        return removed

    def stats(self) -> Dict[str, Any]:
        active = [a for a in self._artifacts.values() if a.status != ArtifactStatus.DELETED]
        total_versions = sum(len(a.versions) for a in active)
        by_type: Dict[str, int] = {}
        for a in active:
            by_type[a.artifact_type.value] = by_type.get(a.artifact_type.value, 0) + 1
        return {
            "service": "the-artifactory",
            "total_artifacts": len(active),
            "total_versions": total_versions,
            "by_type": by_type,
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe
            observe(event_type, category=EventCategory.SYSTEM, service="the-artifactory",
                    metadata=metadata or {})
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream



_artifactory: Optional[TheArtifactory] = None


def get_artifactory() -> TheArtifactory:
    global _artifactory
    if _artifactory is None:
        _artifactory = TheArtifactory()
    return _artifactory
