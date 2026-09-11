"""The ffmpeg worker's workdir: clean at import, checked at startup.

Moving the `mkdir` out of module import fixed nine CI collection errors and
cost something real — a mis-mounted or read-only workdir then let the worker
start clean, answer /health 200, accept every job with a 202, and fail each
one asynchronously. A broken deployment degrading silently is worse than one
that refuses to start.

Startup is the right place: not import, so the module loads anywhere; before
the first request, so the container fails rather than the jobs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(monkeypatch, workdir: Path):
    monkeypatch.setenv("INTERNAL_SECRET", "c" * 64)
    monkeypatch.setenv("FFMPEG_WORKDIR", str(workdir))
    path = REPO / "workers" / "ffmpeg-worker" / "worker.py"
    spec = importlib.util.spec_from_file_location("ffmpeg_worker_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestTheImportStaysClean:
    def test_importing_creates_nothing(self, monkeypatch, tmp_path):
        """Calibrated: restoring the module-level mkdir fails this."""
        target = tmp_path / "not-created-yet"
        _load(monkeypatch, target)
        assert not target.exists()


class TestStartupFailsLoudly:
    def test_startup_creates_the_workdir(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient

        target = tmp_path / "made-at-startup"
        module = _load(monkeypatch, target)
        with TestClient(module.app):
            assert target.exists()

    def test_an_unwritable_workdir_refuses_to_start(self, monkeypatch, tmp_path):
        """Calibrated: dropping the lifespan check fails this.

        Without it the worker starts, /health says 200, and every job 202s
        and then fails — the silent degradation the import-time mkdir used to
        prevent by crashing.
        """
        from fastapi.testclient import TestClient

        module = _load(monkeypatch, Path("/proc/nonexistent/deep"))
        with pytest.raises(RuntimeError, match="not writable"):
            with TestClient(module.app):
                pass

    def test_health_reports_the_workdir_state(self, monkeypatch, tmp_path):
        """A volume can be remounted read-only under a running container.

        Startup cannot catch that, so /health carries the state too.
        """
        from fastapi.testclient import TestClient

        module = _load(monkeypatch, tmp_path / "wd")
        with TestClient(module.app) as client:
            body = client.get("/health").json()
        assert body["workdir_writable"] is True
        assert body["workdir"].endswith("wd")
