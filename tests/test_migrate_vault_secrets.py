"""Offline synthetic secrets only; no live vault or credentials used."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_vault_secrets.py"
spec = importlib.util.spec_from_file_location("safe_vault_migrate", SCRIPT)
assert spec and spec.loader
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)


@pytest.fixture
def old_db(tmp_path):
    path = tmp_path / "legacy.db"
    master = "synthetic-master-test-only"
    salt, nonce = os.urandom(32), os.urandom(12)
    dk = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000).derive(
        master.encode()
    )
    envelope = (salt + nonce + AESGCM(dk).encrypt(nonce, b"synthetic-value-only", None)).hex()
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE secrets (id TEXT, key TEXT, encrypted_value TEXT, is_active INT)")
    conn.execute("INSERT INTO secrets VALUES (?,?,?,1)", ("id-1", "synthetic-name", envelope))
    conn.commit()
    conn.close()
    return path, master


def test_default_offline_dry_run_does_not_contact_destination(old_db):
    path, master = old_db
    assert mig.migrate(str(path), master_key=master) == {"verified": 1, "migrated": 0}


def test_execute_requires_authenticated_bearer(old_db):
    path, master = old_db
    with pytest.raises(mig.MigrationError, match="bearer token"):
        mig.migrate(str(path), master_key=master, execute=True)


def test_rejects_remote_plaintext_http(old_db):
    path, master = old_db
    with pytest.raises(mig.MigrationError, match="HTTPS"):
        mig.migrate(
            str(path),
            master_key=master,
            execute=True,
            bearer_token="synthetic",
            void_url="http://vault.example.com",
        )


def test_successful_migration_uses_current_api_and_verifies_readback(old_db):
    path, master = old_db
    seen = {"stored": None, "methods": []}

    def respond(request):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        seen["methods"].append((request.method, request.url.path))
        if request.url.path == "/secrets" and request.method == "GET":
            return httpx.Response(200, json={"count": 0, "secrets": []})
        if request.url.path == "/secrets" and request.method == "POST":
            import json

            payload = json.loads(request.content)
            assert payload["name"] == "synthetic-name"
            seen["stored"] = payload["value"]
            return httpx.Response(200, json={"secret_id": "syn-1"})
        if request.url.path == "/secrets/retrieve":
            return httpx.Response(200, json={"plaintext": seen["stored"]})
        return httpx.Response(404)

    result = mig.migrate(
        str(path),
        master_key=master,
        execute=True,
        bearer_token="synthetic-token",
        transport=httpx.MockTransport(respond),
    )
    assert result == {"verified": 1, "migrated": 1}
    assert seen["methods"] == [
        ("GET", "/secrets"),
        ("POST", "/secrets"),
        ("POST", "/secrets/retrieve"),
    ]


def test_nonempty_destination_blocks_any_write(old_db):
    path, master = old_db
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json={"count": 1, "secrets": [{"name": "already"}]})

    with pytest.raises(mig.MigrationError, match="not empty"):
        mig.migrate(
            str(path),
            master_key=master,
            execute=True,
            bearer_token="synthetic",
            transport=httpx.MockTransport(respond),
        )
    assert calls == ["GET"]


def test_mismatch_aborts_without_deleting_source(old_db):
    path, master = old_db

    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, json={"count": 0, "secrets": []})
        if request.url.path == "/secrets":
            return httpx.Response(200, json={"secret_id": "syn-1"})
        return httpx.Response(200, json={"plaintext": "wrong-value"})

    with pytest.raises(mig.MigrationError, match="readback mismatch"):
        mig.migrate(str(path), master_key=master, execute=True, bearer_token="synthetic", transport=httpx.MockTransport(respond))
    assert path.exists()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM secrets WHERE is_active=1").fetchone()[0] == 1
    conn.close()


def test_wrong_master_key_is_detected_before_destination_write(old_db):
    path, _ = old_db
    with pytest.raises(mig.MigrationError, match="Source authentication failed"):
        mig.migrate(str(path), master_key="wrong")
