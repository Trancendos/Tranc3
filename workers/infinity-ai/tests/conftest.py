"""
Shared fixtures for infinity-ai tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# Ensure the worker directory is on sys.path so absolute imports work
WORKER_DIR = Path(__file__).parent.parent
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

# ---------------------------------------------------------------------------
# Stubs for optional / heavyweight dependencies that may not be installed
# ---------------------------------------------------------------------------

# Dimensional is IN THIS REPOSITORY, not an optional dependency, so it is
# imported rather than stubbed.
#
# This block used to read `sys.modules.setdefault("Dimensionals", MagicMock())`,
# which replaced the whole package with an object that is not a package. Every
# `from Dimensionals.<submodule> import ...` in the worker then failed with
# "'Dimensionals' is not a package" — 10 collection errors out of 18 tests here.
#
# It went unnoticed because nothing runs this suite: `ci.yml` runs
# `pytest tests/`, `pyproject.toml` sets `testpaths = ["tests"]`, and no workflow
# names a worker suite. The import it breaks — `Dimensionals.service_auth_fastapi`
# — was added to this worker by `scripts/migrate_internal_auth.py`, after this
# stub was written. A stub frozen against an older version of the code it stands
# in for, with no gate to notice the drift.
_REPO_ROOT = WORKER_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

try:  # pragma: no cover - exercised by which branch the environment takes
    import Dimensionals.sanitize  # noqa: F401
except ImportError:
    # Only if the real package genuinely cannot be imported. Stub the SUBMODULE,
    # never the package: a MagicMock package breaks every sibling import.
    dim_pkg = ModuleType("Dimensionals")
    dim_pkg.__path__ = []  # marks it as a package so submodule imports resolve
    dim_mod = MagicMock()
    dim_mod.sanitize_for_log = lambda x: str(x)
    sys.modules.setdefault("Dimensionals", dim_pkg)
    sys.modules.setdefault("Dimensionals.sanitize", dim_mod)

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


@pytest.fixture(scope="session")
def _internal_secret_env():
    """Yield the INTERNAL_SECRET the session is already running with.

    `config.py` reads `INTERNAL_SECRET` at import time and defaults it to `""`,
    which `guard_internal_secret` treats as fail-closed, so the tests need a
    value — but they must not CHANGE one.

    This fixture first set its own secret, and the repository's shared-auth-env
    guard in `tests/conftest.py` caught it: "left a shared auth env var changed
    ... later-imported modules capture these into module-level constants, so this
    makes unrelated tests fail depending on collection order". Which is precisely
    the hazard, and precisely why the guard exists. The root conftest already
    sets a session-wide value; reading it is both correct and one less thing to
    keep in sync.

    The fallback covers this suite being run on its own, where the root conftest
    may not have loaded.
    """
    return os.environ.get("INTERNAL_SECRET") or "test-internal-secret-for-unit-tests-001"


@pytest.fixture()
def test_app(tmp_db, gateway, _internal_secret_env):
    """Return a TestClient for the FastAPI app with temp DB/gateway injected.

    Sends `x-internal-secret` by default. `scripts/migrate_internal_auth.py`
    added `guard_internal_secret` to this worker's routes after these tests were
    written, and the conftest's `Dimensional` MagicMock stub had been standing in
    for the guard — so the tests passed by neutering the very control the
    migration added. With the real package importable, they correctly get 401
    until the header is sent.

    A test that wants the unauthenticated path should build its own client, or
    pass `headers={}` to a request, rather than removing this default.
    """
    import router as router_mod
    from fastapi.testclient import TestClient

    router_mod.init_router(tmp_db, gateway)

    from main import app

    return TestClient(app, headers={"x-internal-secret": _internal_secret_env})
