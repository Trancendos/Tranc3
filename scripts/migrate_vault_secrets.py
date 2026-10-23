"""One-way, verified migration of legacy vault-service secrets into The Void.

Default mode is offline verification only (no network and no destination writes).
Production execution requires --execute and VOID_MIGRATION_BEARER_TOKEN from a
trusted identity provider. Destination must be empty for this identity; reruns
are deliberately refused rather than silently duplicating secrets.

The source database is opened read-only and is never modified/decommissioned.
Do not pass credentials on the command line or record them in job logs.
"""

from __future__ import annotations

import argparse
import hmac
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class MigrationError(RuntimeError):
    """An intentionally non-sensitive migration failure."""


def decrypt_legacy(ciphertext_hex: str, key_seed: str) -> str:
    """Read legacy AES-GCM envelope: 32-byte salt, 12-byte IV, ciphertext + tag.

    Legacy XOR ciphertexts are intentionally *not* supported; they need an
    independently reviewed, authenticated re-encryption process.
    """
    raw = bytes.fromhex(ciphertext_hex)
    if len(raw) < 60:
        raise ValueError("Invalid legacy AES-GCM envelope")
    salt, nonce, encrypted = raw[:32], raw[32:44], raw[44:]
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
    ).derive(key_seed.encode())
    return AESGCM(key).decrypt(nonce, encrypted, None).decode()


def _validate_destination(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise MigrationError("Destination URL must not contain credentials or query data")
    if parsed.scheme == "https" and parsed.hostname:
        return url.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return url.rstrip("/")
    raise MigrationError("Destination requires HTTPS, except for loopback testing")


def migrate(
    vault_db: str,
    *,
    master_key: str,
    execute: bool = False,
    bearer_token: str = "",
    void_url: str = "http://localhost:8002",
    transport: httpx.BaseTransport | None = None,
) -> dict[str, int]:
    """Check source offline or copy to an empty destination with readback.

    Refuses an occupied target. Failures leave the source untouched; any
    successful destination writes made before a failure require manual review.
    """
    if not master_key:
        raise MigrationError("Legacy decryption key is required")
    path = Path(vault_db).expanduser().resolve()
    if not path.is_file():
        raise MigrationError("Source vault database is missing")
    if execute and not bearer_token.strip():
        raise MigrationError("A verified migration bearer token is required for execution")
    if execute:
        void_url = _validate_destination(void_url)

    try:
        # SQLite URI mode=ro rejects writes and avoids creating a missing DB.
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT encrypted_value, key FROM secrets WHERE is_active=1 ORDER BY id"
            ).fetchall()
    except sqlite3.Error:
        raise MigrationError("Cannot read source vault schema") from None

    # Validate every encrypted record before the first write, without caching
    # plaintext secrets in a long-lived collection.
    try:
        for blob, _ in rows:
            decrypt_legacy(blob, master_key)
    except (ValueError, UnicodeError, TypeError):
        raise MigrationError("Source contains an invalid legacy encryption envelope") from None
    except Exception:
        raise MigrationError("Source authentication failed; no secrets were migrated") from None

    if not execute:
        return {"verified": len(rows), "migrated": 0}
    if not rows:
        return {"verified": 0, "migrated": 0}

    headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
    migrated = 0
    try:
        with httpx.Client(base_url=void_url, headers=headers, timeout=15, transport=transport) as client:
            inventory = client.get("/secrets")
            inventory.raise_for_status()
            existing = inventory.json()
            if not isinstance(existing, dict) or existing.get("count") != 0 or existing.get("secrets") != []:
                raise MigrationError("Destination is not empty; refusing non-idempotent migration")

            for blob, name in rows:
                plaintext = decrypt_legacy(blob, master_key)
                response = client.post("/secrets", json={"name": name, "value": plaintext})
                response.raise_for_status()
                secret_id = response.json().get("secret_id")
                if not isinstance(secret_id, str) or not secret_id:
                    raise MigrationError("Destination did not confirm the stored secret ID")
                readback = client.post("/secrets/retrieve", json={"secret_id": secret_id})
                readback.raise_for_status()
                returned = readback.json().get("plaintext")
                if not isinstance(returned, str) or not hmac.compare_digest(returned, plaintext):
                    raise MigrationError("Destination readback mismatch; migration halted")
                migrated += 1
                plaintext = None  # Drop the last local reference promptly.
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise MigrationError(
            "Destination API failed; source unchanged, inspect partial destination writes"
        ) from None
    return {"verified": len(rows), "migrated": migrated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or migrate legacy vault secrets")
    parser.add_argument("--vault-db", default=os.getenv("VAULT_DB_PATH", "data/vault.db"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Offline verification (default)")
    modes.add_argument("--execute", action="store_true", help="Write and verify in the target")
    args = parser.parse_args()
    try:
        result = migrate(
            args.vault_db,
            master_key=os.getenv("VAULT_MASTER_KEY", ""),
            execute=args.execute,
            bearer_token=os.getenv("VOID_MIGRATION_BEARER_TOKEN", ""),
            void_url=os.getenv("VOID_URL", "http://localhost:8002"),
        )
    except MigrationError as exc:
        parser.exit(1, f"Migration stopped: {exc}\n")
    print(f"Verified: {result['verified']}; migrated: {result['migrated']}; source retained")


if __name__ == "__main__":
    main()
