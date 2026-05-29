"""
Dimensional.architecture.storage_factory — Environment-aware storage provider pattern.

Implements the Factory pattern to provide the correct storage backend based
on the SYSTEM_MODE environment variable. All providers adhere to the same
interface, so the rest of the codebase never needs to know which backend
is in use.

SYSTEM_MODE values:
    TRUE_NAS    — Local NAS storage (primary), no cloud dependencies
    HYBRID      — Local NAS (primary) + cloud sync (secondary)
    CLOUD_ONLY  — Cloud storage only (for remote deployments)

Zero-Cost Mandate:
    - TRUE_NAS uses local filesystem (free)
    - HYBRID uses local + Cloudflare R2 free tier (10GB + 10M reads/month)
    - CLOUD_ONLY uses Cloudflare R2 free tier

All providers implement the same async interface:
    - read(path) → bytes
    - write(path, data) → None
    - delete(path) → None
    - list(prefix) → List[str]
    - exists(path) → bool
    - health() → Dict[str, Any]

Usage:
    factory = StorageFactory()
    storage = factory.get_provider()
    await storage.write("data/file.json", b'{"key": "value"}')
    data = await storage.read("data/file.json")
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class SystemMode(Enum):
    """Deployment environment mode."""

    TRUE_NAS = "TRUE_NAS"
    HYBRID = "HYBRID"
    CLOUD_ONLY = "CLOUD_ONLY"


def _get_system_mode() -> SystemMode:
    """Read SYSTEM_MODE from environment, defaulting to TRUE_NAS."""
    raw = os.getenv("SYSTEM_MODE", "TRUE_NAS").upper()
    try:
        return SystemMode(raw)
    except ValueError:
        logger.warning("Unknown SYSTEM_MODE %r, defaulting to TRUE_NAS", raw)
        return SystemMode.TRUE_NAS


def _get_storage_root() -> Path:
    """Get the local storage root directory."""
    raw = os.getenv("STORAGE_ROOT", "/mnt/data/tranc3")
    return Path(raw)


# ---------------------------------------------------------------------------
# Abstract storage provider
# ---------------------------------------------------------------------------


class StorageProvider(ABC):
    """Abstract base class for storage providers.

    All storage providers must implement this interface. The factory
    returns the correct provider based on SYSTEM_MODE.
    """

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """Read data from storage.

        Args:
            path: Relative path within the storage namespace.

        Returns:
            The file contents as bytes.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        ...

    @abstractmethod
    async def write(self, path: str, data: bytes) -> None:
        """Write data to storage.

        Args:
            path: Relative path within the storage namespace.
            data: The data to write.
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete data from storage.

        Args:
            path: Relative path within the storage namespace.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        ...

    @abstractmethod
    async def list(self, prefix: str = "") -> List[str]:
        """List paths in storage matching a prefix.

        Args:
            prefix: Path prefix to filter by (empty = all).

        Returns:
            List of relative path strings.
        """
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a path exists in storage.

        Args:
            path: Relative path within the storage namespace.

        Returns:
            True if the path exists.
        """
        ...

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Return health information about the storage provider.

        Returns:
            Dict with keys: status, mode, details.
        """
        ...


# ---------------------------------------------------------------------------
# TRUE_NAS provider — local filesystem
# ---------------------------------------------------------------------------


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider for TRUE_NAS mode.

    Stores all data on the local filesystem. No cloud dependencies.
    Uses the STORAGE_ROOT environment variable (default: /mnt/data/tranc3).
    """

    def __init__(self, root: Optional[Path] = None):
        self._root = root or _get_storage_root()
        self._root.mkdir(parents=True, exist_ok=True)
        self._mode = SystemMode.TRUE_NAS

    async def read(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"Storage path not found: {path}")
        return target.read_bytes()

    async def write(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.debug("Wrote %d bytes to %s", len(data), sanitize_for_log(path))

    async def delete(self, path: str) -> None:
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"Storage path not found: {path}")
        target.unlink()

    async def list(self, prefix: str = "") -> List[str]:
        base = self._resolve(prefix) if prefix else self._root
        if not base.exists():
            return []
        if base.is_file():
            return [str(base.relative_to(self._root))]
        results = []
        for f in base.rglob("*"):
            if f.is_file():
                results.append(str(f.relative_to(self._root)))
        return sorted(results)

    async def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    async def health(self) -> Dict[str, Any]:
        usage = shutil.disk_usage(self._root)
        return {
            "status": "healthy",
            "mode": self._mode.value,
            "root": str(self._root),
            "disk_usage": {
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": round(usage.used / usage.total * 100, 1),
            },
        }

    def _resolve(self, path: str) -> Path:
        """Resolve a relative path against the storage root."""
        resolved = (self._root / path).resolve()
        # Security: ensure path stays within storage root
        try:
            resolved.relative_to(self._root.resolve())
        except ValueError:
            raise ValueError(f"Path escapes storage root: {path}") from None
        return resolved


