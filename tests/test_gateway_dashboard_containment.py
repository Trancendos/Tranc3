"""Traversal containment for gateway-service's dashboard static-file route.

SEC-016. ``GET /dashboard/{path:path}`` joined the remainder of the URL onto
``DASHBOARD_DIR`` with no containment check and served whatever was there.

This module lives in ``tests/`` rather than ``workers/gateway-service/tests/``
on purpose. That suite exists, has a conftest and a TestClient, and is not run
by any workflow: ``ci.yml``'s Pytest job runs ``pytest tests/ -q``, and nothing
in ``.github/workflows/`` names a worker suite. A regression test for an
exploitable traversal has to sit where the gate can see it.

Importing the worker needs its own directory on ``sys.path`` and three env vars,
exactly as its conftest arranges. That is done here at module scope so an import
failure is a loud red test rather than a silent skip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[1] / "workers" / "gateway-service"
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32x")
os.environ.setdefault("GATEWAY_DB_PATH", ":memory:")
os.environ.setdefault("GATEWAY_CACHE_TTL", "5")
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import router as gateway_router  # noqa: E402

from Dimensional.path_validation import PathTraversalError  # noqa: E402

_contained = gateway_router._contained_dashboard_file
DASHBOARD_DIR = gateway_router.DASHBOARD_DIR


class TestRefusesTraversal:
    """Every one of these returned file contents before the fix."""

    @pytest.mark.parametrize(
        "path",
        [
            "../../../../etc/passwd",
            "../.git/config",
            "..",
            "a/../../../../etc/passwd",
            "./../../etc/hostname",
            "foo/../../bar",
        ],
    )
    def test_dotdot_is_refused(self, path: str) -> None:
        with pytest.raises((PathTraversalError, ValueError)):
            _contained(path)

    @pytest.mark.parametrize("path", ["/etc/passwd", "//etc/passwd", "/"])
    def test_absolute_path_is_contained_not_honoured(self, path: str) -> None:
        """A URL can carry a leading slash into the ``:path`` converter.

        This test first asserted a refusal, and failed — correctly. The leading
        separator is dropped and the remainder is treated as relative to the
        dashboard root, which is what every static-file server does, so
        ``/etc/passwd`` resolves to ``DASHBOARD_DIR/etc/passwd`` and is refused
        by being somewhere harmless rather than by raising. Refusal and
        containment are both acceptable answers here; containment is the one
        the requirement actually names, so that is what is asserted.
        """
        root = Path(DASHBOARD_DIR).resolve()
        assert _contained(path).is_relative_to(root)

    def test_nul_byte_is_refused(self) -> None:
        with pytest.raises((PathTraversalError, ValueError)):
            _contained("index\x00.html")


class TestServesWhatItShould:
    def test_plain_filename(self) -> None:
        assert _contained("app.js") == (DASHBOARD_DIR / "app.js").resolve()

    def test_nested_filename(self) -> None:
        assert (
            _contained("assets/css/main.css")
            == (DASHBOARD_DIR / "assets" / "css" / "main.css").resolve()
        )

    @pytest.mark.parametrize("path", ["", ".", "./"])
    def test_empty_path_falls_back_to_index(self, path: str) -> None:
        """``GET /dashboard/`` leaves the converter with an empty string.

        Without this the route 404s on its own landing URL — the shape of
        regression that makes a security fix get reverted.
        """
        assert _contained(path) == (DASHBOARD_DIR / "index.html").resolve()

    def test_every_accepted_result_is_inside_the_root(self) -> None:
        root = Path(DASHBOARD_DIR).resolve()
        for path in ["a", "a/b", "a/b/c.txt", "", "index.html", "./x"]:
            assert _contained(path).is_relative_to(root), path


class TestSymlinkOutOfRoot:
    def test_symlink_inside_root_pointing_out_is_refused(self, tmp_path: Path) -> None:
        """The property the lexical component check alone cannot give.

        ``safe_join`` resolves the joined path and re-checks containment, which
        is what catches this. Uses a temporary root rather than the real
        dashboard directory so the test never writes into the checkout.
        """
        root = tmp_path / "dashboard"
        root.mkdir()
        (root / "escape").symlink_to("/etc", target_is_directory=True)

        original = gateway_router.DASHBOARD_DIR
        try:
            gateway_router.DASHBOARD_DIR = root
            with pytest.raises((PathTraversalError, ValueError)):
                gateway_router._contained_dashboard_file("escape/passwd")
        finally:
            gateway_router.DASHBOARD_DIR = original


class TestRouteLevel:
    """End to end through Starlette, because the encoding is the exploit.

    A plain ``../`` is normalised away by every normal HTTP client, so a
    component-level test alone would not have shown why this survived review.
    """

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(gateway_router.router)
        return TestClient(app)

    @pytest.mark.parametrize(
        "probe",
        [
            "..%2f..%2f..%2f..%2fetc%2fpasswd",
            "%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            "..%2f.git%2fconfig",
            "../../../../etc/passwd",
        ],
    )
    def test_traversal_probes_return_404(self, client, probe: str) -> None:
        response = client.get(f"/dashboard/{probe}")
        assert response.status_code == 404, response.text
        assert "root:x:0:0" not in response.text
        assert "[core]" not in response.text
