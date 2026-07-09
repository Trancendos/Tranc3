"""Tests for admin-gated auth on Cryptex's IP block and bounty-scan routes.

Guards against regressing to the previous behaviour where POST/DELETE
/cryptex/block/{ip} and every /cryptex/bounty/* route were reachable by
anyone with no authentication at all — including the ability to trigger a
scan against caller-controlled infrastructure (fixed here to always target
BOUNTY_TARGET_URL, never a caller-supplied target).
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.cryptex.routes import router as cryptex_router

app = FastAPI()
app.include_router(cryptex_router)
client = TestClient(app)


def _override(role: str = "user"):
    def _dep():
        return {"id": "u1", "role": role}

    return _dep


def test_stats_is_public():
    resp = client.get("/cryptex/stats")
    assert resp.status_code == 200


def test_block_ip_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post("/cryptex/block/1.2.3.4")
    assert resp.status_code in (401, 403)


def test_block_ip_requires_admin_role():
    app.dependency_overrides[get_current_user] = _override("user")
    try:
        resp = client.post("/cryptex/block/1.2.3.4")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_block_and_unblock_ip():
    app.dependency_overrides[get_current_user] = _override("admin")
    try:
        resp = client.post("/cryptex/block/1.2.3.4")
        assert resp.status_code == 200
        resp = client.delete("/cryptex/block/1.2.3.4")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_bounty_scan_requires_admin():
    app.dependency_overrides[get_current_user] = _override("user")
    try:
        resp = client.post("/cryptex/bounty/scan")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_bounty_scan_ignores_caller_target_and_requires_admin():
    app.dependency_overrides[get_current_user] = _override("admin")
    try:
        with patch("src.cryptex.bounty_hunter.run_full_scan") as mock_scan:
            resp = client.post("/cryptex/bounty/scan?target=http://evil.example.com")
        assert resp.status_code == 200
        assert "target" not in resp.json()
        # No caller-supplied target must ever reach run_full_scan.
        mock_scan.assert_called_once_with()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_bounty_candidates_requires_admin():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.get("/cryptex/bounty/candidates")
    assert resp.status_code in (401, 403)


def test_bounty_summary_requires_admin():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.get("/cryptex/bounty/summary")
    assert resp.status_code in (401, 403)