# ---------------------------------------------------------------------------
# CLOUD_ONLY provider — Cloudflare R2 (free tier)
# ---------------------------------------------------------------------------


class CloudStorageProvider(StorageProvider):
    """Cloud storage provider using Cloudflare R2 (S3-compatible, free tier).

    Free tier: 10 GB storage, 10M class A ops, 1M class B ops/month.
    Uses boto3-compatible interface via environment variable configuration.

    Required environment variables:
        R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
    """

    def __init__(self):
        self._mode = SystemMode.CLOUD_ONLY
        self._account_id = os.getenv("R2_ACCOUNT_ID", "")
        self._bucket = os.getenv("R2_BUCKET_NAME", "tranc3-data")
        self._client = None

    def _get_client(self):
        """Lazy-initialize the S3 client for R2."""
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client(
                    "s3",
                    endpoint_url=f"https://{self._account_id}.r2.cloudflarestorage.com",
                    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID", ""),
                    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", ""),
                    region_name="auto",
                )
            except ImportError:
                raise RuntimeError(
                    "boto3 is required for CLOUD_ONLY mode. Install it with: pip install boto3"
                ) from None
        return self._client

    async def read(self, path: str) -> bytes:
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self._bucket, Key=path)
            return response["Body"].read()
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"Storage path not found: {path}") from e
            raise

    async def write(self, path: str, data: bytes) -> None:
        client = self._get_client()
        client.put_object(Bucket=self._bucket, Key=path, Body=data)
        logger.debug(
            "Wrote %d bytes to R2://%s/%s", len(data), self._bucket, sanitize_for_log(path)
        )

    async def delete(self, path: str) -> None:
        client = self._get_client()
        try:
            client.delete_object(Bucket=self._bucket, Key=path)
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"Storage path not found: {path}") from e
            raise

    async def list(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        results = []
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                results.append(obj["Key"])
        return sorted(results)

    async def exists(self, path: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=self._bucket, Key=path)
            return True
        except Exception:
            return False

    async def health(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._bucket)
            return {
                "status": "healthy",
                "mode": self._mode.value,
                "bucket": self._bucket,
                "provider": "cloudflare-r2",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "mode": self._mode.value,
                "bucket": self._bucket,
                "provider": "cloudflare-r2",
                "error": str(e),
            }


# ---------------------------------------------------------------------------
# HYBRID provider — local primary + cloud sync
# ---------------------------------------------------------------------------


class HybridStorageProvider(StorageProvider):
    """Hybrid storage provider — local primary with cloud sync.

    Writes go to local storage first, then asynchronously sync to R2.
    Reads always come from local storage. If local is unavailable,
    falls back to cloud. This ensures low latency for reads while
    maintaining cloud redundancy.

    Auto-sync: A background asyncio task runs every sync_interval_seconds
    to flush the sync queue to cloud storage, ensuring eventual consistency
    without requiring manual sync_to_cloud() calls.
    """

    def __init__(self, root: Optional[Path] = None, sync_interval_seconds: int = 60):
        self._local = LocalStorageProvider(root)
        self._cloud = CloudStorageProvider()
        self._mode = SystemMode.HYBRID
        self._sync_queue: List[str] = []
        self._sync_lock = threading.Lock()
        self._sync_enabled = bool(os.getenv("R2_ACCOUNT_ID"))
        self._sync_interval = sync_interval_seconds
        self._sync_task: Optional[asyncio.Task] = None
        self._sync_stats = {"total_synced": 0, "total_failed": 0, "last_sync": None}

    async def read(self, path: str) -> bytes:
        # Try local first
        try:
            return await self._local.read(path)
        except FileNotFoundError:
            if self._sync_enabled:
                # Fall back to cloud
                data = await self._cloud.read(path)
                # Cache locally
                await self._local.write(path, data)
                return data
            raise

    async def write(self, path: str, data: bytes) -> None:
        # Write locally first
        await self._local.write(path, data)
        # Queue for cloud sync
        if self._sync_enabled:
            with self._sync_lock:
                self._sync_queue.append(path)

    async def delete(self, path: str) -> None:
        await self._local.delete(path)
        if self._sync_enabled:
            try:
                await self._cloud.delete(path)
            except FileNotFoundError:
                pass

    async def list(self, prefix: str = "") -> List[str]:
        return await self._local.list(prefix)

    async def exists(self, path: str) -> bool:
        return await self._local.exists(path)

    async def health(self) -> Dict[str, Any]:
        local_health = await self._local.health()
        local_health["mode"] = self._mode.value
        local_health["sync_enabled"] = self._sync_enabled
        local_health["auto_sync_active"] = (
            self._sync_task is not None and not self._sync_task.done()
        )
        with self._sync_lock:
            local_health["pending_sync"] = len(self._sync_queue)
        local_health["sync_stats"] = self._sync_stats
        if self._sync_enabled:
            cloud_health = await self._cloud.health()
            local_health["cloud_status"] = cloud_health["status"]
        return local_health

    async def sync_to_cloud(self) -> int:
        """Sync all pending writes to cloud storage.

        Returns:
            Number of files synced.
        """
        if not self._sync_enabled:
            return 0

        synced = 0
        with self._sync_lock:
            queue = list(self._sync_queue)
            self._sync_queue.clear()

        for path in queue:
            try:
                data = await self._local.read(path)
                await self._cloud.write(path, data)
                synced += 1
            except Exception as e:
                logger.error("Cloud sync failed for %s: %s", sanitize_for_log(path), e)
                self._sync_stats["total_failed"] += 1
                with self._sync_lock:
                    self._sync_queue.append(path)  # Re-queue

        self._sync_stats["total_synced"] += synced
        self._sync_stats["last_sync"] = datetime.now(timezone.utc).isoformat()
        return synced

    async def start_auto_sync(self) -> None:
        """Start the background auto-sync task.

        This ensures that write operations queued for cloud sync
        are automatically flushed every sync_interval_seconds without
        requiring manual sync_to_cloud() calls. The task runs as an
        asyncio background task and will stop when stop_auto_sync() is
        called or the event loop shuts down.
        """
        if self._sync_task is not None and not self._sync_task.done():
            logger.warning("Auto-sync task already running")
            return
        self._sync_task = asyncio.create_task(self._auto_sync_loop())
        logger.info("Auto-sync started (interval=%ds)", self._sync_interval)

    async def stop_auto_sync(self) -> None:
        """Stop the background auto-sync task gracefully."""
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            # Final sync before stopping
            await self.sync_to_cloud()
        self._sync_task = None
        logger.info("Auto-sync stopped")

    async def _auto_sync_loop(self) -> None:
        """Background loop that periodically syncs queued writes to cloud."""
        while True:
            try:
                await asyncio.sleep(self._sync_interval)
                with self._sync_lock:
                    pending = len(self._sync_queue)
                if pending > 0:
                    logger.debug("Auto-sync: %d files pending", pending)
                    synced = await self.sync_to_cloud()
                    if synced > 0:
                        logger.info("Auto-sync: %d files synced to cloud", synced)
            except asyncio.CancelledError:
                logger.info("Auto-sync loop cancelled")
                break
            except Exception as e:
                logger.error("Auto-sync loop error: %s", sanitize_for_log(str(e)))
                # Continue running despite errors
                await asyncio.sleep(self._sync_interval)


# ---------------------------------------------------------------------------
# StorageFactory
# ---------------------------------------------------------------------------


class StorageFactory:
    """Factory that provides the correct storage provider based on SYSTEM_MODE.

    Implements the Factory pattern with environment-aware provider selection.
    All providers implement the same StorageProvider interface, so consumers
    never need to know which backend is in use.

    Usage:
        factory = StorageFactory()
        storage = factory.get_provider()
        await storage.write("data/file.json", b'{"key": "value"}')

        # Or with explicit mode:
        storage = factory.get_provider(mode=SystemMode.TRUE_NAS)
    """

    _instance: Optional[StorageProvider] = None
    _instance_mode: Optional[SystemMode] = None

    def get_provider(self, mode: Optional[SystemMode] = None) -> StorageProvider:
        """Get the storage provider for the current or specified mode.

        Args:
            mode: Explicit mode to use. If None, reads from SYSTEM_MODE env var.

        Returns:
            A StorageProvider instance appropriate for the mode.

        Cloud Provider Selection (CLOUD_ONLY / HYBRID):
            - If OCI_COMPARTMENT_ID is set → OCI Object Storage (10GB free)
            - Else if R2_ACCOUNT_ID is set → Cloudflare R2 (10GB free)
            - Else → LocalStorageProvider (filesystem, always free)
        """
        effective_mode = mode or _get_system_mode()

        # Return cached instance if mode hasn't changed
        if self._instance is not None and self._instance_mode == effective_mode:
            return self._instance

        if effective_mode == SystemMode.TRUE_NAS:
            provider = LocalStorageProvider()
        elif effective_mode == SystemMode.HYBRID:
            # Choose cloud backend based on available credentials
            cloud_provider = self._detect_cloud_provider()
            if cloud_provider == "oci":
                provider = self._create_hybrid_with_oci()
            elif cloud_provider == "r2":
                provider = HybridStorageProvider()
            else:
                # No cloud credentials — fall back to local-only
                logger.warning("No cloud credentials found (OCI or R2), using local-only storage")
                provider = LocalStorageProvider()
        elif effective_mode == SystemMode.CLOUD_ONLY:
            cloud_provider = self._detect_cloud_provider()
            if cloud_provider == "oci":
                from Dimensional.architecture.oci_storage import OCIObjectStorageProvider

                provider = OCIObjectStorageProvider()
            elif cloud_provider == "r2":
                provider = CloudStorageProvider()
            else:
                logger.warning("No cloud credentials found, falling back to local storage")
                provider = LocalStorageProvider()
        else:
            logger.warning("Unknown mode %s, falling back to TRUE_NAS", effective_mode)
            provider = LocalStorageProvider()

        self._instance = provider
        self._instance_mode = effective_mode
        logger.info(
            "Storage provider initialized: %s mode (cloud=%s)",
            effective_mode.value,
            self._detect_cloud_provider(),
        )
        return provider

    def _detect_cloud_provider(self) -> str:
        """Detect which cloud provider to use based on environment variables.

        Priority: OCI > R2 > none
        OCI has the most generous free tier (10GB + 10TB outbound).
        """
        if os.getenv("OCI_COMPARTMENT_ID"):
            return "oci"
        if os.getenv("R2_ACCOUNT_ID"):
            return "r2"
        return "none"

    def _create_hybrid_with_oci(self) -> HybridStorageProvider:
        """Create a hybrid provider with OCI as the cloud backend.

        Since HybridStorageProvider currently uses CloudStorageProvider (R2),
        we create it but override the cloud provider with OCI.
        """
        hybrid = HybridStorageProvider()
        # Replace the cloud provider with OCI
        from Dimensional.architecture.oci_storage import OCIObjectStorageProvider

        hybrid._cloud = OCIObjectStorageProvider()
        hybrid._sync_enabled = True
        return hybrid

    @classmethod
    def reset(cls) -> None:
        """Reset the cached provider instance (useful for testing)."""
        cls._instance = None
        cls._instance_mode = None
