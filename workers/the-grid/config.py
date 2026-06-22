"""The Digital Grid — Configuration"""
from __future__ import annotations

import os
from pathlib import Path

WORKER_PORT = 8010
WORKER_NAME = "the-grid-api"
DB_PATH = Path(__file__).parent / "data" / "grid.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

# ── Engine URLs (all zero-cost / self-hosted) ───────────────────────────────
N8N_URL = os.environ.get("N8N_URL", "http://n8n:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

PREFECT_URL = os.environ.get("PREFECT_URL", "http://prefect-server:4200")

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "temporalite:7233")

AIRFLOW_URL = os.environ.get("AIRFLOW_URL", "http://airflow:8089")
AIRFLOW_USER = os.environ.get("AIRFLOW_USER", "admin")
AIRFLOW_PASS = os.environ.get("AIRFLOW_PASS", "admin")

DAGSTER_URL = os.environ.get("DAGSTER_URL", "http://dagster-webserver:3002")

# ── Threshold guards (requests per sliding window before hard-stop) ──────────
THRESHOLD_N8N = int(os.environ.get("THRESHOLD_N8N", "500"))
THRESHOLD_PREFECT = int(os.environ.get("THRESHOLD_PREFECT", "500"))
THRESHOLD_TEMPORAL = int(os.environ.get("THRESHOLD_TEMPORAL", "500"))
THRESHOLD_AIRFLOW = int(os.environ.get("THRESHOLD_AIRFLOW", "500"))
THRESHOLD_DAGSTER = int(os.environ.get("THRESHOLD_DAGSTER", "500"))
THRESHOLD_LUIGI = int(os.environ.get("THRESHOLD_LUIGI", "1000"))
THRESHOLD_WINDOW_SECONDS = int(os.environ.get("THRESHOLD_WINDOW_SECONDS", "3600"))

# ── ACO pheromone decay (0–1; lower = faster decay) ─────────────────────────
ACO_DECAY = float(os.environ.get("ACO_DECAY", "0.9"))

# ── Engine routing toggle (set to "internal" to bypass all external engines) ─
FORCE_ENGINE = os.environ.get("FORCE_ENGINE", "")  # internal|n8n|prefect|…|offline
