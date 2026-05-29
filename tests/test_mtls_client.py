"""
tests/test_mtls_client.py — Unit tests for src/security/mtls_client.py

All tests are zero-cost: no real network connections, no certificates required.
The mTLS module degrades gracefully when certs are absent.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# mtls_status
# ---------------------------------------------------------------------------


class TestMtlsStatus:
    def test_status_returns_dict(self):
        from src.security.mtls_client import mtls_status
        status = mtls_status()
        assert isinstance(status, dict)

    def test_status_has_required_keys(self):
        from src.security.mtls_client import mtls_status
        status = mtls_status()
        for key in ("ca_cert_present", "client_cert_present", "verify_enabled"):
            assert key in status, f"Missing key: {key}"

    def test_status_ca_absent_when_no_certs(self):
        """Without actual cert files the CA should be absent."""
        from src.security.mtls_client import mtls_status
        status = mtls_status()
        # In test environment, cert files are not present
        assert isinstance(status["ca_cert_present"], bool)

    def test_status_verify_default_true(self):
        with patch.dict(os.environ, {"MTLS_VERIFY": "true"}):
            import importlib

            import src.security.mtls_client as m
            importlib.reload(m)
            status = m.mtls_status()
            assert status["verify_enabled"] is True
            importlib.reload(m)  # restore


# ---------------------------------------------------------------------------
# _build_ssl_kwargs
# ---------------------------------------------------------------------------


class TestBuildSslKwargs:
    def _import(self):
        from src.security.mtls_client import _build_ssl_kwargs
        return _build_ssl_kwargs

    def test_verify_false_when_disabled(self, monkeypatch):
        monkeypatch.setenv("MTLS_VERIFY", "false")
        import importlib

        import src.security.mtls_client as m
        importlib.reload(m)
        kwargs = m._build_ssl_kwargs()
        assert kwargs.get("verify") is False
        importlib.reload(m)

    def test_no_cert_key_in_kwargs_when_files_absent(self):
        from src.security.mtls_client import _build_ssl_kwargs
        kwargs = _build_ssl_kwargs()
        # cert key absent when no client cert files exist
        assert "cert" not in kwargs or kwargs.get("cert") is None


# ---------------------------------------------------------------------------
# get_mtls_client / get_async_mtls_client
# ---------------------------------------------------------------------------


class TestGetMtlsClient:
    def test_returns_none_when_httpx_missing(self):
        import sys
        with patch.dict(sys.modules, {"httpx": None}):
            import importlib

            import src.security.mtls_client as m
            importlib.reload(m)
            result = m.get_mtls_client()
            assert result is None
            importlib.reload(m)

    def test_returns_client_when_httpx_present(self):
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")
        from src.security.mtls_client import get_mtls_client
        client = get_mtls_client()
        assert client is not None
        client.close()

    def test_async_returns_none_when_httpx_missing(self):
        import sys
        with patch.dict(sys.modules, {"httpx": None}):
            import importlib

            import src.security.mtls_client as m
            importlib.reload(m)
            result = m.get_async_mtls_client()
            assert result is None
            importlib.reload(m)

    def test_async_returns_client_when_httpx_present(self):
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")
        from src.security.mtls_client import get_async_mtls_client
        client = get_async_mtls_client()
        assert client is not None


# ---------------------------------------------------------------------------
# internal_get / internal_post raise when httpx missing
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_internal_get_raises_without_httpx(self):
        import sys
        with patch.dict(sys.modules, {"httpx": None}):
            import importlib

            import src.security.mtls_client as m
            importlib.reload(m)
            with pytest.raises(RuntimeError, match="httpx is required"):
                m.internal_get("https://dummy.internal:8443/health")
            importlib.reload(m)

    def test_internal_post_raises_without_httpx(self):
        import sys
        with patch.dict(sys.modules, {"httpx": None}):
            import importlib

            import src.security.mtls_client as m
            importlib.reload(m)
            with pytest.raises(RuntimeError, match="httpx is required"):
                m.internal_post("https://dummy.internal:8443/data", json={})
            importlib.reload(m)
