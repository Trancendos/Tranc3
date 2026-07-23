"""P0 workers must import and expose entity metadata on /health."""

from __future__ import annotations

import ast
from pathlib import Path

from tests._repo_io import read_repo_text

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
        ast.parse(read_repo_text(path), filename=str(path))


def test_infinity_auth_health_includes_entity_in_source():
    # infinity-auth's /health route lives in router.py, not worker.py — the
    # latter is just a `from main import app` backwards-compat shim.
    text = read_repo_text(ROOT / "workers/infinity-auth/router.py")
    assert "health_entity_block(8005" in text
    assert '"version": "2.0.0",' in text


def test_infinity_ws_health_includes_entity_in_source():
    text = read_repo_text(ROOT / "workers/infinity-ws/worker.py")
    assert "health_entity_block(8004" in text


def test_api_health_includes_entity_in_source():
    text = read_repo_text(ROOT / "api.py")
    assert "health_entity_block(8000" in text
