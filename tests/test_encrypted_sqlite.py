"""
Tests for src.database.encrypted_sqlite — AES-GCM field-level encryption.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.pop("TRANC3_DB_ENCRYPTION_DISABLED", None)
os.environ["SECRET_KEY"] = "test-secret-key-for-encrypted-sqlite-unit-tests-32chars"

from src.database.encrypted_sqlite import (  # noqa: E402
    EncryptedKVStore,
    _decrypt_bytes,
    _encrypt_bytes,
    _derive_key,
    connect,
    decrypt_field,
    decrypt_row,
    encrypt_field,
    invalidate_key_cache,
)


@pytest.fixture()
def db_path(tmp_path):
    p = str(tmp_path / "test.db")
    invalidate_key_cache(p)
    return p


# ---------------------------------------------------------------------------
# Low-level AES-GCM
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(db_path):
    key = _derive_key(db_path)
    for pt in [b"hello", b"", b"\x00\xff" * 100]:
        assert _decrypt_bytes(key, _encrypt_bytes(key, pt)) == pt


def test_different_ivs_each_call(db_path):
    key = _derive_key(db_path)
    a = _encrypt_bytes(key, b"same")
    b = _encrypt_bytes(key, b"same")
    assert a != b


def test_tamper_detection(db_path):
    key = _derive_key(db_path)
    blob = _encrypt_bytes(key, b"sensitive")
    tampered = blob[:-4] + bytes([blob[-4] ^ 0xFF]) + blob[-3:]
    from cryptography.exceptions import InvalidTag

    with pytest.raises((InvalidTag, Exception)):
        _decrypt_bytes(key, tampered)


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def test_encrypt_field_string(db_path):
    enc = encrypt_field(db_path, "hello")
    assert enc != "hello"
    assert enc.startswith("ENC1:")
    assert decrypt_field(db_path, enc) == "hello"


def test_encrypt_field_bytes(db_path):
    data = os.urandom(32)
    enc = encrypt_field(db_path, data)
    assert enc != data
    assert decrypt_field(db_path, enc) == data


def test_encrypt_field_passthrough_types(db_path):
    for v in (42, 3.14, None):
        assert encrypt_field(db_path, v) == v
        assert decrypt_field(db_path, v) == v


def test_decrypt_field_plain_value_passthrough(db_path):
    # A value not starting with ENC1 is returned as-is
    assert decrypt_field(db_path, "plain-text") == "plain-text"


def test_decrypt_row_all_columns(db_path):
    row = (
        encrypt_field(db_path, "alice"),
        encrypt_field(db_path, "secret@example.com"),
        42,
    )
    dec = decrypt_row(db_path, row)
    assert dec == ("alice", "secret@example.com", 42)


def test_decrypt_row_selected_columns(db_path):
    raw_id = "user-123"
    enc_email = encrypt_field(db_path, "secret@example.com")
    row = (raw_id, enc_email, 99)
    dec = decrypt_row(db_path, row, columns=[1])
    assert dec == ("user-123", "secret@example.com", 99)


def test_decrypt_row_none(db_path):
    assert decrypt_row(db_path, None) is None


def test_key_stable_across_calls(db_path):
    invalidate_key_cache(db_path)
    k1 = _derive_key(db_path)
    k2 = _derive_key(db_path)
    assert k1 == k2


def test_key_differs_across_databases(tmp_path):
    db1 = str(tmp_path / "a.db")
    db2 = str(tmp_path / "b.db")
    invalidate_key_cache(db1)
    invalidate_key_cache(db2)
    assert _derive_key(db1) != _derive_key(db2)


def test_persist_and_redecrypt(db_path):
    """Encrypt a value, store in SQLite, re-open db, decrypt it."""
    enc = encrypt_field(db_path, "super-secret")

    con = connect(db_path)
    con.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("INSERT INTO t VALUES (?,?)", ("k1", enc))
    con.commit()
    con.close()

    con2 = connect(db_path)
    row = con2.execute("SELECT v FROM t WHERE k=?", ("k1",)).fetchone()
    con2.close()
    assert decrypt_field(db_path, row[0]) == "super-secret"


def test_raw_sqlite_sees_encrypted_bytes(db_path):
    enc = encrypt_field(db_path, "sensitive-data")

    con = connect(db_path)
    con.execute("CREATE TABLE t (v TEXT)")
    con.execute("INSERT INTO t VALUES (?)", (enc,))
    con.commit()
    con.close()

    raw = sqlite3.connect(db_path)
    row = raw.execute("SELECT v FROM t").fetchone()
    raw.close()
    assert row[0].startswith("ENC1:")
    assert "sensitive-data" not in row[0]


def test_encryption_disabled(db_path, monkeypatch):
    monkeypatch.setenv("TRANC3_DB_ENCRYPTION_DISABLED", "1")
    assert encrypt_field(db_path, "plain") == "plain"
    assert decrypt_field(db_path, "plain") == "plain"


def test_key_from_master_key_env(tmp_path, monkeypatch):
    db = str(tmp_path / "master.db")
    master = os.urandom(32).hex()
    monkeypatch.setenv("TRANC3_DB_MASTER_KEY", master)
    monkeypatch.delenv("TRANC3_DB_ENCRYPTION_DISABLED", raising=False)
    invalidate_key_cache(db)

    enc = encrypt_field(db, "from-master")
    invalidate_key_cache(db)
    # Key re-derived from same env → same result
    assert decrypt_field(db, enc) == "from-master"


# ---------------------------------------------------------------------------
# EncryptedKVStore
# ---------------------------------------------------------------------------


def test_kv_store_set_get(tmp_path):
    store = EncryptedKVStore(str(tmp_path / "kv.db"))
    store.set("api_token", "sk-real-token")
    assert store.get("api_token") == "sk-real-token"
    store.close()


def test_kv_store_default(tmp_path):
    store = EncryptedKVStore(str(tmp_path / "kv.db"))
    assert store.get("missing", default="fallback") == "fallback"
    store.close()


def test_kv_store_update(tmp_path):
    store = EncryptedKVStore(str(tmp_path / "kv.db"))
    store.set("k", "v1")
    store.set("k", "v2")
    assert store.get("k") == "v2"
    store.close()


def test_kv_store_delete(tmp_path):
    store = EncryptedKVStore(str(tmp_path / "kv.db"))
    store.set("k", "v")
    assert store.delete("k") is True
    assert store.get("k") is None
    store.close()


def test_kv_store_raw_value_is_encrypted(tmp_path):
    db_path = str(tmp_path / "kv.db")
    store = EncryptedKVStore(db_path)
    store.set("secret", "my-password")
    store.close()

    raw = sqlite3.connect(db_path)
    row = raw.execute("SELECT value_enc FROM kv_encrypted").fetchone()
    raw.close()
    assert row[0].startswith("ENC1:")
    assert "my-password" not in row[0]


def test_kv_store_key_hash_not_plaintext(tmp_path):
    db_path = str(tmp_path / "kv.db")
    store = EncryptedKVStore(db_path)
    store.set("api_token", "value")
    store.close()

    raw = sqlite3.connect(db_path)
    row = raw.execute("SELECT key_hash FROM kv_encrypted").fetchone()
    raw.close()
    assert "api_token" not in row[0]


# ---------------------------------------------------------------------------
# connect() factory
# ---------------------------------------------------------------------------


def test_connect_returns_sqlite_connection(db_path):
    con = connect(db_path)
    assert isinstance(con, sqlite3.Connection)
    con.close()


def test_connect_wal_mode(db_path):
    con = connect(db_path)
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert mode == "wal"


def test_connect_foreign_keys(db_path):
    con = connect(db_path)
    fk = con.execute("PRAGMA foreign_keys").fetchone()[0]
    con.close()
    assert fk == 1
