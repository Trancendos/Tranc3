"""
Trancendos blender-worker — Self-Hosted Worker
===============================================
Headless Blender rendering and 3D scene creation for TranceFlow
(3D modeling & games creation studio).

Port: 8050
Zero-cost: FastAPI + subprocess Blender, no external deps.
Gracefully degrades to 503 when Blender is not installed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

WORKER_PORT = 8050
WORKER_NAME = "blender-worker"

RENDERS_DIR = Path(os.environ.get("RENDERS_DIR", "/app/renders"))
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

STARTED_AT = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Blender availability check
# ---------------------------------------------------------------------------

_BLENDER_PATH: str | None = None


def _find_blender() -> str | None:
    """Return the path to the blender executable, or None if not found."""
    candidate = shutil.which("blender")
    if candidate:
        return candidate
    # Common installation paths on Linux
    for path in [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/opt/blender/blender",
        "/snap/bin/blender",
    ]:
        if Path(path).is_file():
            return path
    return None


def blender_available() -> str | None:
    global _BLENDER_PATH
    if _BLENDER_PATH is None:
        _BLENDER_PATH = _find_blender()
    return _BLENDER_PATH


def _unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "available": False,
            "reason": "blender not installed",
            "hint": (
                "Install Blender (https://www.blender.org/download/) and ensure "
                "the `blender` executable is on PATH or at a standard location."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RenderRequest(BaseModel):
    script: str
    timeout: int = 120


class SceneObject(BaseModel):
    type: str = "cube"
    location: list[float] = [0.0, 0.0, 0.0]
    rotation: list[float] = [0.0, 0.0, 0.0]
    scale: list[float] = [1.0, 1.0, 1.0]
    name: str | None = None


class CreateSceneRequest(BaseModel):
    objects: list[SceneObject] = []
    render: bool = False
    output_format: str = "PNG"
    timeout: int = 120


# ---------------------------------------------------------------------------
# Helper: run blender subprocess
# ---------------------------------------------------------------------------


def _run_blender(script: str, timeout: int) -> dict[str, Any]:
    """Write *script* to a temp file and run it headlessly with Blender.

    Returns a dict with keys: success, stdout, stderr, returncode.
    """
    blender = blender_available()
    if not blender:
        return {
            "success": False,
            "stdout": "",
            "stderr": "blender not installed",
            "returncode": -1,
        }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="/tmp"
    ) as tmp:
        tmp.write(script)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [blender, "--background", "--python", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-4096:] if result.stdout else "",
            "stderr": result.stderr[-4096:] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Blender process timed out after {timeout}s",
            "returncode": -1,
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Scene script builder
# ---------------------------------------------------------------------------

_OBJECT_TYPE_MAP = {
    "cube": "mesh.primitive_cube_add",
    "sphere": "mesh.primitive_uv_sphere_add",
    "cylinder": "mesh.primitive_cylinder_add",
    "cone": "mesh.primitive_cone_add",
    "torus": "mesh.primitive_torus_add",
    "plane": "mesh.primitive_plane_add",
    "monkey": "mesh.primitive_monkey_add",
}


def _build_scene_script(
    objects: list[SceneObject],
    render: bool,
    output_path: str,
    output_format: str,
) -> str:
    lines = [
        "import bpy",
        "# Clear scene",
        "bpy.ops.wm.read_factory_settings(use_empty=True)",
        "# Add default light",
        "bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))",
        "# Add camera",
        "bpy.ops.object.camera_add(location=(7, -7, 5))",
        "bpy.context.scene.camera = bpy.context.active_object",
        "",
    ]

    for i, obj in enumerate(objects):
        op = _OBJECT_TYPE_MAP.get(obj.type.lower(), "mesh.primitive_cube_add")
        loc = repr(tuple(obj.location))
        rot = repr(tuple(obj.rotation))
        lines.append(f"# Object {i}: {obj.type}")
        lines.append(f"bpy.ops.{op}(location={loc})")
        lines.append("active = bpy.context.active_object")
        if obj.name:
            lines.append(f"active.name = {repr(obj.name)}")
        if obj.rotation != [0.0, 0.0, 0.0]:
            lines.append(f"active.rotation_euler = {rot}")
        if obj.scale != [1.0, 1.0, 1.0]:
            lines.append(f"active.scale = {repr(tuple(obj.scale))}")
        lines.append("")

    if render:
        lines += [
            f"bpy.context.scene.render.filepath = {repr(output_path)}",
            f"bpy.context.scene.render.image_settings.file_format = {repr(output_format)}",
            "bpy.ops.render.render(write_still=True)",
            "print('RENDER_COMPLETE:' + bpy.context.scene.render.filepath)",
        ]
    else:
        lines.append("print('SCENE_CREATED:OK')")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    blender_path = blender_available()
    if blender_path:
        logger.info("Blender found at: %s", blender_path)
    else:
        logger.warning(
            "Blender not found in PATH or standard locations — "
            "all render/scene endpoints will return 503."
        )
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="blender-worker",
    description="Headless Blender rendering for TranceFlow (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    blender_path = blender_available()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "blender_available": blender_path is not None,
        "blender_path": blender_path,
        "entity": {
            "platform_service": "TranceFlow",
            "lead_ai": "Junior Cesar",
            "role": "3D modeling & games creation studio",
            "status": "Planned",
        },
    }


@app.post("/render")
async def render_script(req: RenderRequest):
    """Run an arbitrary Blender Python script headlessly.

    Accepts ``{"script": "<blender python code>"}`` and returns the process
    output.  Returns 503 if Blender is not installed.
    """
    if not blender_available():
        return _unavailable_response()

    logger.info("Running render script (timeout=%ds)", req.timeout)
    result = _run_blender(req.script, req.timeout)

    status_code = 200 if result["success"] else 500
    return JSONResponse(
        status_code=status_code,
        content={
            "success": result["success"],
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        },
    )


@app.post("/blend/create")
async def create_scene(req: CreateSceneRequest):
    """Create a 3D scene from a JSON description.

    Accepts a list of objects with type, location, rotation, and scale.
    Optionally renders the scene to a PNG file.
    Returns 503 if Blender is not installed.
    """
    if not blender_available():
        return _unavailable_response()

    output_path = ""
    if req.render:
        import uuid

        output_name = f"render_{uuid.uuid4().hex[:8]}"
        output_path = str(RENDERS_DIR / output_name)

    script = _build_scene_script(
        req.objects,
        req.render,
        output_path,
        req.output_format.upper(),
    )

    logger.info(
        "Creating scene: %d objects, render=%s, timeout=%ds",
        len(req.objects),
        req.render,
        req.timeout,
    )
    result = _run_blender(script, req.timeout)

    response_body: dict[str, Any] = {
        "success": result["success"],
        "object_count": len(req.objects),
        "rendered": req.render and result["success"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }

    if req.render and result["success"]:
        # Blender appends the frame number, e.g. output0001.png
        rendered_files = list(RENDERS_DIR.glob(f"{Path(output_path).name}*.png"))
        response_body["render_files"] = [str(f) for f in rendered_files]

    status_code = 200 if result["success"] else 500
    return JSONResponse(status_code=status_code, content=response_body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
