"""SSRF and URL validation tests — Dimensional / shared_core.url_validation."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from Dimensional.url_validation import SSRFError, validate_url, validate_webhook_url


class TestValidateUrlBasics:
    def test_rejects_empty(self) -> None:
        with pytest.raises(SSRFError, match="empty"):
            validate_webhook_url("")

    def test_rejects_http_in_production_defaults(self) -> None:
        with pytest.raises(SSRFError, match="scheme"):
            validate_webhook_url("http://example.com/hook")

    def test_allows_https_public_with_mock_dns(self) -> None:
        def fake_getaddrinfo(host, port, *args, **kwargs):
            if host == "hooks.example.com":
                return [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        ("93.184.216.34", port),
                    )
                ]
            raise socket.gaierror("unknown")

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
            out = validate_webhook_url("https://hooks.example.com/path")
        assert out == "https://hooks.example.com/path"

    def test_rejects_localhost_hostname(self) -> None:
        with pytest.raises(SSRFError, match="blocked"):
            validate_webhook_url("https://localhost/cb")

    def test_rejects_metadata_hostname(self) -> None:
        with pytest.raises(SSRFError, match="blocked"):
            validate_webhook_url("https://metadata.google.internal/")

    def test_rejects_private_ip_resolution(self) -> None:
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", port))
            ]

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
            with pytest.raises(SSRFError, match="private"):
                validate_webhook_url("https://evil.example.com/")

    def test_rejects_unresolvable_host(self) -> None:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("fail")):
            with pytest.raises(SSRFError, match="resolve"):
                validate_webhook_url("https://does-not-resolve.invalid/")

    def test_rejects_overlong_url(self) -> None:
        long_path = "a" * 3000
        with pytest.raises(SSRFError, match="maximum length"):
            validate_webhook_url(f"https://example.com/{long_path}")

    def test_dev_http_allowed_with_override(self) -> None:
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", port),
                )
            ]

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
            out = validate_url(
                "http://hooks.example.com/x",
                allowed_schemes={"http", "https"},
            )
        assert out.startswith("http://")


def _load_dimensional_url_validation():
    """Load Dimensional/url_validation.py without importing Dimensional package (avoids fastapi)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "Dimensional" / "url_validation.py"
    spec = importlib.util.spec_from_file_location("dimensional_url_validation", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestNotificationsIntegration:
    def test_dimensional_validate_webhook_matches_shared(self) -> None:
        dim = _load_dimensional_url_validation()
        with pytest.raises(dim.SSRFError):
            dim.validate_webhook_url("https://127.0.0.1/x")
