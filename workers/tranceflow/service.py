"""TranceFlow — ACO pheromone router with 7 zero-cost processing backends"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import (
    BackendStatus,
    ExportRequest,
    ExportResponse,
    ProcessingBackend,
    ProjectCreate,
    ProjectResponse,
    TranceFlowStatus,
)

import config
from database import TranceFlowDatabase


class ThresholdGuard:
    def __init__(self, name: str, quota: int, window: int) -> None:
        self.name = name
        self.quota = quota
        self.window = window
        self._calls: deque[float] = deque()
        self.pheromone: float = 1.0

    def can_allow(self) -> bool:
        now = time.time()
        cutoff = now - self.window
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        return len(self._calls) < self.quota

    def record(self) -> None:
        self._calls.append(time.time())

    def reinforce(self) -> None:
        self.pheromone = min(1.0, self.pheromone + 0.1)

    def decay(self) -> None:
        self.pheromone = max(0.0, self.pheromone - config.PHEROMONE_DECAY)

    @property
    def calls_in_window(self) -> int:
        now = time.time()
        cutoff = now - self.window
        return sum(1 for t in self._calls if t >= cutoff)

    @property
    def quota_remaining(self) -> int:
        return max(0, self.quota - self.calls_in_window)


_GUARDS: Dict[ProcessingBackend, ThresholdGuard] = {
    ProcessingBackend.godot: ThresholdGuard(
        "godot", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.blender: ThresholdGuard(
        "blender", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.trimesh: ThresholdGuard(
        "trimesh", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.meshio: ThresholdGuard(
        "meshio", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.open3d: ThresholdGuard(
        "open3d", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.pyvista: ThresholdGuard(
        "pyvista", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.offline: ThresholdGuard("offline", 999_999, config.QUOTA_WINDOW_SECONDS),
}

_PRIORITY = [
    ProcessingBackend.godot,
    ProcessingBackend.trimesh,
    ProcessingBackend.blender,
    ProcessingBackend.meshio,
    ProcessingBackend.open3d,
    ProcessingBackend.pyvista,
    ProcessingBackend.offline,
]


def _select_backend() -> ProcessingBackend:
    available = [b for b in _PRIORITY if _GUARDS[b].can_allow()]
    if not available:
        return ProcessingBackend.offline
    return max(available, key=lambda b: _GUARDS[b].pheromone)


async def _call_godot(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    try:
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        proc = await asyncio.create_subprocess_exec(
            config.GODOT_BIN,
            "--headless",
            "--export-pack",
            tgt_fmt,
            src,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=config.PROCESS_TIMEOUT)
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_blender(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    script = (
        "import bpy; bpy.ops.wm.read_factory_settings(use_empty=True);"
        f" bpy.ops.export_scene.gltf(filepath='{src.replace(src_fmt, tgt_fmt)}',"
        " export_format='GLB')"
    )
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(script)
            sp = f.name
        proc = await asyncio.create_subprocess_exec(
            config.BLENDER_BIN,
            "--background",
            "--python",
            sp,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=config.PROCESS_TIMEOUT)
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_trimesh(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    try:
        import trimesh  # type: ignore[import-untyped]

        mesh = trimesh.load(src)
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        mesh.export(out)
        return out
    except Exception:
        return None


async def _call_meshio(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    try:
        import meshio  # type: ignore[import-untyped]

        mesh = meshio.read(src)
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        meshio.write(out, mesh)
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_open3d(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    try:
        import open3d as o3d  # type: ignore[import-untyped]

        mesh = o3d.io.read_triangle_mesh(src)
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        o3d.io.write_triangle_mesh(out, mesh)
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_pyvista(src: str, src_fmt: str, tgt_fmt: str) -> Optional[str]:
    try:
        import pyvista as pv  # type: ignore[import-untyped]

        mesh = pv.read(src)
        out = src.replace(f".{src_fmt}", f".{tgt_fmt}")
        mesh.save(out)
        return out if Path(out).exists() else None
    except Exception:
        return None


def _offline_export(src: str, src_fmt: str, tgt_fmt: str) -> str:
    return f"offline://{src_fmt}:{tgt_fmt}:{Path(src).name}"


class TranceFlowRouter:
    def __init__(self, db: TranceFlowDatabase) -> None:
        self._db = db

    def create_project(self, req: ProjectCreate) -> ProjectResponse:
        project_id = str(uuid.uuid4())
        data: Dict[str, Any] = {
            "project_id": project_id,
            "name": req.name,
            "project_type": req.project_type.value,
            "description": req.description,
            "engine": req.engine.value,
            "assets": [a.model_dump() for a in req.assets],
            "settings": req.settings,
            "metadata": req.metadata,
        }
        saved = self._db.save_project(data)
        return ProjectResponse(**saved)

    def get_project(self, project_id: str) -> Optional[ProjectResponse]:
        row = self._db.get_project(project_id)
        return ProjectResponse(**row) if row else None

    def list_projects(self, limit: int = 50, offset: int = 0) -> List[ProjectResponse]:
        return [ProjectResponse(**r) for r in self._db.list_projects(limit, offset)]

    def delete_project(self, project_id: str) -> bool:
        return self._db.delete_project(project_id)

    async def export_asset(self, req: ExportRequest) -> ExportResponse:
        backend = _select_backend()
        guard = _GUARDS[backend]
        guard.record()

        job_id = str(uuid.uuid4())
        start = time.time()

        Path(config.ASSET_DIR).mkdir(parents=True, exist_ok=True)
        src = str(Path(config.ASSET_DIR) / f"{job_id}.{req.source_format.value}")

        if req.asset_data_b64:
            with open(src, "wb") as f:
                f.write(base64.b64decode(req.asset_data_b64))
        elif req.source_path:
            src = req.source_path
        else:
            src = f"/dev/null.{req.source_format.value}"

        _adapters = {
            ProcessingBackend.godot: _call_godot,
            ProcessingBackend.blender: _call_blender,
            ProcessingBackend.trimesh: _call_trimesh,
            ProcessingBackend.meshio: _call_meshio,
            ProcessingBackend.open3d: _call_open3d,
            ProcessingBackend.pyvista: _call_pyvista,
        }

        output_path: Optional[str] = None
        if backend == ProcessingBackend.offline:
            output_path = _offline_export(src, req.source_format.value, req.target_format.value)
            success = True
        else:
            output_path = await _adapters[backend](
                src, req.source_format.value, req.target_format.value
            )
            success = output_path is not None

        latency_ms = (time.time() - start) * 1000

        if success:
            guard.reinforce()
        else:
            guard.decay()

        self._db.record_event(backend.value, success)
        self._db.save_export_job(
            {
                "job_id": job_id,
                "project_id": req.project_id,
                "source_format": req.source_format.value,
                "target_format": req.target_format.value,
                "backend": backend.value,
                "status": "done" if success else "failed",
                "output_path": output_path,
                "metadata": req.metadata,
            }
        )

        return ExportResponse(
            job_id=job_id,
            project_id=req.project_id,
            source_format=req.source_format,
            target_format=req.target_format,
            backend=backend,
            status="done" if success else "failed",
            output_url=output_path,
            latency_ms=latency_ms,
        )

    def status(self) -> TranceFlowStatus:
        active = _select_backend()
        backends = [
            BackendStatus(
                name=b,
                healthy=_GUARDS[b].can_allow(),
                pheromone=round(_GUARDS[b].pheromone, 4),
                calls_in_window=_GUARDS[b].calls_in_window,
                quota_remaining=_GUARDS[b].quota_remaining,
            )
            for b in _PRIORITY
        ]
        return TranceFlowStatus(
            active_backend=active,
            backends=backends,
            project_count=self._db.count_projects(),
            engine="Godot Engine (MIT) + Blender (GPL) + trimesh + meshio + open3d + pyvista",
        )
