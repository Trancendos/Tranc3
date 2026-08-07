"""
Tests for src/shared/client_ip.py — the single X-Forwarded-For-aware resolver
shared by src/mcp/server.py's injection-strike tracking and
src/security/middleware.py's GovernanceMiddleware.is_blocked() gate.

Regression context: before this module existed, the two call sites resolved
"client IP" differently (one preferred X-Forwarded-For, the other used the raw
TCP peer), so a Cryptex block set by one check never matched what the other
looked up under a Traefik-proxied deployment (cubic-dev-ai P1, confidence 10,
on Tranc3#493). Both now import this single function.
"""

from __future__ import annotations

from src.shared.client_ip import resolve_client_ip


def test_prefers_x_forwarded_for():
    assert resolve_client_ip({"X-Forwarded-For": "203.0.113.5"}, "10.0.0.2") == "203.0.113.5"


def test_takes_first_entry_of_forwarded_chain():
    headers = {"X-Forwarded-For": "203.0.113.5, 10.0.0.1, 10.0.0.2"}
    assert resolve_client_ip(headers, "10.0.0.2") == "203.0.113.5"


def test_strips_whitespace_around_first_entry():
    headers = {"X-Forwarded-For": "  203.0.113.5  ,10.0.0.1"}
    assert resolve_client_ip(headers, "10.0.0.2") == "203.0.113.5"


def test_falls_back_to_direct_peer_when_header_absent():
    assert resolve_client_ip({}, "10.0.0.2") == "10.0.0.2"


def test_falls_back_to_direct_peer_when_header_empty():
    assert resolve_client_ip({"X-Forwarded-For": ""}, "10.0.0.2") == "10.0.0.2"


def test_returns_none_when_nothing_available():
    assert resolve_client_ip({}, None) is None


def test_lowercase_header_key_also_matched():
    assert resolve_client_ip({"x-forwarded-for": "203.0.113.9"}, "10.0.0.2") == "203.0.113.9"
