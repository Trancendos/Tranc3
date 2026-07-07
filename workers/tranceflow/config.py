"""TranceFlow — configuration (Lead AI: Junior Cesar)"""

from __future__ import annotations

import os
import warnings

WORKER_NAME = "tranceflow"
WORKER_PORT = int(os.environ.get("PORT", os.environ.get("TRANCEFLOW_PORT", "8059")))
DB_PATH = os.environ.get("TRANCEFLOW_DB_PATH", "/data/tranceflow.db")
ASSET_DIR = os.environ.get("TRANCEFLOW_ASSET_DIR", "/data/tranceflow-assets")

# ── Processing backends (zero-cost self-hosted) ───────────────────────────────
GODOT_BIN = os.environ.get("GODOT_BIN", "godot")
GODOT_ENABLED = os.environ.get("TRANCEFLOW_GODOT", "1") == "1"

BLENDER_BIN = os.environ.get("BLENDER_BIN", "blender")
BLENDER_ENABLED = os.environ.get("TRANCEFLOW_BLENDER", "1") == "1"

TRIMESH_ENABLED = os.environ.get("TRANCEFLOW_TRIMESH", "1") == "1"
MESHIO_ENABLED = os.environ.get("TRANCEFLOW_MESHIO", "1") == "1"
OPEN3D_ENABLED = os.environ.get("TRANCEFLOW_OPEN3D", "1") == "1"
PYVISTA_ENABLED = os.environ.get("TRANCEFLOW_PYVISTA", "1") == "1"

# ── ACO / ThresholdGuard ───────────────────────────────────────────────────────
PHEROMONE_DECAY = float(os.environ.get("TRANCEFLOW_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW_SECONDS = int(os.environ.get("TRANCEFLOW_QUOTA_WINDOW", "3600"))
QUOTA_MAX_CALLS = int(os.environ.get("TRANCEFLOW_QUOTA_MAX_CALLS", "10000"))
PROBE_TIMEOUT = float(os.environ.get("TRANCEFLOW_PROBE_TIMEOUT", "5.0"))
PROCESS_TIMEOUT = float(os.environ.get("TRANCEFLOW_PROCESS_TIMEOUT", "120.0"))

# ── Internal auth ──────────────────────────────────────────────────────────────
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
if not INTERNAL_SECRET:
    warnings.warn("INTERNAL_SECRET is not set — inter-service auth disabled", stacklevel=1)

TLS_VERIFY = os.environ.get("TRANCEFLOW_TLS_VERIFY", "0") != "0"
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
