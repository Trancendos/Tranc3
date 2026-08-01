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
        except (ImportError, ModuleNotFoundError) as e:
            # Only a genuinely absent dependency is a skip. Catching everything
            # would turn a broken /auth/rollout route into a silent pass.
            pytest.skip(f"missing production dependency: {e}")

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


class TestSmokeCheckStageParsing:
    """cloud_smoke_check parses the stage the API actually emits.

    The script lives outside the app, so nothing else keeps its expectation of
    the refusal shape aligned with what /auth/register returns. These tests pin
    them together.
    """

    def _parser(self):
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "cloud_smoke_check.py"
        spec = importlib.util.spec_from_file_location("cloud_smoke_check", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._reported_stage

    def test_parses_stage_from_a_real_gate_refusal(self, monkeypatch):
        """Build the body from the gate itself, not a hand-written fixture."""
        import json

        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        decision = rollout_gate.check_registration(None, 10)
        assert not decision.allowed
        body = json.dumps({"detail": {"stage": decision.stage, "reason": decision.reason}})
        assert self._parser()(body) == "private_beta"

    def test_returns_none_on_unparseable_or_shapeless_bodies(self):
        parse = self._parser()
        assert parse("not json at all") is None
        assert parse('{"detail": "a plain string detail"}') is None
        assert parse("{}") is None

    def test_does_not_match_a_stage_merely_mentioned_in_prose(self):
        """The regression the substring check would have had."""
        import json

        body = json.dumps({"detail": "registration reopens at the private_beta stage"})
        assert self._parser()(body) is None


class TestNeedsUserCount:
    def test_public_stage_does_not_need_a_count(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "public")
        assert rollout_gate.needs_user_count() is False

    def test_capped_stages_need_a_count(self, monkeypatch):
        for stage in ("owner", "private_beta", "extended_beta"):
            monkeypatch.setenv("ROLLOUT_STAGE", stage)
            assert rollout_gate.needs_user_count() is True

    def test_production_default_needs_a_count(self, monkeypatch):
        """Fail-closed resolves to owner, which is capped."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert rollout_gate.needs_user_count() is True


class TestInviteCodeRobustness:
    def test_non_ascii_invite_code_denies_rather_than_raising(self, monkeypatch):
        """compare_digest() on str raises TypeError for non-ASCII — a tester
        pasting a smart quote must get a clean refusal, not a 500."""
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "beta-wave-1")
        decision = rollout_gate.check_registration("béta-wave-1—", 0)
        assert not decision.allowed

    def test_non_ascii_configured_code_still_matches_itself(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "café-wave-één")
        assert rollout_gate.check_registration("café-wave-één", 0).allowed


class TestInviteThrottle:
    @pytest.fixture(autouse=True)
    def _reset_throttle(self):
        rollout_gate._failed_invites.clear()
        yield
        rollout_gate._failed_invites.clear()

    def test_repeated_wrong_codes_eventually_throttle(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "correct-horse-battery")
        for _ in range(rollout_gate._MAX_FAILED_INVITES_PER_WINDOW):
            assert not rollout_gate.check_registration("wrong", 0).allowed
        throttled = rollout_gate.check_registration("wrong", 0)
        assert not throttled.allowed
        assert "too many" in throttled.reason

    def test_correct_code_is_unaffected_by_a_clean_window(self, monkeypatch):
        monkeypatch.setenv("ROLLOUT_STAGE", "private_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "correct-horse-battery")
        for _ in range(rollout_gate._MAX_FAILED_INVITES_PER_WINDOW - 1):
            rollout_gate.check_registration("wrong", 0)
        assert rollout_gate.check_registration("correct-horse-battery", 0).allowed

    def test_successful_registrations_never_consume_the_budget(self, monkeypatch):
        """A full tester wave must not throttle itself."""
        monkeypatch.setenv("ROLLOUT_STAGE", "extended_beta")
        monkeypatch.setenv("ROLLOUT_INVITE_CODE", "correct-horse-battery")
        for n in range(25):
            assert rollout_gate.check_registration("correct-horse-battery", n).allowed
        assert not rollout_gate._invite_attempts_exhausted()


class TestCountUsersDatabasePath:
    """The DB branch of count_users — the one that actually runs in production.

    The fallback branch is what tests hit by default, so without these the
    production path of the function every cap decision depends on is unexercised.
    """

    def _manager_with_session(self, session):
        from src.auth.db_user_manager import DBUserManager

        return DBUserManager(lambda: session)

    def test_returns_the_database_count(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        session.query.return_value.count.return_value = 7
        assert self._manager_with_session(session).count_users() == 7
        session.close.assert_called_once()

    def test_query_failure_returns_none_not_a_fallback_count(self):
        """A DB error must deny in capped stages, never silently under-count."""
        from unittest.mock import MagicMock

        session = MagicMock()
        session.query.side_effect = RuntimeError("connection reset")
        assert self._manager_with_session(session).count_users() is None
        session.close.assert_called_once()

    def test_session_is_closed_even_on_success(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        session.query.return_value.count.return_value = 0
        self._manager_with_session(session).count_users()
        session.close.assert_called_once()

    def test_a_none_returning_factory_is_treated_as_unknown(self):
        from src.auth.db_user_manager import DBUserManager

        mgr = DBUserManager(lambda: None)
        assert mgr.count_users() is None


class TestSpaFallbackDoesNotShadowApiRoutes:
    """The frontend catch-all must be matched last.

    `GET /{full_path:path}` is declared early in api.py and FastAPI matches in
    registration order, so with web/dist/ present it swallowed every route
    declared below it — /health included, returning index.html instead of JSON.
    api.py reorders it to the end; this asserts the ordering directly, since the
    behaviour only manifests when a frontend build exists at import time.
    """

    def test_no_concrete_route_is_registered_after_the_catch_all(self):
        import os
        from unittest.mock import MagicMock, patch

        import pytest
        from fastapi.routing import APIRoute

        if not os.getenv("SECRET_KEY"):
            pytest.skip("SECRET_KEY env var not set")
        try:
            with patch("redis.from_url", return_value=MagicMock(ping=lambda: True)):
                from api import app
        except (ImportError, ModuleNotFoundError) as e:
            pytest.skip(f"missing production dependency: {e}")

        paths = [r.path for r in app.router.routes if isinstance(r, APIRoute)]
        if "/{full_path:path}" not in paths:
            pytest.skip("no frontend build present, so the catch-all is not registered")

        shadowed = paths[paths.index("/{full_path:path}") + 1 :]
        assert not shadowed, (
            "these API routes are registered after the SPA catch-all and would "
            f"return index.html instead of JSON: {shadowed}"
        )
