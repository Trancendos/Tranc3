"""The Void must never invent identities when upstream verification is unavailable."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def void_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_KEY_SEED", "synthetic-master-key-for-auth-tests")
    monkeypatch.setenv("INTERNAL_SECRET", "synthetic-internal-secret-for-auth-tests")
    monkeypatch.setenv("VOID_DATA_DIR", str(tmp_path / "void"))
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("INFINITY_ONE_URL", raising=False)
    return import_worker(
        "void_auth_fail_closed_test",
        ROOT / "workers" / "infinity-void" / "worker.py",
    )


def test_missing_header_is_denied_even_in_test_mode(void_worker):
    assert asyncio.run(void_worker.get_auth_user_id(None)) is None


def test_unconfigured_verifier_denies_arbitrary_bearer_tokens(void_worker):
    assert asyncio.run(void_worker.get_auth_user_id("Bearer invented-credential")) is None


def test_blank_bearer_token_is_denied(void_worker):
    assert asyncio.run(void_worker.get_auth_user_id("Bearer   ")) is None


def test_without_verifier_secret_endpoints_return_401(void_worker):
    with TestClient(void_worker.app) as client:
        assert client.get("/vault/status").status_code == 401
        assert (
            client.get("/secrets", headers={"Authorization": "Bearer invented"}).status_code == 401
        )


@pytest.mark.parametrize(
    ("identity_response", "expected_user_id"),
    [
        ({"user_id": "verified-user"}, "verified-user"),
        ({"user_id": ""}, None),
        ({"user_id": 123}, None),
        ({}, None),
    ],
)
def test_only_nonblank_string_identity_from_verifier_is_accepted(
    void_worker, monkeypatch, identity_response, expected_user_id
):
    monkeypatch.setattr(void_worker, "INFINITY_ONE_URL", "http://synthetic-auth.invalid")

    class FakeResponse:
        status_code = 200

        def json(self):
            return identity_response

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json, headers):
            assert url == "http://synthetic-auth.invalid/auth/verify"
            assert json == {"token": "synthetic-token"}
            assert headers["X-Internal-Secret"] == "synthetic-internal-secret-for-auth-tests"
            return FakeResponse()

    monkeypatch.setattr(void_worker.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    assert asyncio.run(void_worker.get_auth_user_id("Bearer synthetic-token")) == expected_user_id


@pytest.mark.parametrize("failure", ["server-error", "invalid-json", "connection-error"])
def test_verifier_failures_never_grant_an_identity(void_worker, monkeypatch, failure):
    monkeypatch.setattr(void_worker, "INFINITY_ONE_URL", "http://synthetic-auth.invalid")

    class FakeResponse:
        status_code = 503 if failure == "server-error" else 200

        def json(self):
            if failure == "invalid-json":
                raise ValueError("Malformed response")
            return {"user_id": "must-not-be-granted"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json, headers):
            if failure == "connection-error":
                raise void_worker.httpx.ConnectError(
                    "Synthetic connection failure",
                    request=void_worker.httpx.Request("POST", url),
                )
            return FakeResponse()

    monkeypatch.setattr(void_worker.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    assert asyncio.run(void_worker.get_auth_user_id("Bearer synthetic-token")) is None
