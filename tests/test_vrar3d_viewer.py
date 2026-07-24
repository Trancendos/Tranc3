"""
Tests for workers/vrar3d/main.py's viewer + asset-download addition.

VRAR3D already had a real scene/asset-conversion backend (8 zero-cost mesh
processing backends, ACO pheromone routing) but nothing served an actual
browser-renderable page or the converted file bytes — this covers the two
routes that close that gap: GET /vrar3d/viewer (static Three.js/VRM page)
and GET /vrar3d/assets/{asset_id}/download (serves a completed local job's
output file).

Note: workers/vrar3d/worker.py is a separate, dead duplicate never referenced
by workers/vrar3d/Dockerfile's CMD (which targets main:app) — not exercised
here. src/vrar3d/wellbeing_centre.py is a third, unrelated in-process VR
"wellbeing" module (see tests/test_platform_routes.py::TestVRAR3D) — also
unrelated to this worker.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker as _import_worker

_TRANC3_ROOT = Path(__file__).resolve().parent.parent
_TMP_DIR = tempfile.mkdtemp(prefix="vrar3d-test-")

os.environ["VRAR3D_DB_PATH"] = str(Path(_TMP_DIR) / "vrar3d.db")
os.environ["VRAR3D_ASSET_DIR"] = str(Path(_TMP_DIR) / "assets")
os.environ["INTERNAL_SECRET"] = "test-internal-secret"

main_mod = _import_worker("vrar3d_main", _TRANC3_ROOT / "workers" / "vrar3d" / "main.py")
# main.py's `db` is local to _build_app(), not module-level — open a second
# connection to the same on-disk SQLite file to seed asset-job rows directly.
_db = main_mod.VRARDatabase(os.environ["VRAR3D_DB_PATH"])

_HEADERS = {"x-internal-secret": "test-internal-secret"}


@pytest.fixture
def client():
    return TestClient(main_mod.app)


class TestViewerRoute:
    def test_viewer_serves_html(self, client):
        response = client.get("/vrar3d/viewer")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "VRAR3D Viewer" in response.text

    def test_viewer_static_assets_mounted(self, client):
        response = client.get("/vrar3d/static/viewer.html")
        assert response.status_code == 200
        assert "VRAR3D Viewer" in response.text


class TestAssetDownloadRoute:
    def test_download_requires_internal_secret(self, client):
        response = client.get("/vrar3d/assets/some-id/download")
        assert response.status_code == 403

    def test_download_unknown_asset_404s(self, client):
        response = client.get("/vrar3d/assets/does-not-exist/download", headers=_HEADERS)
        assert response.status_code == 404

    def test_download_serves_completed_local_job(self, client):
        asset_dir = Path(os.environ["VRAR3D_ASSET_DIR"])
        asset_dir.mkdir(parents=True, exist_ok=True)
        output_file = asset_dir / "job-1.glb"
        output_file.write_bytes(b"not-a-real-glb-but-a-real-file")

        _db.save_asset_job(
            {
                "asset_id": "job-1",
                "scene_id": None,
                "source_format": "obj",
                "target_format": "glb",
                "backend": "trimesh",
                "status": "done",
                "output_path": str(output_file),
            }
        )

        response = client.get("/vrar3d/assets/job-1/download", headers=_HEADERS)
        assert response.status_code == 200
        assert response.content == b"not-a-real-glb-but-a-real-file"

    def test_download_rejects_remote_output_path(self, client):
        # e.g. the sketchfab backend returns a hosted URL, not a local file —
        # the browser should fetch that URL directly, not through this route.
        _db.save_asset_job(
            {
                "asset_id": "job-remote",
                "scene_id": None,
                "source_format": "obj",
                "target_format": "glb",
                "backend": "sketchfab",
                "status": "done",
                "output_path": "https://sketchfab.com/models/abc123",
            }
        )
        response = client.get("/vrar3d/assets/job-remote/download", headers=_HEADERS)
        assert response.status_code == 404

    def test_download_rejects_unfinished_job(self, client):
        _db.save_asset_job(
            {
                "asset_id": "job-pending",
                "scene_id": None,
                "source_format": "obj",
                "target_format": "glb",
                "backend": "trimesh",
                "status": "failed",
                "output_path": None,
            }
        )
        response = client.get("/vrar3d/assets/job-pending/download", headers=_HEADERS)
        assert response.status_code == 404
