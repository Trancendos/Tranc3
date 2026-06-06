"""
Encrypted SQLite — AES-GCM At-Rest Encryption Utilities
========================================================
Provides two complementary layers:

1. **Field-level helpers** — ``encrypt_field`` / ``decrypt_field`` / ``decrypt_row``
   Used in model code to protect individual sensitive columns (passwords, tokens,
   PII) without breaking SQL WHERE-clause lookups.

2. **Encrypted key-value store** — ``EncryptedKVStore``
   A simple encrypted table for arbitrary secret values, used by workers that
   need to persist credentials, session tokens, or API keys in SQLite.

3. **Connection factory** — ``connect``
   Drop-in for ``sqlite3.connect()`` that automatically runs ``PRAGMA journal_mode=WAL``
   and ``PRAGMA foreign_keys=ON``, and injects the field helpers into the connection
   namespace. Works transparently; callers opt in to column encryption via the
   field helpers.

Why not full transparent row encryption?
-----------------------------------------
Encrypting every value (including WHERE-clause params) with a random IV breaks
SQL equality lookups — each encryption call produces a different ciphertext.
The correct trade-off is: **index / lookup columns stay plaintext; sensitive
data columns are encrypted at the application layer using the helpers below**.

Encryption model
-----------------
* One **database key** per file, derived from the platform master secret via
  HKDF-SHA256 (salt = SHA-256(canonical_db_path)).
* Per encrypted value: ``b"ENC1:" + base64(iv[12] + tag[16] + ciphertext)``
* Values not prefixed with ``ENC1:`` are returned as-is (backwards compat).

Key source (priority order)
-----------------------------
1. ``TRANC3_DB_MASTER_KEY`` env var (hex-encoded ≥ 16 bytes)
2. ``SECRET_KEY`` env var (stretched via PBKDF2-HMAC-SHA256, 100k iterations)
3. Dev-mode deterministic key from db path + hostname (NOT for production)

Set ``TRANC3_DB_ENCRYPTION_DISABLED=1`` to bypass encryption (CI / unit tests
that need exact-value assertions on raw rows).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("tranc3.database.encrypted_sqlite")

_SENTINEL = b"ENC1:"
_KEY_CACHE: dict[str, bytes] = {}

# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def _derive_key(db_path: str) -> bytes:
    """Return a stable 32-byte AES key for *db_path*."""
    canonical = str(Path(db_path).resolve())
    if canonical in _KEY_CACHE:
        return _KEY_CACHE[canonical]

    salt = hashlib.sha256(canonical.encode()).digest()

    master_hex = os.environ.get("TRANC3_DB_MASTER_KEY", "")
    secret_key = os.environ.get("SECRET_KEY", "")

    if master_hex:
        try:
            master = bytes.fromhex(master_hex.strip())
            if len(master) < 16:
                raise ValueError("TRANC3_DB_MASTER_KEY too short")
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                info=b"tranc3-sqlite-encryption-v1",
            ).derive(master)
            _KEY_CACHE[canonical] = key
            return key
        except ValueError:
            logger.warning("TRANC3_DB_MASTER_KEY is not valid hex; falling back to SECRET_KEY")

    if secret_key:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = kdf.derive(secret_key.encode())
        _KEY_CACHE[canonical] = key
        return key

    import socket
    logger.warning(
        "No TRANC3_DB_MASTER_KEY or SECRET_KEY; using dev-mode encryption key for %s "
        "— NOT suitable for production",
        canonical,
    )
    seed = f"dev:{canonical}:{socket.gethostname()}".encode()
    key = hashlib.sha256(seed).digest()
    _KEY_CACHE[canonical] = key
    return key


def invalidate_key_cache(db_path: Optional[str] = None) -> None:
    """Flush the in-process key cache (useful after key rotation or in tests)."""
    if db_path:
        _KEY_CACHE.pop(str(Path(db_path).resolve()), None)
    else:
        _KEY_CACHE.clear()


# ---------------------------------------------------------------------------
# Field-level encrypt / decrypt helpers
# ---------------------------------------------------------------------------


def _is_disabled() -> bool:
    return os.environ.get("TRANC3_DB_ENCRYPTION_DISABLED", "").strip() in ("1", "true", "yes")


def encrypt_field(db_path: str, value: Any) -> Any:
    """Encrypt a TEXT or BLOB value for storage in *db_path*.

    Non-string / non-bytes values (int, float, None) are returned unchanged.
    If encryption is disabled returns *value* unchanged.
    """
    if _is_disabled() or value is None:
        return value
    key = _derive_key(db_path)
    if isinstance(value, str):
        return _encrypt_bytes(key, value.encode()).decode()
    if isinstance(value, (bytes, bytearray)):
        return _encrypt_bytes(key, bytes(value))
    return value


def decrypt_field(db_path: str, value: Any) -> Any:
    """Decrypt a value previously encrypted by ``encrypt_field``.

    Returns non-encrypted values unchanged (backwards compat).
    """
    if _is_disabled() or value is None:
        return value
    key = _derive_key(db_path)
    if isinstance(value, str):
        bv = value.encode()
        if bv.startswith(_SENTINEL):
            return _decrypt_bytes(key, bv).decode()
        return value
    if isinstance(value, bytes):
        if value.startswith(_SENTINEL):
            return _decrypt_bytes(key, value)
        return value
    return value


def decrypt_row(db_path: str, row: Optional[tuple], columns: Optional[List[int]] = None) -> Optional[tuple]:
    """Decrypt selected columns (by index) of *row*, or all columns if *columns* is None."""
    if row is None:
        return None
    if columns is None:
        return tuple(decrypt_field(db_path, v) for v in row)
    return tuple(
        decrypt_field(db_path, v) if i in columns else v
        for i, v in enumerate(row)
    )


# ---------------------------------------------------------------------------
# Low-level AES-GCM
# ---------------------------------------------------------------------------


def _encrypt_bytes(key: bytes, plaintext: bytes) -> bytes:
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plaintext, None)
    return _SENTINEL + base64.b64encode(iv + ct)


def _decrypt_bytes(key: bytes, blob: bytes) -> bytes:
    raw = base64.b64decode(blob[len(_SENTINEL):])
    iv, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(iv, ct, None)


# ---------------------------------------------------------------------------
# Encrypted key-value store (for secrets / tokens / credentials)
# ---------------------------------------------------------------------------


class EncryptedKVStore:
    """A simple encrypted key-value table on top of SQLite.

    Keys are stored as plaintext SHA-256 HMACs (to support lookup), values
    are encrypted with AES-GCM.

    ::

        store = EncryptedKVStore("data/secrets.db")
        store.set("api_token", "sk-real-token-here")
        token = store.get("api_token")   # returns "sk-real-token-here"
        store.delete("api_token")
    """

    def __init__(self, db_path: str, table: str = "kv_encrypted") -> None:
        self.db_path = db_path
        self.table = table
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table} "
            "(key_hash TEXT PRIMARY KEY, value_enc TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        self._conn.commit()

    def _key_hash(self, key: str) -> str:
        import hmac as _hmac
        return _hmac.new(
            _derive_key(self.db_path),
            key.encode(),
            hashlib.sha256,
        ).hexdigest()

    def set(self, key: str, value: str) -> None:
        from datetime import datetime, timezone
        h = self._key_hash(key)
        enc = encrypt_field(self.db_path, value)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            f"INSERT INTO {self.table} (key_hash, value_enc, updated_at) "
            "VALUES (?,?,?) ON CONFLICT(key_hash) DO UPDATE SET value_enc=excluded.value_enc, updated_at=excluded.updated_at",
            (h, enc, now),
        )
        self._conn.commit()

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        h = self._key_hash(key)
        row = self._conn.execute(
            f"SELECT value_enc FROM {self.table} WHERE key_hash=?", (h,)
        ).fetchone()
        if row is None:
            return default
        return decrypt_field(self.db_path, row[0])

    def delete(self, key: str) -> bool:
        h = self._key_hash(key)
        cur = self._conn.execute(
            f"DELETE FROM {self.table} WHERE key_hash=?", (h,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def connect(
    database: str,
    *,
    check_same_thread: bool = False,
    timeout: float = 5.0,
    **kwargs: Any,
) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled.

    Drop-in replacement for ``sqlite3.connect()``.  Use ``encrypt_field`` /
    ``decrypt_field`` / ``decrypt_row`` to protect individual sensitive columns.
    """
    conn = sqlite3.connect(database, check_same_thread=check_same_thread, timeout=timeout, **kwargs)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
