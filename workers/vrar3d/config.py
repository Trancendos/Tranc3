"""VRAR3D — configuration (Lead AI: Entari)"""

from __future__ import annotations

import os
import warnings

WORKER_NAME = "vrar3d"
WORKER_PORT = int(os.environ.get("VRAR3D_PORT", "8063"))
DB_PATH = os.environ.get("VRAR3D_DB_PATH", "/data/vrar3d.db")
ASSET_DIR = os.environ.get("VRAR3D_ASSET_DIR", "/data/assets")

# ── Rendering / processing backends (all zero-cost) ───────────────────────────
# Primary: trimesh — fast Python mesh processing (MIT)
TRIMESH_ENABLED = os.environ.get("VRAR3D_TRIMESH", "1") == "1"

# Secondary: open3d — point cloud + advanced mesh ops (MIT)
OPEN3D_ENABLED = os.environ.get("VRAR3D_OPEN3D", "1") == "1"

# Tertiary: Blender headless — full 3D pipeline (GPL, self-hosted)
BLENDER_BIN = os.environ.get("BLENDER_BIN", "blender")
BLENDER_ENABLED = os.environ.get("VRAR3D_BLENDER", "1") == "1"

# Quaternary: Godot headless — game engine export (MIT, self-hosted)
GODOT_BIN = os.environ.get("GODOT_BIN", "godot")
GODOT_ENABLED = os.environ.get("VRAR3D_GODOT", "1") == "1"

# Quinary: pyvista — 3D visualisation + mesh ops (MIT)
PYVISTA_ENABLED = os.environ.get("VRAR3D_PYVISTA", "1") == "1"

# Senary: meshio — mesh format conversion (MIT)
MESHIO_ENABLED = os.environ.get("VRAR3D_MESHIO", "1") == "1"

# Cloud: Sketchfab free API (rate-limited, optional)
SKETCHFAB_API_KEY = os.environ.get("SKETCHFAB_API_KEY", "")
SKETCHFAB_HOURLY_LIMIT = int(os.environ.get("VRAR3D_SKETCHFAB_LIMIT", "100"))

# ── ACO / ThresholdGuard ───────────────────────────────────────────────────────
PHEROMONE_DECAY = float(os.environ.get("VRAR3D_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW_SECONDS = int(os.environ.get("VRAR3D_QUOTA_WINDOW", "3600"))
QUOTA_MAX_CALLS = int(os.environ.get("VRAR3D_QUOTA_MAX_CALLS", "10000"))
PROBE_TIMEOUT = float(os.environ.get("VRAR3D_PROBE_TIMEOUT", "5.0"))
PROCESS_TIMEOUT = float(os.environ.get("VRAR3D_PROCESS_TIMEOUT", "60.0"))

# ── Client-side renderer preference hints ─────────────────────────────────────
# These are returned to the browser so it picks the best renderer.
# Priority order delivered to clients: Three.js → Babylon.js → A-Frame → Model Viewer
RENDERER_PRIORITY = os.environ.get(
    "VRAR3D_RENDERER_PRIORITY", "threejs,babylonjs,aframe,model-viewer"
).split(",")

# ── CDN URLs for client-side 3D libraries (all free/OSS) ──────────────────────
THREEJS_CDN = os.environ.get(
    "THREEJS_CDN", "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js"
)
BABYLONJS_CDN = os.environ.get("BABYLONJS_CDN", "https://cdn.babylonjs.com/babylon.js")
AFRAME_CDN = os.environ.get("AFRAME_CDN", "https://aframe.io/releases/1.6.0/aframe.min.js")
MODEL_VIEWER_CDN = os.environ.get(
    "MODEL_VIEWER_CDN",
    "https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js",
)

# ── Internal auth ──────────────────────────────────────────────────────────────
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
if not INTERNAL_SECRET:
    warnings.warn("INTERNAL_SECRET is not set — inter-service auth disabled", stacklevel=1)

TLS_VERIFY = os.environ.get("VRAR3D_TLS_VERIFY", "0") != "0"
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
