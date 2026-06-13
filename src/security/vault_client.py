"""Universal vault client — REQ-SEC-002 / RSK-003.

Provides a unified interface to The Void (self-hosted vault at port 8038).
All workers should use this client instead of reading secrets from env vars
directly, eliminating REQ-SEC-002 PARTIAL status.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VAULT_URL = os.getenv("VAULT_SERVICE_URL", "http://localhost:8038")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "")
_DEFAULT_TIMEOUT = 5.0


class VaultError(Exception):
    pass


class VaultClient:
    """Async client for The Void self-hosted secrets vault."""

    def __init__(self, base_url: str = VAULT_URL, token: str = VAULT_TOKEN) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._cache: dict[str, tuple[str, datetime]] = {}

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                r = await client.get(f"{self.base_url}/health", headers=self._headers)
                return r.status_code == 200
        except Exception:
            return False

    async def get_secret(self, secret_name: str, use_cache: bool = True) -> str:
        if use_cache and secret_name in self._cache:
            value, cached_at = self._cache[secret_name]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < 300:  # 5-minute TTL
                return value

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                r = await client.post(
                    f"{self.base_url}/secrets/retrieve",
                    headers=self._headers,
                    json={"name": secret_name},
                )
                r.raise_for_status()
                data = r.json()
                value = data.get("value", "")
                self._cache[secret_name] = (value, datetime.now(timezone.utc))
                return value
        except httpx.HTTPStatusError as e:
            logger.error("Vault secret fetch failed for %s: %s", secret_name, e)
            raise VaultError(f"Failed to fetch secret '{secret_name}': {e}") from e
        except Exception as e:
            logger.warning("Vault unreachable, falling back to env for %s: %s", secret_name, e)
            env_val = os.getenv(secret_name.upper().replace("-", "_"), "")
            if env_val:
                return env_val
            raise VaultError(f"Vault unreachable and no env fallback for '{secret_name}'") from e

    async def set_secret(self, secret_name: str, value: str, metadata: dict | None = None) -> str:
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                r = await client.post(
                    f"{self.base_url}/secrets",
                    headers=self._headers,
                    json={"name": secret_name, "value": value, "metadata": metadata or {}},
                )
                r.raise_for_status()
                data = r.json()
                self._cache.pop(secret_name, None)
                return data.get("id", "")
        except Exception as e:
            raise VaultError(f"Failed to set secret '{secret_name}': {e}") from e

    async def list_secrets(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                r = await client.get(f"{self.base_url}/secrets", headers=self._headers)
                r.raise_for_status()
                return r.json().get("secrets", [])
        except Exception as e:
            raise VaultError(f"Failed to list secrets: {e}") from e

    def get_secret_sync(self, secret_name: str) -> str:
        """Synchronous wrapper — use in non-async contexts (startup, config)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't use run_until_complete in running loop — use env fallback
                env_val = os.getenv(secret_name.upper().replace("-", "_"), "")
                return env_val
            return loop.run_until_complete(self.get_secret(secret_name))
        except Exception as e:
            logger.warning("Sync vault get failed for %s, using env: %s", secret_name, e)
            return os.getenv(secret_name.upper().replace("-", "_"), "")


async def migrate_env_secrets_to_vault(client: VaultClient, secret_names: list[str]) -> dict[str, bool]:
    """Migrate named environment secrets into the vault (one-time migration helper)."""
    results: dict[str, bool] = {}
    for name in secret_names:
        env_key = name.upper().replace("-", "_")
        value = os.getenv(env_key, "")
        if not value:
            logger.info("Skipping %s — not set in environment", name)
            results[name] = False
            continue
        try:
            await client.set_secret(name, value, metadata={"source": "env_migration", "migrated_at": datetime.now(timezone.utc).isoformat()})
            results[name] = True
            logger.info("Migrated secret: %s", name)
        except VaultError as e:
            logger.error("Migration failed for %s: %s", name, e)
            results[name] = False
    return results


# Singleton
_vault_client: VaultClient | None = None


def get_vault_client() -> VaultClient:
    global _vault_client
    if _vault_client is None:
        _vault_client = VaultClient()
    return _vault_client
