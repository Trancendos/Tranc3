"""P0 workers must import and expose entity metadata on /health."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

P0_WORKERS = [
    ("workers/infinity-auth/worker.py", 8005),
    ("workers/infinity-ws/worker.py", 8004),
    ("workers/api-gateway/worker.py", 8003),
    ("workers/infinity-void/worker.py", 8002),
    ("workers/tranc3-ai/worker.py", 8001),
]


def test_p0_worker_files_parse():
    for rel, _port in P0_WORKERS:
        path = ROOT / rel
        ast.parse(path.read_text(), filename=str(path))


def test_infinity_auth_health_includes_entity_in_source():
    text = (ROOT / "workers/infinity-auth/worker.py").read_text()
    assert "health_entity_block(8005" in text
    assert '"version": "2.0.0",' in text


def test_infinity_ws_health_includes_entity_in_source():
    text = (ROOT / "workers/infinity-ws/worker.py").read_text()
    assert "health_entity_block(8004" in text


def test_api_health_includes_entity_in_source():
    text = (ROOT / "api.py").read_text()
    assert "health_entity_block(8000" in text
