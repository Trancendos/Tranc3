# src/studio/hub.py
# The Studio — Trancendos creativity hub.
#
# The Studio orchestrates creative sub-services:
#   - Sashas Photo Studio (image creation/editing via Stable Diffusion + ComfyUI)
#   - TateKing (video creation/editing via FFmpeg)
#   - TranceFlow (3D game development via Godot Engine)
#   - Fabulousa (UX/UI + Aria styling via Penpot)
#   - The Imaginarium (unified creative megahub)
#
# In this scaffold, each sub-service is represented as a StudioService record
# that tracks availability, capability manifest, and job queue depth.
# When the foundation services (ComfyUI, FFmpeg, Godot, Penpot) are wired in,
# the dispatch layer here routes jobs to the correct backend.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StudioServiceType(str, Enum):
    PHOTO = "sashas-photo-studio"
    VIDEO = "tatekings"
    GAME_DEV = "tranceflow"
    UI_DESIGN = "fabulousa"
    IMAGINARIUM = "imaginarium"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class StudioJob:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service: StudioServiceType = StudioServiceType.IMAGINARIUM
    created_at: float = field(default_factory=time.time)
    status: JobStatus = JobStatus.QUEUED
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "service": self.service.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "result": self.result,
            "error": self.error,
        }


# Capability manifests for each sub-service
_CAPABILITIES: Dict[StudioServiceType, Dict[str, Any]] = {
    StudioServiceType.PHOTO: {
        "name": "Sasha's Photo Studio",
        "description": "AI image creation and editing — Stable Diffusion + ComfyUI",
        "foundation": "Stable Diffusion / ComfyUI",
        "capabilities": [
            "text-to-image",
            "img2img",
            "inpainting",
            "upscaling",
            "style-transfer",
        ],
        "status": "planned",
    },
    StudioServiceType.VIDEO: {
        "name": "TateKing",
        "description": "Video creation and editing — FFmpeg + custom UI",
        "foundation": "FFmpeg",
        "capabilities": [
            "transcoding",
            "trim-merge",
            "subtitles",
            "transitions",
            "audio-mix",
        ],
        "status": "planned",
    },
    StudioServiceType.GAME_DEV: {
        "name": "TranceFlow",
        "description": "3D game development studio — Godot Engine integration",
        "foundation": "Godot Engine",
        "capabilities": ["scene-management", "asset-pipeline", "script-gen", "export"],
        "status": "planned",
    },
    StudioServiceType.UI_DESIGN: {
        "name": "Fabulousa",
        "description": "UX/UI + Aria styling and design platform — Penpot self-hosted",
        "foundation": "Penpot",
        "capabilities": [
            "wireframing",
            "prototyping",
            "design-tokens",
            "handoff",
            "aria-audit",
        ],
        "status": "planned",
    },
    StudioServiceType.IMAGINARIUM: {
        "name": "The Imaginarium",
        "description": "Creative megahub — orchestrates all Studio sub-services",
        "foundation": "Fabulousa + TateKing + TranceFlow + Studio + Photo",
        "capabilities": ["job-routing", "multi-service-projects", "asset-library"],
        "status": "scaffold",
    },
}


class TheStudio:
    """
    The Studio — creativity hub and sub-service orchestrator.
    """

    def __init__(self):
        self._jobs: Dict[str, StudioJob] = {}

    def submit_job(
        self,
        service: StudioServiceType,
        payload: Dict[str, Any],
    ) -> StudioJob:
        job = StudioJob(service=service, payload=payload)
        self._jobs[job.id] = job
        self._emit(job)
        logger.info("studio: job submitted id=%s service=%s", job.id, service.value)
        return job

    def get_job(self, job_id: str) -> Optional[StudioJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, service: Optional[StudioServiceType] = None) -> List[StudioJob]:
        jobs = list(self._jobs.values())
        if service:
            jobs = [j for j in jobs if j.service == service]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:50]

    def capabilities(self) -> Dict[str, Any]:
        return {k.value: v for k, v in _CAPABILITIES.items()}

    def stats(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for j in self._jobs.values():
            by_status[j.status.value] = by_status.get(j.status.value, 0) + 1
        return {
            "service": "the-studio",
            "total_jobs": len(self._jobs),
            "by_status": by_status,
            "sub_services": list(StudioServiceType),
        }

    def _emit(self, job: StudioJob) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                "studio.job.submitted",
                category=EventCategory.DATA,
                service="the-studio",
                metadata={"job_id": job.id, "sub_service": job.service.value},
            )
        except Exception:  # noqa: S110
            pass  # nosec B110 — graceful degradation; error logged upstream


_studio: Optional[TheStudio] = None


def get_studio() -> TheStudio:
    global _studio
    if _studio is None:
        _studio = TheStudio()
    return _studio
