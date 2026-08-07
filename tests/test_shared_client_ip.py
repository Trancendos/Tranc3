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


class TestUntrustedDirectPeerIgnoresForwardedHeader:
    """
    CodeRabbit (Major, on Tranc3#493): a caller reaching the service directly — bypassing
    Traefik — could set X-Forwarded-For to an arbitrary victim IP and get that victim
    strike-tracked/blocked instead of themselves. X-Forwarded-For is only trusted when the
    direct peer is itself private/loopback (i.e. plausibly Traefik's own container hop on
    the Docker network); a non-private direct peer's self-reported header is ignored.
    """

    def test_public_direct_peer_forwarded_header_ignored(self):
        # Attacker connects directly (genuinely public source IP) and tries to frame a
        # victim IP. Note: RFC 5737 documentation ranges (203.0.113.0/24, 198.51.100.0/24,
        # 192.0.2.0/24) are treated as "private" by Python's ipaddress module, same as
        # RFC 1918 — a real public address is needed here to exercise the untrusted path.
        headers = {"X-Forwarded-For": "203.0.113.50"}  # attacker-chosen "victim" IP
        assert resolve_client_ip(headers, "1.2.3.4") == "1.2.3.4"

    def test_private_direct_peer_forwarded_header_still_trusted(self):
        # Traefik's own container IP (private) is the expected, trusted proxy hop.
        headers = {"X-Forwarded-For": "198.51.100.7"}
        assert resolve_client_ip(headers, "172.18.0.3") == "198.51.100.7"

    def test_loopback_direct_peer_forwarded_header_still_trusted(self):
        headers = {"X-Forwarded-For": "198.51.100.7"}
        assert resolve_client_ip(headers, "127.0.0.1") == "198.51.100.7"

    def test_public_direct_peer_no_header_returns_peer(self):
        assert resolve_client_ip({}, "1.2.3.4") == "1.2.3.4"

    def test_malformed_direct_peer_treated_as_untrusted(self):
        # Defensive: an unparsable peer value must not be treated as trusted-private.
        headers = {"X-Forwarded-For": "198.51.100.7"}
        assert resolve_client_ip(headers, "not-an-ip") == "not-an-ip"
