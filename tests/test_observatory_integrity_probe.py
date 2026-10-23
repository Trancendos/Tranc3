"""Self-contained Observatory probe behavior and safety tests."""

import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "observatory_integrity_probe.py"


def probe():
    spec = importlib.util.spec_from_file_location("observatory_integrity_probe", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_healthy_only_when_health_and_full_verify_are_both_clean():
    mod = probe()
    result = mod.classify(
        {"status": "healthy", "chain_valid": True, "total_events": 3}, {"valid": True, "checked": 3}
    )
    assert result["state"] == "healthy"
    assert result["code"] == 0


@pytest.mark.parametrize(
    "health,verify",
    [
        ({"status": "degraded", "chain_valid": False}, {"valid": True, "checked": 0}),
        ({"status": "healthy", "chain_valid": True}, {"valid": False, "checked": 2}),
        ({"status": "healthy", "chain_valid": True}, {"checked": 2}),
    ],
)
def test_corrupt_or_incomplete_evidence_is_critical(health, verify):
    result = probe().classify(health, verify)
    assert result["state"] == "critical"
    assert result["code"] == 1


def test_no_credentials_to_plain_http_nonloopback():
    mod = probe()
    assert mod.validate_base_url("http://127.0.0.1:8025") == "http://127.0.0.1:8025"
    assert (
        mod.validate_base_url("https://observatory.example.org/")
        == "https://observatory.example.org"
    )
    with pytest.raises(ValueError):
        mod.validate_base_url("http://observatory.example.org")
    with pytest.raises(ValueError):
        mod.validate_base_url("file:///etc/passwd")


def test_probe_returns_unavailable_for_connection_failure(monkeypatch):
    mod = probe()

    def fail(*args, **kwargs):
        raise OSError("down")

    monkeypatch.setattr(mod, "fetch_json", fail)
    result = mod.check("http://127.0.0.1:8025", timeout=1)
    assert result["state"] == "unavailable"
    assert result["code"] == 2
    assert "down" not in str(result)


def test_probe_refuses_redirect_to_other_origin():
    from urllib.error import HTTPError
    from urllib.request import Request

    mod = probe()
    handler = mod._RefuseRedirect()
    with pytest.raises(HTTPError):
        handler.redirect_request(
            Request("https://observatory.example.org/verify"),
            None,
            302,
            "Moved",
            {},
            "http://attacker.example.com",
        )


def test_probe_detects_dropped_events_between_health_and_verify():
    mod = probe()
    result = mod.classify(
        {"status": "healthy", "chain_valid": True, "total_events": 5}, {"valid": True, "checked": 3}
    )
    assert result["state"] == "critical"
