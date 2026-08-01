"""Tests for the shared CORS allow-list resolver used by Nexus and HIVE.

Covers the two failure modes that motivated `Dimensional/cors.py`: a *set but
blank* variable silently disabling all cross-origin access, and a configured
wildcard re-opening the hole this module exists to close.
"""

from __future__ import annotations

import pytest

from Dimensional.cors import DEFAULT_ORIGIN, resolve_cors_origins


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start every test from no CORS configuration at all.

    These variables are frequently set process-wide by other suites and by the
    developer's own shell; without this the tests would pass or fail depending
    on run order.
    """
    for var in ("CORS_ORIGINS", "ALLOWED_ORIGINS", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)


class TestResolutionOrder:
    def test_no_configuration_yields_the_local_default(self):
        assert resolve_cors_origins("Test") == [DEFAULT_ORIGIN]

    def test_cors_origins_wins_when_set(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://b.example")
        assert resolve_cors_origins("Test") == ["https://a.example"]

    def test_allowed_origins_used_when_cors_origins_absent(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://b.example")
        assert resolve_cors_origins("Test") == ["https://b.example"]

    def test_entries_are_split_and_trimmed(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", " https://a.example , https://b.example ")
        assert resolve_cors_origins("Test") == ["https://a.example", "https://b.example"]


class TestBlankValuesFallThrough:
    """A set-but-empty variable must not win with an empty allow-list.

    ``os.getenv("CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", default))`` reads as
    though it handles this, but an exported empty string is *present*, so getenv
    returns it and the fallback never runs. The result is an empty list handed to
    CORSMiddleware, which disables cross-origin access entirely — with nothing
    raised and no log line, surfacing only as browser requests failing later.
    """

    def test_empty_cors_origins_falls_through_to_allowed_origins(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://b.example")
        assert resolve_cors_origins("Test") == ["https://b.example"]

    def test_whitespace_cors_origins_falls_through(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "   ")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://b.example")
        assert resolve_cors_origins("Test") == ["https://b.example"]

    def test_separators_only_falls_through(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", " , , ")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://b.example")
        assert resolve_cors_origins("Test") == ["https://b.example"]

    def test_both_blank_yields_the_default_never_an_empty_list(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "")
        monkeypatch.setenv("ALLOWED_ORIGINS", "  ")
        assert resolve_cors_origins("Test") == [DEFAULT_ORIGIN]

    def test_resolution_never_returns_an_empty_list(self, monkeypatch):
        """The property that matters, stated directly.

        An empty allow-list is the one output that silently breaks every browser
        client, so no combination of inputs may produce it.
        """
        for cors, allowed in (("", ""), ("   ", ","), (",,", "   "), ("", ",")):
            monkeypatch.setenv("CORS_ORIGINS", cors)
            monkeypatch.setenv("ALLOWED_ORIGINS", allowed)
            assert resolve_cors_origins("Test"), f"empty for {cors!r}/{allowed!r}"


class TestWildcardWithCredentials:
    """With credentials enabled a wildcard has no valid configuration.

    Starlette does not refuse it — it echoes the request's own Origin header
    back, so the browser restriction never engages and any site can make
    credentialed calls. Rejected in every environment, not just production.
    """

    @pytest.mark.parametrize("environment", ["production", "development", "test", ""])
    def test_rejected_in_every_environment(self, monkeypatch, environment):
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="allow_credentials=True"):
            resolve_cors_origins("Nexus", allow_credentials=True)

    def test_rejected_via_allowed_origins_too(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
            resolve_cors_origins("Nexus", allow_credentials=True)

    def test_rejected_when_mixed_with_real_origins(self, monkeypatch):
        """A wildcard alongside specific origins is still a wildcard.

        Starlette treats the list as allow-all the moment "*" appears, so the
        specific entries provide no narrowing whatsoever.
        """
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example,*")
        with pytest.raises(RuntimeError):
            resolve_cors_origins("Nexus", allow_credentials=True)


class TestWildcardWithoutCredentials:
    """Without credentials a wildcard is permissive rather than broken, so it
    follows the repo's existing rule in `startup_validator._check_cors_origins`:
    an error in production, tolerated elsewhere."""

    def test_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="production"):
            resolve_cors_origins("HIVE")

    def test_production_detection_ignores_case_and_padding(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "  Production ")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError):
            resolve_cors_origins("HIVE")

    def test_allowed_with_a_warning_outside_production(self, monkeypatch, caplog):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with caplog.at_level("WARNING"):
            assert resolve_cors_origins("HIVE") == ["*"]
        assert "ENVIRONMENT=production" in caplog.text


class TestAppsUseTheResolver:
    """The apps must actually route through the resolver — a fix that only
    exists in the helper protects nothing."""

    def test_nexus_app_refuses_wildcard(self, monkeypatch):
        from Dimensional.nexus.nexus_core import create_nexus_app

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="allow_credentials=True"):
            create_nexus_app()

    def test_hive_app_refuses_wildcard_in_production(self, monkeypatch):
        from Dimensional.hive.hive_core import create_hive_app

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="production"):
            create_hive_app()

    def test_apps_build_normally_with_explicit_origins(self, monkeypatch):
        from Dimensional.hive.hive_core import create_hive_app
        from Dimensional.nexus.nexus_core import create_nexus_app

        monkeypatch.setenv("CORS_ORIGINS", "https://trancendos.com")
        assert create_nexus_app().title == "Tranc3 Nexus"
        assert create_hive_app().title == "Tranc3 HIVE"
