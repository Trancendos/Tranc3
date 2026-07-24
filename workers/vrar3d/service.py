"""VRAR3D — ACO pheromone router with 8 zero-cost processing backends"""

from __future__ import annotations

import asyncio
import base64
import tempfile
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from models import (
    AssetProcessRequest,
    AssetProcessResponse,
    BackendStatus,
    ProcessingBackend,
    SceneCreate,
    SceneResponse,
    VRARStatus,
)

import config
from database import VRARDatabase


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
    ProcessingBackend.trimesh: ThresholdGuard(
        "trimesh", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.open3d: ThresholdGuard(
        "open3d", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.blender: ThresholdGuard(
        "blender", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.godot: ThresholdGuard(
        "godot", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.pyvista: ThresholdGuard(
        "pyvista", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.meshio: ThresholdGuard(
        "meshio", config.QUOTA_MAX_CALLS, config.QUOTA_WINDOW_SECONDS
    ),
    ProcessingBackend.sketchfab: ThresholdGuard("sketchfab", config.SKETCHFAB_HOURLY_LIMIT, 3600),
    ProcessingBackend.offline: ThresholdGuard("offline", 999_999, config.QUOTA_WINDOW_SECONDS),
}

_PRIORITY = [
    ProcessingBackend.trimesh,
    ProcessingBackend.open3d,
    ProcessingBackend.pyvista,
    ProcessingBackend.meshio,
    ProcessingBackend.blender,
    ProcessingBackend.godot,
    ProcessingBackend.sketchfab,
    ProcessingBackend.offline,
]


def _select_backend() -> Optional[ProcessingBackend]:
    available = [b for b in _PRIORITY if _GUARDS[b].can_allow()]
    if not available:
        return None
    return max(available, key=lambda b: _GUARDS[b].pheromone)


async def _call_trimesh(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    try:
        import trimesh  # type: ignore[import-untyped]

        mesh = trimesh.load(src_path)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        mesh.export(out)
        return out
    except Exception:
        return None


async def _call_open3d(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    try:
        import open3d as o3d  # type: ignore[import-untyped]

        mesh = o3d.io.read_triangle_mesh(src_path)
        if optimize:
            mesh = mesh.simplify_quadric_decimation(100_000)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        o3d.io.write_triangle_mesh(out, mesh)
        return out
    except Exception:
        return None


async def _call_blender(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    script = f"""
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.obj(filepath='{src_path}') if '{src_fmt}' == 'obj' else None
bpy.ops.import_scene.fbx(filepath='{src_path}') if '{src_fmt}' == 'fbx' else None
bpy.ops.export_scene.gltf(filepath='{src_path.replace(src_fmt, tgt_fmt)}',
    export_format='GLB' if '{tgt_fmt}' == 'glb' else 'GLTF_SEPARATE')
"""
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(script)
            script_path = f.name
        proc = await asyncio.create_subprocess_exec(
            config.BLENDER_BIN,
            "--background",
            "--python",
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=config.PROCESS_TIMEOUT)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_godot(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            config.GODOT_BIN,
            "--headless",
            "--export-pack",
            tgt_fmt,
            src_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=config.PROCESS_TIMEOUT)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_pyvista(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    try:
        import pyvista as pv  # type: ignore[import-untyped]

        mesh = pv.read(src_path)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        mesh.save(out)
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_meshio(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> Optional[str]:
    try:
        import meshio  # type: ignore[import-untyped]

        mesh = meshio.read(src_path)
        out = src_path.replace(f".{src_fmt}", f".{tgt_fmt}")
        meshio.write(out, mesh)
        return out if Path(out).exists() else None
    except Exception:
        return None


async def _call_sketchfab(
    src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool
) -> Optional[str]:
    if not config.SKETCHFAB_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=config.PROCESS_TIMEOUT) as client:
            with open(src_path, "rb") as f:
                resp = await client.post(
                    "https://api.sketchfab.com/v3/models",
                    headers={"Authorization": f"Token {config.SKETCHFAB_API_KEY}"},
                    files={"modelFile": (Path(src_path).name, f)},
                    data={"name": Path(src_path).stem, "isPublished": "false"},
                )
            if resp.status_code not in (200, 201):
                return None
            uid = resp.json().get("uid")
            return f"https://sketchfab.com/models/{uid}" if uid else None
    except Exception:
        return None


def _offline_process(src_path: str, src_fmt: str, tgt_fmt: str, optimize: bool) -> str:
    return f"offline://{src_fmt}:{tgt_fmt}:{Path(src_path).name}"


def _renderer_hints(scene_data: Dict[str, Any]) -> List[str]:
    hints = list(config.RENDERER_PRIORITY)
    if scene_data.get("xr_enabled"):
        hints = ["aframe"] + [h for h in hints if h != "aframe"]
    if scene_data.get("physics_enabled"):
        hints = ["babylonjs"] + [h for h in hints if h != "babylonjs"]
    return hints


def _cdn_urls() -> Dict[str, str]:
    return {
        "threejs": config.THREEJS_CDN,
        "babylonjs": config.BABYLONJS_CDN,
        "aframe": config.AFRAME_CDN,
        "model-viewer": config.MODEL_VIEWER_CDN,
    }


class VRARRouter:
    def __init__(self, db: VRARDatabase) -> None:
        self._db = db

    def create_scene(self, req: SceneCreate) -> SceneResponse:
        scene_id = str(uuid.uuid4())
        data: Dict[str, Any] = {
            "scene_id": scene_id,
            "name": req.name,
            "scene_type": req.scene_type.value,
            "description": req.description,
            "objects": [o.model_dump() for o in req.objects],
            "environment": req.environment,
            "physics_enabled": req.physics_enabled,
            "xr_enabled": req.xr_enabled,
            "preferred_engine": req.preferred_engine.value if req.preferred_engine else None,
            "metadata": req.metadata,
        }
        saved = self._db.save_scene(data)
        return SceneResponse(
            **saved,
            renderer_hints=_renderer_hints(saved),
            cdn_urls=_cdn_urls(),
        )

    def get_scene(self, scene_id: str) -> Optional[SceneResponse]:
        row = self._db.get_scene(scene_id)
        if not row:
            return None
        return SceneResponse(**row, renderer_hints=_renderer_hints(row), cdn_urls=_cdn_urls())

    def list_scenes(
        self, scene_type: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[SceneResponse]:
        rows = self._db.list_scenes(scene_type=scene_type, limit=limit, offset=offset)
        return [
            SceneResponse(**r, renderer_hints=_renderer_hints(r), cdn_urls=_cdn_urls())
            for r in rows
        ]

    def delete_scene(self, scene_id: str) -> bool:
        return self._db.delete_scene(scene_id)

    async def process_asset(self, req: AssetProcessRequest) -> AssetProcessResponse:
        backend = _select_backend()
        if backend is None:
            backend = ProcessingBackend.offline

        guard = _GUARDS[backend]
        guard.record()

        job_id = str(uuid.uuid4())
        start = time.time()

        asset_path = str(Path(config.ASSET_DIR) / f"{job_id}.{req.source_format.value}")
        Path(config.ASSET_DIR).mkdir(parents=True, exist_ok=True)

        if req.asset_data_b64:
            with open(asset_path, "wb") as f:
                f.write(base64.b64decode(req.asset_data_b64))
        elif req.asset_url:
            try:
                async with httpx.AsyncClient(
                    timeout=config.PROBE_TIMEOUT,
                    verify=config.TLS_VERIFY,
                ) as client:
                    r = await client.get(req.asset_url)
                    with open(asset_path, "wb") as f:
                        f.write(r.content)
            except Exception:
                guard.decay()
                self._db.record_event(backend.value, False)
                return AssetProcessResponse(
                    job_id=job_id,
                    scene_id=req.scene_id,
                    source_format=req.source_format,
                    target_format=req.target_format,
                    backend=backend,
                    status="failed",
                    latency_ms=(time.time() - start) * 1000,
                )
        else:
            asset_path = f"/dev/null.{req.source_format.value}"

        _adapters = {
            ProcessingBackend.trimesh: _call_trimesh,
            ProcessingBackend.open3d: _call_open3d,
            ProcessingBackend.blender: _call_blender,
            ProcessingBackend.godot: _call_godot,
            ProcessingBackend.pyvista: _call_pyvista,
            ProcessingBackend.meshio: _call_meshio,
            ProcessingBackend.sketchfab: _call_sketchfab,
        }

        output_path: Optional[str] = None
        if backend == ProcessingBackend.offline:
            output_path = _offline_process(
                asset_path, req.source_format.value, req.target_format.value, req.optimize
            )
            success = True
        else:
            adapter = _adapters[backend]
            output_path = await adapter(
                asset_path, req.source_format.value, req.target_format.value, req.optimize
            )
            success = output_path is not None

        latency_ms = (time.time() - start) * 1000

        if success:
            guard.reinforce()
        else:
            guard.decay()

        self._db.record_event(backend.value, success)
        self._db.save_asset_job(
            {
                "asset_id": job_id,
                "scene_id": req.scene_id,
                "source_format": req.source_format.value,
                "target_format": req.target_format.value,
                "backend": backend.value,
                "status": "done" if success else "failed",
                "output_path": output_path,
                "metadata": req.metadata,
            }
        )

        return AssetProcessResponse(
            job_id=job_id,
            scene_id=req.scene_id,
            source_format=req.source_format,
            target_format=req.target_format,
            backend=backend,
            status="done" if success else "failed",
            output_url=output_path,
            latency_ms=latency_ms,
        )

    def get_asset_download_path(self, asset_id: str) -> Optional[str]:
        """
        Resolve a completed asset job to a locally-servable file path.

        Returns None for unknown jobs, jobs whose status isn't "done",
        offline-backend placeholders (offline://... isn't a real file), and
        remote outputs (e.g. a Sketchfab model URL) — those are already
        directly fetchable by a browser and don't need this route.
        """
        job = self._db.get_asset_job(asset_id)
        if not job or job.get("status") != "done":
            return None
        output_path = job.get("output_path")
        if not output_path or "://" in output_path:
            return None
        resolved = Path(output_path).resolve()
        asset_dir = Path(config.ASSET_DIR).resolve()
        if not resolved.is_relative_to(asset_dir):
            # Defense-in-depth: every writer in this file already constrains
            # output_path to ASSET_DIR, but a served file should never trust
            # a DB value alone against path traversal.
            return None
        if not resolved.is_file():
            return None
        return str(resolved)

    def status(self) -> VRARStatus:
        active = _select_backend() or ProcessingBackend.offline
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
        return VRARStatus(
            active_backend=active,
            backends=backends,
            renderer_priority=config.RENDERER_PRIORITY,
            cdn_urls=_cdn_urls(),
            scene_count=self._db.count_scenes(),
        )
