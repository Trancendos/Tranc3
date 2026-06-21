"""
Shared fixtures for infinity-ai tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure the worker directory is on sys.path so absolute imports work
WORKER_DIR = Path(__file__).parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

# ---------------------------------------------------------------------------
# Stubs for optional / heavyweight dependencies that may not be installed
# ---------------------------------------------------------------------------

# Dimensional.sanitize
dim_mod = MagicMock()
dim_mod.sanitize_for_log = lambda x: str(x)
sys.modules.setdefault("Dimensional", MagicMock())
sys.modules.setdefault("Dimensional.sanitize", dim_mod)

# src.* — optional integrations
for _pkg in [
    "src",
    "src.ai_gateway",
    "src.ai_gateway.smart_cache",
    "src.ai_gateway.limit_monitor",
    "src.adaptive",
    "src.adaptive.provider_rotator",
    "src.observability",
    "src.observability.otel",
    "opentelemetry",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.fastapi",
]:
    sys.modules.setdefault(_pkg, MagicMock())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    """Return an AIDatabase backed by a temp file."""
    from database import AIDatabase

    return AIDatabase(tmp_path / "test_ai_gateway.db")


@pytest.fixture()
def gateway(tmp_db):
    """Return an AIGatewayRouter wired to a temp database."""
    from service import AIGatewayRouter

    return AIGatewayRouter(tmp_db)


@pytest.fixture()
def test_app(tmp_db, gateway):
    """Return a TestClient for the FastAPI app with temp DB/gateway injected."""
    import router as router_mod
    from fastapi.testclient import TestClient

    router_mod.init_router(tmp_db, gateway)

    from main import app

    return TestClient(app)
