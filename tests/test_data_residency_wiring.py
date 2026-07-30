# tests/test_data_residency_wiring.py
# Tests for the staged, warn-only-first rollout of DataResidencyMiddleware
# into api.py (task: "Stage data_residency.py rollout"). src/storage/data_residency.py
# itself is covered by tests/test_data_residency.py; this file covers only the
# api.py wiring decision: disabled by default, and defaulting to warn-only when
# enabled unless the operator explicitly opts into enforcement.
#
# Uses a subprocess per case because api.py's middleware wiring runs once at
# import time, keyed off environment variables read before the module is
# first imported — a single pytest process can't re-run that decision twice.

import subprocess
import sys
import textwrap

_BASE_ENV_SETUP = """
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-0000001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MASTER_KEY_SEED", "test-master-key-seed-for-unit-tests-0001")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-for-unit-tests-001")
from unittest.mock import MagicMock, patch
with patch(
    "redis.from_url",
    return_value=MagicMock(ping=lambda: True, get=lambda k: None, set=lambda *a, **kw: True),
):
    import api

names = [type(m).__name__ if not hasattr(m, "cls") else m.cls.__name__ for m in api.app.user_middleware]
print("MIDDLEWARE_PRESENT=" + str("DataResidencyMiddleware" in names))
print("ENFORCE=" + os.environ.get("DATA_RESIDENCY_ENFORCE", "<unset>"))
"""


def _run(extra_env: dict) -> dict:
    import os

    env = dict(os.environ)
    env.pop("DATA_RESIDENCY_MIDDLEWARE_ENABLED", None)
    env.pop("DATA_RESIDENCY_ENFORCE", None)
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_BASE_ENV_SETUP)],
        cwd=str(__file__.rsplit("/tests/", 1)[0]),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key] = value
    return out


class TestDataResidencyStagedRollout:
    def test_disabled_by_default(self):
        out = _run({})
        assert out["MIDDLEWARE_PRESENT"] == "False"

    def test_enabled_defaults_to_warn_only(self):
        out = _run({"DATA_RESIDENCY_MIDDLEWARE_ENABLED": "true"})
        assert out["MIDDLEWARE_PRESENT"] == "True"
        assert out["ENFORCE"] == "false"

    def test_enabled_respects_explicit_enforce_true(self):
        out = _run(
            {
                "DATA_RESIDENCY_MIDDLEWARE_ENABLED": "true",
                "DATA_RESIDENCY_ENFORCE": "true",
            }
        )
        assert out["MIDDLEWARE_PRESENT"] == "True"
        assert out["ENFORCE"] == "true"
