"""
OpenBao Client for Trancendos vault-service
============================================
Provides a unified secret-management interface backed by OpenBao
(MPL 2.0, HashiCorp Vault API-compatible) with an automatic fallback
to the local SQLite AES-GCM vault when OpenBao is not reachable.

Usage
-----
    from openbao_client import store_secret, get_secret, delete_secret, list_secrets

Environment variables
---------------------
    OPENBAO_URL    Base URL of the OpenBao server (default: http://localhost:8200)
    OPENBAO_TOKEN  Root / service token for OpenBao   (default: dev-root-token)

If the ``hvac`` package is not installed, or if the OpenBao server is
unreachable, ALL calls transparently fall through to the SQLite backend
implemented in worker.py.  No exception is ever raised to the caller;
instead a ``backend`` key in the return dict indicates which store was used.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vault-service.openbao_client")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENBAO_URL: str = os.environ.get("OPENBAO_URL", "http://localhost:8200")
OPENBAO_TOKEN: str = os.environ.get("OPENBAO_TOKEN", "dev-root-token")
# KV v2 mount path inside OpenBao — change if you mount at a different path.
_KV_MOUNT: str = os.environ.get("OPENBAO_KV_MOUNT", "secret")

# ---------------------------------------------------------------------------
# Optional hvac import (graceful degradation)
# ---------------------------------------------------------------------------

try:
    import hvac  # type: ignore[import]

    _HVAC_AVAILABLE = True
except ImportError:
    hvac = None  # type: ignore[assignment]
    _HVAC_AVAILABLE = False
    logger.warning(
        "openbao_client: hvac package not installed — OpenBao backend unavailable. "
        "Install with: pip install hvac",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_hvac_client() -> Optional[Any]:
    """Return an authenticated hvac.Client pointed at OpenBao, or None."""
    if not _HVAC_AVAILABLE:
        return None
    try:
        client = hvac.Client(url=OPENBAO_URL, token=OPENBAO_TOKEN)
        if not client.is_authenticated():
            logger.warning("openbao_client: authentication failed — falling back to SQLite vault")
            return None
        return client
    except Exception as exc:  # noqa: BLE001
        logger.debug("openbao_client: cannot reach OpenBao at %s — %s", OPENBAO_URL, exc)
        return None


def _openbao_available() -> bool:
    """Return True if OpenBao is reachable and authenticated."""
    return _get_hvac_client() is not None


# ---------------------------------------------------------------------------
# SQLite fallback shim
# ---------------------------------------------------------------------------
# These imports reference worker.py symbols; they are resolved at call-time
# to avoid circular-import issues during module load.


def _sqlite_store(key: str, value: str) -> Dict[str, Any]:
    import sqlite3

    from worker import (  # noqa: PLC0415
        _append_audit,
        _encrypt_secret,
        _get_db,
        _new_id,
        _now,
    )

    conn = _get_db()
    sid = _new_id()
    now = _now()
    encrypted = _encrypt_secret(value)
    try:
        conn.execute(
            "INSERT INTO secrets (id, key, encrypted_value, tags, ttl, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, key, encrypted, "[]", 3600, now, now),
        )
        _append_audit(conn, sid, "secret.create", details={"key": key, "via": "openbao_client"})
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"ok": False, "backend": "sqlite", "error": f"key '{key}' already exists"}
    conn.close()
    return {"ok": True, "backend": "sqlite", "id": sid, "key": key}


def _sqlite_get(key: str) -> Dict[str, Any]:
    from worker import _append_audit, _decrypt_secret, _get_db, _legacy_xor_decrypt  # noqa: PLC0415

    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM secrets WHERE key=? AND is_active=1",
        (key,),
    ).fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "backend": "sqlite", "error": "not found"}
    try:
        value = _decrypt_secret(row["encrypted_value"])
    except Exception:  # noqa: BLE001
        try:
            value = _legacy_xor_decrypt(row["encrypted_value"])
        except Exception:  # noqa: BLE001
            conn.close()
            return {"ok": False, "backend": "sqlite", "error": "decryption failed"}
    _append_audit(conn, row["id"], "secret.read", details={"via": "openbao_client"})
    conn.commit()
    conn.close()
    return {"ok": True, "backend": "sqlite", "key": key, "value": value}


def _sqlite_delete(key: str) -> Dict[str, Any]:
    from worker import _append_audit, _get_db, _now  # noqa: PLC0415

    conn = _get_db()
    row = conn.execute("SELECT id FROM secrets WHERE key=? AND is_active=1", (key,)).fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "backend": "sqlite", "error": "not found"}
    now = _now()
    conn.execute(
        "UPDATE secrets SET is_active=0, updated_at=? WHERE id=?",
        (now, row["id"]),
    )
    _append_audit(conn, row["id"], "secret.delete", details={"via": "openbao_client"})
    conn.commit()
    conn.close()
    return {"ok": True, "backend": "sqlite", "key": key}


def _sqlite_list() -> Dict[str, Any]:
    from worker import _get_db  # noqa: PLC0415

    conn = _get_db()
    rows = conn.execute(
        "SELECT key FROM secrets WHERE is_active=1 ORDER BY key",
    ).fetchall()
    conn.close()
    return {"ok": True, "backend": "sqlite", "keys": [r["key"] for r in rows]}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_secret(key: str, value: str) -> Dict[str, Any]:
    """
    Store *value* under *key* in the vault.

    Tries OpenBao (KV v2) first; falls back to SQLite AES-GCM vault if
    OpenBao is unavailable.

    Returns a dict with at minimum::

        {"ok": bool, "backend": "openbao" | "sqlite", "key": str}
    """
    client = _get_hvac_client()
    if client is not None:
        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret={"value": value},
                mount_point=_KV_MOUNT,
            )
            logger.debug("openbao_client: stored '%s' via OpenBao", key)
            return {"ok": True, "backend": "openbao", "key": key}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "openbao_client: OpenBao write failed for '%s': %s — using SQLite", key, exc
            )

    return _sqlite_store(key, value)


def get_secret(key: str) -> Dict[str, Any]:
    """
    Retrieve the secret stored under *key*.

    Tries OpenBao first; falls back to SQLite if unavailable.

    Returns a dict with at minimum::

        {"ok": bool, "backend": "openbao" | "sqlite", "key": str, "value": str}

    On miss: ``{"ok": False, "backend": ..., "error": "not found"}``
    """
    client = _get_hvac_client()
    if client is not None:
        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=_KV_MOUNT,
                raise_on_deleted_version=True,
            )
            value = response["data"]["data"].get("value", "")
            logger.debug("openbao_client: fetched '%s' via OpenBao", key)
            return {"ok": True, "backend": "openbao", "key": key, "value": value}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "openbao_client: OpenBao read failed for '%s': %s — using SQLite", key, exc
            )

    return _sqlite_get(key)


def delete_secret(key: str) -> Dict[str, Any]:
    """
    Delete (soft-delete / destroy) the secret stored under *key*.

    Tries OpenBao first (permanently destroys all versions); falls back to
    SQLite soft-delete (sets ``is_active=0``) if unavailable.

    Returns::

        {"ok": bool, "backend": "openbao" | "sqlite", "key": str}
    """
    client = _get_hvac_client()
    if client is not None:
        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=key,
                mount_point=_KV_MOUNT,
            )
            logger.debug("openbao_client: deleted '%s' via OpenBao", key)
            return {"ok": True, "backend": "openbao", "key": key}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "openbao_client: OpenBao delete failed for '%s': %s — using SQLite", key, exc
            )

    return _sqlite_delete(key)


def list_secrets() -> Dict[str, Any]:
    """
    List all secret keys visible to this client.

    Tries OpenBao first; falls back to SQLite if unavailable.

    Returns::

        {"ok": bool, "backend": "openbao" | "sqlite", "keys": List[str]}
    """
    client = _get_hvac_client()
    if client is not None:
        try:
            response = client.secrets.kv.v2.list_secrets(
                path="",
                mount_point=_KV_MOUNT,
            )
            keys: List[str] = response.get("data", {}).get("keys", [])
            logger.debug("openbao_client: listed %d keys via OpenBao", len(keys))
            return {"ok": True, "backend": "openbao", "keys": keys}
        except Exception as exc:  # noqa: BLE001
            logger.warning("openbao_client: OpenBao list failed: %s — using SQLite", exc)

    return _sqlite_list()
