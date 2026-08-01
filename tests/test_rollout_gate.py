# tests/test_rollout_gate.py
"""Staged-rollout gate: stage resolution, caps, invite codes, fail-closed."""

import pytest

from src.auth import rollout_gate


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ROLLOUT_STAGE", raising=False)
    monkeypatch.delenv("ROLLOUT_INVITE_CODE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


class TestStageResolution:
    def test_default_outside_production_is_public(self):
        assert rollout_gate.current_stage() == "public"

    def test_default_in_production_is_owner_fail_closed(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert rollout_gate.current_stage() == "owner"

    def test_unknown_value_in_production_fails_closed(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ROLLOUT_STAGE", "beta-2")
        assert rollout_gate.current_stage() == "owner"

    def test_explicit_stage_wins_regardless_of_environment(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ROLLOUT_STAGE", "extended_beta")
        assert rollout_gate.current_stage() == "extended_beta"

    def test_stage_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "  Private_Beta ")
        assert rollout_gate.current_stage() == "private_beta"


class TestGateDecisions:
    def test_public_allows_without_invite_even_at_high_count(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "public")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "secret")
        d = rollout_gate.check_registration(None, 10_000)
        assert d.allowed

    def test_owner_cap_blocks_third_account(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "owner")
        assert rollout_gate.check_registration(None, 1).allowed
        d = rollout_gate.check_registration(None, 2)
        assert not d.allowed
        assert "capacity" in d.reason

    def test_private_beta_cap_is_10(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        assert rollout_gate.check_registration(None, 9).allowed
        assert not rollout_gate.check_registration(None, 10).allowed

    def test_extended_beta_cap_is_25(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "extended_beta")
        assert rollout_gate.check_registration(None, 24).allowed
        assert not rollout_gate.check_registration(None, 25).allowed

    def test_invite_code_required_when_configured(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "beta-wave-1")
        assert not rollout_gate.check_registration(None, 0).allowed
        assert not rollout_gate.check_registration("wrong", 0).allowed
        assert rollout_gate.check_registration("beta-wave-1", 0).allowed

    def test_invite_code_does_not_bypass_cap(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "beta-wave-1")
        assert not rollout_gate.check_registration("beta-wave-1", 10).allowed

    def test_unknown_user_count_denies_in_capped_stage(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "owner")
        d = rollout_gate.check_registration(None, None)
        assert not d.allowed
        assert "cannot verify" in d.reason

    def test_decision_names_the_stage(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "extended_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "x")
        d = rollout_gate.check_registration(None, 0)
        assert d.stage == "extended_beta"
        assert "extended_beta" in d.reason


class TestCountUsers:
    def test_fallback_store_counts(self):
        from src.auth.db_user_manager import DBUserManager

        mgr = DBUserManager(None)
        assert mgr.count_users() == 0
        mgr.create_user("rollout_counter", "Str0ng!Passw0rd")
        assert mgr.count_users() == 1

    def test_db_configured_but_unavailable_returns_none(self):
        from src.auth.db_user_manager import DBUserManager

        def broken_factory():
            raise RuntimeError("db down")

        mgr = DBUserManager(broken_factory)
        assert mgr.count_users() is None


class TestRolloutStatusEndpoint:
    """The admin-only /auth/rollout ops endpoint."""

    def _client(self):
        import os
        from unittest.mock import MagicMock, patch

        import pytest

        if not os.getenv("SECRET_KEY"):
            pytest.skip("SECRET_KEY env var not set")
        try:
            from fastapi.testclient import TestClient

            with patch("redis.from_url", return_value=MagicMock(ping=lambda: True)):
                from api import app
            return TestClient(app, raise_server_exceptions=False)
        except Exception as e:  # missing production deps in a lean env
            pytest.skip(f"api.py unavailable: {e}")

    def test_requires_authentication(self):
        r = self._client().get("/auth/rollout")
        assert r.status_code in (401, 403)

    def test_non_admin_is_refused(self):
        from auth import create_token

        client = self._client()
        token = create_token(user_id="u1", username="tester", role="user", tier=0)
        r = client.get("/auth/rollout", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_admin_sees_stage_and_capacity(self, monkeypatch):
        from auth import create_token

        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        client = self._client()
        token = create_token(user_id="u0", username="owner", role="admin", tier=3)
        r = client.get("/auth/rollout", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["stage"] == "private_beta"
        assert body["cap"] == 10
        assert "remaining" in body
