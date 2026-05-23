"""
shared_core.architecture.smart_storage — Adaptive Interchangeable Smart ZFS Storage Providers.

Implements environment-aware, zero-cost storage with intelligent failover,
capacity monitoring, and proactive tier migration.

Design Principles:
    - Smart: Auto-detects environment and selects optimal provider
    - Intelligent: Monitors capacity and proactively migrates before limits
    - Logical: Priority-based provider selection (ZFS → MinIO → Ceph → R2 → OCI)
    - Adaptive: Switches providers dynamically based on availability and cost
    - Fluidic: Seamless data flow between storage tiers
    - Dynamic: Runtime provider switching without data loss
    - Modular: Each provider is independently pluggable
    - Nanoservice: Each operation is atomic and self-contained

Storage Tier Priority (Zero-Cost Mandate):
    Tier 0: ZFS (local NAS — unlimited, fastest, free)
    Tier 1: MinIO (local S3-compatible — unlimited, fast, free)
    Tier 2: Ceph (distributed — scalable, self-hosted, free)
    Tier 3: Cloudflare R2 (cloud — 10GB free, egress-free)
    Tier 4: OCI Object Storage (cloud — 10GB free tier)

SYSTEM_MODE:
    TRUE_NAS   — Primary: ZFS/MinIO (local), No cloud fallback
    HYBRID     — Primary: ZFS/MinIO (local), Fallback: R2/OCI (cloud free tier)
    CLOUD_ONLY — Primary: R2 (cloud free tier), Fallback: OCI (cloud free tier)

Zero-Cost Auto-Modulation:
    When a location approaches its free-tier limit, the system proactively
    migrates data to an alternative free-tier provider before any charges
    can occur. This ensures 0 cost is maintained at all times.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SystemMode(Enum):
    """Deployment environment mode."""
    TRUE_NAS = "TRUE_NAS"
    HYBRID = "HYBRID"
    CLOUD_ONLY = "CLOUD_ONLY"


class StorageTier(Enum):
    """Storage tier priority levels."""
    ZFS = 0          # Local NAS — unlimited, fastest, free
    MINIO = 1        # Local S3-compatible — unlimited, fast, free
    CEPH = 2         # Distributed — scalable, self-hosted, free
    R2 = 3           # Cloudflare R2 — 10GB free, egress-free
    OCI = 4          # OCI Object Storage — 10GB free tier


@dataclass
class TierCapacity:
    """Capacity tracking for a storage tier."""
    tier: StorageTier
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    is_available: bool = False
    last_checked: float = 0.0
    warning_threshold: float = 0.80   # Alert at 80% usage
    critical_threshold: float = 0.95  # Migrate at 95% usage

    @property
    def usage_pct(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.used_bytes / self.total_bytes

    @property
    def is_warning(self) -> bool:
        return self.usage_pct >= self.warning_threshold

    @property
    def is_critical(self) -> bool:
        return self.usage_pct >= self.critical_threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.name,
            "total_gb": round(self.total_bytes / (1024**3), 2),
            "used_gb": round(self.used_bytes / (1024**3), 2),
            "free_gb": round(self.free_bytes / (1024**3), 2),
            "usage_pct": round(self.usage_pct * 100, 1),
            "is_available": self.is_available,
            "is_warning": self.is_warning,
            "is_critical": self.is_critical,
            "last_checked": datetime.fromtimestamp(self.last_checked, tz=timezone.utc).isoformat() if self.last_checked else None,
        }


# ---------------------------------------------------------------------------
# Abstract Smart Storage Provider
# ---------------------------------------------------------------------------

class SmartStorageProvider(ABC):
    """Abstract base class for all smart storage providers.

    Extends the basic StorageProvider interface with:
    - Capacity monitoring
    - Tier-aware operations
    - Health reporting with capacity metrics
    - Snapshot support
    - Compression support
    """

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """Read data from storage."""

    @abstractmethod
    async def write(self, path: str, data: bytes) -> None:
        """Write data to storage."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete data from storage."""

    @abstractmethod
    async def list(self, prefix: str = "") -> List[str]:
        """List objects with given prefix."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a path exists."""

    @abstractmethod
    async def get_capacity(self) -> TierCapacity:
        """Get current capacity information."""

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Return health status including capacity."""

    @property
    @abstractmethod
    def tier(self) -> StorageTier:
        """The storage tier of this provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""


# ---------------------------------------------------------------------------
# ZFS Storage Provider
# ---------------------------------------------------------------------------

class ZFSStorageProvider(SmartStorageProvider):
    """ZFS-based storage provider for TRUE_NAS mode.

    Features:
    - Native ZFS snapshots (hourly/daily/weekly/monthly)
    - ZFS replication with zstd compression
    - Encrypted dataset support
    - Automatic snapshot rotation
    - Dataset-level capacity monitoring

    Zero-cost: ZFS is filesystem-level, no additional software cost.
    """

    def __init__(
        self,
        pool_name: str = "tank",
        dataset_prefix: str = "tranc3",
        mount_root: Optional[str] = None,
        compression: str = "zstd",
        encryption: bool = False,
    ):
        self._pool_name = pool_name
        self._dataset_prefix = dataset_prefix
        self._mount_root = Path(mount_root or f"/mnt/{pool_name}/{dataset_prefix}")
        self._compression = compression
        self._encryption = encryption
        self._tier_value = StorageTier.ZFS

    @property
    def tier(self) -> StorageTier:
        return self._tier_value

    @property
    def name(self) -> str:
        return f"ZFS({self._pool_name}/{self._dataset_prefix})"

    def _resolve_path(self, path: str) -> Path:
        """Resolve a relative storage path to a filesystem path.

        Enforces that the resolved path stays within the mount root
        to prevent path traversal attacks (e.g. '../../../etc/passwd').
        """
        resolved = (self._mount_root / path.lstrip("/")).resolve()
        mount_resolved = self._mount_root.resolve()
        if not str(resolved).startswith(str(mount_resolved)):
            raise ValueError(f"Path traversal blocked: {path} escapes mount root {self._mount_root}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    async def read(self, path: str) -> bytes:
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"ZFS: path not found: {path}")
        return await asyncio.to_thread(file_path.read_bytes)

    async def write(self, path: str, data: bytes) -> None:
        file_path = self._resolve_path(path)
        await asyncio.to_thread(file_path.write_bytes, data)

    async def delete(self, path: str) -> None:
        file_path = self._resolve_path(path)
        if file_path.exists():
            await asyncio.to_thread(file_path.unlink)

    async def list(self, prefix: str = "") -> List[str]:
        search_dir = self._resolve_path(prefix)
        if not search_dir.exists():
            return []
        results = []
        for f in search_dir.rglob("*"):
            if f.is_file():
                rel = str(f.relative_to(self._mount_root))
                results.append(rel)
        return sorted(results)

    async def exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    async def get_capacity(self) -> TierCapacity:
        """Get ZFS pool capacity using filesystem stats."""
        cap = TierCapacity(tier=StorageTier.ZFS)
        try:
            stat = await asyncio.to_thread(shutil.disk_usage, str(self._mount_root))
            cap.total_bytes = stat.total
            cap.used_bytes = stat.used
            cap.free_bytes = stat.free
            cap.is_available = True
            cap.last_checked = time.time()
        except Exception as e:
            logger.warning("ZFS capacity check failed: %s", e)
            cap.is_available = False
            cap.last_checked = time.time()
        return cap

    async def health(self) -> Dict[str, Any]:
        cap = await self.get_capacity()
        return {
            "provider": self.name,
            "tier": self.tier.name,
            "status": "healthy" if cap.is_available else "unavailable",
            "capacity": cap.to_dict(),
            "compression": self._compression,
            "encryption": self._encryption,
            "pool": self._pool_name,
            "dataset": self._dataset_prefix,
        }

    # ZFS-specific operations

    async def create_snapshot(
        self,
        dataset: str,
        label: str = "auto",
    ) -> str:
        """Create a ZFS snapshot. Returns snapshot name.

        Snapshot naming: {pool}/{dataset}@{label}-{timestamp}
        Example: tank/tranc3/data@auto-20250522T143000Z
        """
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap_name = f"{self._pool_name}/{dataset}@{label}-{ts}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "zfs", "snapshot", snap_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("ZFS snapshot failed: %s", stderr.decode())
                raise RuntimeError(f"ZFS snapshot failed: {stderr.decode()}")
            logger.info("ZFS snapshot created: %s", snap_name)
            return snap_name
        except FileNotFoundError:
            logger.warning("zfs command not found — snapshot skipped (non-ZFS environment)")
            return f"mock-snapshot:{snap_name}"

    async def list_snapshots(self, dataset: str = "") -> List[str]:
        """List ZFS snapshots for a dataset."""
        target = f"{self._pool_name}/{self._dataset_prefix}"
        if dataset:
            target = f"{self._pool_name}/{dataset}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "zfs", "list", "-t", "snapshot", "-o", "name", "-H",
                target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode().strip().split("\n")
            return []
        except FileNotFoundError:
            return []

    async def destroy_snapshot(self, snapshot: str) -> None:
        """Destroy a ZFS snapshot."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "zfs", "destroy", snapshot,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("ZFS destroy snapshot failed: %s", stderr.decode())
        except FileNotFoundError:
            logger.warning("zfs command not found — destroy skipped")

    async def replicate(
        self,
        snapshot: str,
        target_pool: str,
        compressed: bool = True,
    ) -> bool:
        """Replicate a ZFS snapshot to a target pool with optional compression.

        Uses `zfs send | zfs recv` with zstd compression for efficient replication.
        """
        try:
            # zfs send -R (replication stream) | zstd | zfs recv
            send_cmd = ["zfs", "send", "-R", snapshot]
            recv_cmd = ["zfs", "recv", f"{target_pool}/{self._dataset_prefix}"]

            send_proc = await asyncio.create_subprocess_exec(
                *send_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if compressed:
                # Pipe through zstd for compression
                zstd_proc = await asyncio.create_subprocess_exec(
                    "zstd", "-T0",  # multi-threaded zstd
                    stdin=send_proc.stdout,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                recv_proc = await asyncio.create_subprocess_exec(
                    *recv_cmd,
                    stdin=zstd_proc.stdout,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                recv_proc = await asyncio.create_subprocess_exec(
                    *recv_cmd,
                    stdin=send_proc.stdout,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            _, stderr = await recv_proc.communicate()
            if recv_proc.returncode != 0:
                logger.error("ZFS replication failed: %s", stderr.decode())
                return False
            logger.info("ZFS replication complete: %s → %s", snapshot, target_pool)
            return True
        except FileNotFoundError:
            logger.warning("zfs command not found — replication skipped")
            return False


# ---------------------------------------------------------------------------
# MinIO Storage Provider (Local S3-Compatible)
# ---------------------------------------------------------------------------

class MinIOStorageProvider(SmartStorageProvider):
    """MinIO local S3-compatible storage provider.

    Features:
    - S3-compatible API (dropbox for local object storage)
    - Bucket lifecycle policies
    - Versioning support
    - Erasure coding for data durability
    - Self-hosted, zero-cost

    Requires MinIO server running (typically on port 9000).
    Falls back gracefully if MinIO is not available.
    """

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "tranc3",
        secure: bool = False,
    ):
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._client = None
        self._tier_value = StorageTier.MINIO

    @property
    def tier(self) -> StorageTier:
        return self._tier_value

    @property
    def name(self) -> str:
        return f"MinIO({self._endpoint}/{self._bucket})"

    def _get_client(self):
        """Lazy-initialize MinIO client."""
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
            # Ensure bucket exists
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("MinIO bucket created: %s", self._bucket)
            return self._client
        except ImportError:
            logger.warning("minio package not installed — MinIO provider unavailable")
            return None
        except Exception as e:
            logger.warning("MinIO connection failed: %s", e)
            return None

    async def read(self, path: str) -> bytes:
        client = self._get_client()
        if client is None:
            raise RuntimeError("MinIO client not available")
        try:
            response = await asyncio.to_thread(
                client.get_object, self._bucket, path
            )
            data = await asyncio.to_thread(response.read)
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            raise FileNotFoundError(f"MinIO read failed: {path}: {e}")

    async def write(self, path: str, data: bytes) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("MinIO client not available")
        from io import BytesIO
        await asyncio.to_thread(
            client.put_object,
            self._bucket,
            path,
            BytesIO(data),
            len(data),
        )

    async def delete(self, path: str) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("MinIO client not available")
        await asyncio.to_thread(
            client.remove_object, self._bucket, path
        )

    async def list(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        if client is None:
            return []
        objects = await asyncio.to_thread(
            client.list_objects, self._bucket, prefix=prefix, recursive=True
        )
        return [obj.object_name for obj in objects]

    async def exists(self, path: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            await asyncio.to_thread(
                client.stat_object, self._bucket, path
            )
            return True
        except Exception:
            return False

    async def get_capacity(self) -> TierCapacity:
        """MinIO capacity — approximate from local disk usage."""
        cap = TierCapacity(tier=StorageTier.MINIO)
        client = self._get_client()
        if client is None:
            cap.is_available = False
            cap.last_checked = time.time()
            return cap
        try:
            # Use local disk stats as approximation
            data_dir = os.getenv("MINIO_DATA_DIR", "/mnt/data/minio")
            stat = await asyncio.to_thread(shutil.disk_usage, data_dir)
            cap.total_bytes = stat.total
            cap.used_bytes = stat.used
            cap.free_bytes = stat.free
            cap.is_available = True
            cap.last_checked = time.time()
        except Exception as e:
            logger.warning("MinIO capacity check failed: %s", e)
            cap.is_available = False
            cap.last_checked = time.time()
        return cap

    async def health(self) -> Dict[str, Any]:
        cap = await self.get_capacity()
        return {
            "provider": self.name,
            "tier": self.tier.name,
            "status": "healthy" if cap.is_available else "unavailable",
            "capacity": cap.to_dict(),
            "endpoint": self._endpoint,
            "bucket": self._bucket,
        }

    async def set_lifecycle_policy(
        self,
        prefix: str,
        expiry_days: int = 90,
        transition_days: Optional[int] = None,
    ) -> None:
        """Set a lifecycle policy for objects with the given prefix.

        Implements automatic expiry and transition rules:
        - expiry_days: Delete objects after this many days
        - transition_days: Move to cheaper storage after this many days (if supported)
        """
        client = self._get_client()
        if client is None:
            logger.warning("MinIO client not available — lifecycle policy skipped")
            return

        # MinIO supports ILM (Information Lifecycle Management)
        # Using the minio-py API for lifecycle configuration
        try:
            from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration, Filter

            config = LifecycleConfig(
                [
                    Rule(
                        rule_id=f"tranc3-lifecycle-{prefix.strip('/')}",
                        status="Enabled",
                        filter=Filter(prefix=prefix),
                        expiration=Expiration(days=expiry_days),
                    )
                ]
            )
            await asyncio.to_thread(
                client.set_bucket_lifecycle, self._bucket, config
            )
            logger.info(
                "MinIO lifecycle policy set: prefix=%s, expiry=%dd",
                prefix, expiry_days,
            )
        except ImportError:
            logger.warning("minio lifecycleconfig not available — policy skipped")
        except Exception as e:
            logger.warning("MinIO lifecycle policy failed: %s", e)


# ---------------------------------------------------------------------------
# Ceph Distributed Storage Provider
# ---------------------------------------------------------------------------

class CephStorageProvider(SmartStorageProvider):
    """Ceph distributed storage provider.

    Features:
    - Distributed object storage via RADOS Gateway (S3-compatible)
    - Erasure coding for storage efficiency
    - Replication factor for durability
    - Self-healing and self-managing
    - Self-hosted, zero-cost

    Requires Ceph cluster with RADOS Gateway (RGW) running.
    Falls back gracefully if Ceph is not available.
    """

    def __init__(
        self,
        endpoint: str = "localhost:7480",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "tranc3",
        secure: bool = False,
    ):
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._client = None
        self._tier_value = StorageTier.CEPH

    @property
    def tier(self) -> StorageTier:
        return self._tier_value

    @property
    def name(self) -> str:
        return f"Ceph({self._endpoint}/{self._bucket})"

    def _get_client(self):
        """Lazy-initialize Ceph RADOS client. Uses S3-compatible API via RGW."""
        if self._client is not None:
            return self._client
        try:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if self._secure else 'http'}://{self._endpoint}",
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name="default",
            )
            # Ensure bucket exists
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except Exception:
                self._client.create_bucket(Bucket=self._bucket)
                logger.info("Ceph bucket created: %s", self._bucket)
            return self._client
        except ImportError:
            logger.warning("boto3 package not installed — Ceph provider unavailable")
            return None
        except Exception as e:
            logger.warning("Ceph connection failed: %s", e)
            return None

    async def read(self, path: str) -> bytes:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Ceph client not available")
        try:
            response = await asyncio.to_thread(
                client.get_object, Bucket=self._bucket, Key=path
            )
            return await asyncio.to_thread(response["Body"].read)
        except Exception as e:
            raise FileNotFoundError(f"Ceph read failed: {path}: {e}")

    async def write(self, path: str, data: bytes) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Ceph client not available")
        await asyncio.to_thread(
            client.put_object,
            Bucket=self._bucket,
            Key=path,
            Body=data,
        )

    async def delete(self, path: str) -> None:
        client = self._get_client()
        if client is None:
            raise RuntimeError("Ceph client not available")
        await asyncio.to_thread(
            client.delete_object, Bucket=self._bucket, Key=path
        )

    async def list(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        if client is None:
            return []
        response = await asyncio.to_thread(
            client.list_objects_v2, Bucket=self._bucket, Prefix=prefix
        )
        return [obj["Key"] for obj in response.get("Contents", [])]

    async def exists(self, path: str) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            await asyncio.to_thread(
                client.head_object, Bucket=self._bucket, Key=path
            )
            return True
        except Exception:
            return False

    async def get_capacity(self) -> TierCapacity:
        """Ceph capacity — from cluster stats."""
        cap = TierCapacity(tier=StorageTier.CEPH)
        client = self._get_client()
        if client is None:
            cap.is_available = False
            cap.last_checked = time.time()
            return cap
        try:
            # Ceph provides cluster stats via the admin API
            # For now, use a reasonable default estimate
            cap.total_bytes = 100 * (1024**3)  # 100 GB estimate
            cap.used_bytes = 0  # Would need ceph df to get actual
            cap.free_bytes = cap.total_bytes
            cap.is_available = True
            cap.last_checked = time.time()
        except Exception as e:
            logger.warning("Ceph capacity check failed: %s", e)
            cap.is_available = False
            cap.last_checked = time.time()
        return cap

    async def health(self) -> Dict[str, Any]:
        cap = await self.get_capacity()
        return {
            "provider": self.name,
            "tier": self.tier.name,
            "status": "healthy" if cap.is_available else "unavailable",
            "capacity": cap.to_dict(),
            "endpoint": self._endpoint,
            "bucket": self._bucket,
        }



# ---------------------------------------------------------------------------
# OCI Object Storage Provider (Smart adapter)
# ---------------------------------------------------------------------------

class OCISmartProvider(SmartStorageProvider):
    """OCI Object Storage provider adapted for SmartStorageOrchestrator.

    Wraps the existing OCIObjectStorageProvider from oci_storage.py
    and adds the SmartStorageProvider interface (capacity monitoring, tier).
    OCI Always-Free tier: 10 GB Object Storage + 10 TB outbound/month.
    """

    def __init__(self):
        from shared_core.architecture.oci_storage import OCIObjectStorageProvider
        self._oci = OCIObjectStorageProvider()

    @property
    def tier(self) -> StorageTier:
        return StorageTier.OCI

    @property
    def name(self) -> str:
        return "OCI Object Storage"

    async def read(self, path: str) -> bytes:
        return await self._oci.read(path)

    async def write(self, path: str, data: bytes) -> None:
        await self._oci.write(path, data)

    async def delete(self, path: str) -> None:
        await self._oci.delete(path)

    async def list(self, prefix: str = "") -> List[str]:
        return await self._oci.list(prefix)

    async def exists(self, path: str) -> bool:
        return await self._oci.exists(path)

    async def get_capacity(self) -> TierCapacity:
        """OCI free tier: 10 GB Object Storage."""
        now = time.time()
        try:
            health = await self._oci.health()
            if health.get("status") != "healthy":
                return TierCapacity(
                    tier=StorageTier.OCI,
                    is_available=False,
                    last_checked=now,
                )
            # OCI doesn't expose simple capacity via the health endpoint;
            # return nominal free-tier capacity
            free_tier_bytes = 10 * 1024 ** 3  # 10 GB
            return TierCapacity(
                tier=StorageTier.OCI,
                is_available=True,
                total_bytes=free_tier_bytes,
                used_bytes=0,  # Actual usage requires list+sum
                usage_pct=0.0,
                is_critical=False,
                last_checked=now,
            )
        except Exception as e:
            logger.warning("OCI capacity check failed: %s", e)
            return TierCapacity(
                tier=StorageTier.OCI,
                is_available=False,
                last_checked=now,
            )

    async def health(self) -> Dict[str, Any]:
        return await self._oci.health()


# ---------------------------------------------------------------------------
# Smart Storage Orchestrator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cloudflare R2 Storage Provider (S3-compatible, free tier)
# ---------------------------------------------------------------------------

class CloudflareR2Provider(SmartStorageProvider):
    """Cloudflare R2 storage provider — S3-compatible, zero egress fees.

    Free tier: 10 GB storage, 10M class A ops, 1M class B ops/month.
    Implements the SmartStorageProvider interface for use with
    SmartStorageOrchestrator in CLOUD_ONLY and HYBRID modes.
    """

    def __init__(
        self,
        account_id: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "tranc3",
        endpoint_url: str = "",
    ):
        self._account_id = account_id or os.getenv("R2_ACCOUNT_ID", "")
        self._access_key = access_key or os.getenv("R2_ACCESS_KEY_ID", "")
        self._secret_key = secret_key or os.getenv("R2_SECRET_ACCESS_KEY", "")
        self._bucket = bucket
        self._endpoint_url = endpoint_url or f"https://{self._account_id}.r2.cloudflarestorage.com"
        self._client = None

    @property
    def tier(self) -> StorageTier:
        return StorageTier.R2

    @property
    def name(self) -> str:
        return "Cloudflare R2"

    def _get_client(self):
        """Lazy-initialize the S3 client for R2."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    "s3",
                    endpoint_url=self._endpoint_url,
                    aws_access_key_id=self._access_key,
                    aws_secret_access_key=self._secret_key,
                    region_name="auto",
                )
            except ImportError:
                raise RuntimeError(
                    "boto3 is required for R2 storage. Install: pip install boto3"
                )
        return self._client

    async def read(self, path: str) -> bytes:
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self._bucket, Key=path)
            return response["Body"].read()
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"R2 path not found: {path}")
            raise

    async def write(self, path: str, data: bytes) -> None:
        client = self._get_client()
        client.put_object(Bucket=self._bucket, Key=path, Body=data)
        logger.debug("Wrote %d bytes to R2://%s/%s", len(data), self._bucket, path)

    async def delete(self, path: str) -> None:
        client = self._get_client()
        try:
            client.delete_object(Bucket=self._bucket, Key=path)
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                raise FileNotFoundError(f"R2 path not found: {path}")
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

    async def get_capacity(self) -> TierCapacity:
        """R2 free tier: 10 GB storage."""
        now = time.time()
        try:
            # R2 doesn't expose capacity via API; estimate from object listing
            client = self._get_client()
            total_bytes = 0
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket):
                for obj in page.get("Contents", []):
                    total_bytes += obj.get("Size", 0)

            free_tier_gb = 10.0
            used_gb = total_bytes / (1024 ** 3)
            usage_pct = min(used_gb / free_tier_gb, 1.0)

            return TierCapacity(
                tier=StorageTier.R2,
                is_available=True,
                total_bytes=int(free_tier_gb * 1024 ** 3),
                used_bytes=total_bytes,
                usage_pct=usage_pct,
                is_critical=usage_pct > 0.95,
                last_checked=now,
            )
        except Exception as e:
            logger.warning("R2 capacity check failed: %s", e)
            return TierCapacity(
                tier=StorageTier.R2,
                is_available=False,
                last_checked=now,
            )

    async def health(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._bucket)
            cap = await self.get_capacity()
            return {
                "status": "healthy",
                "provider": self.name,
                "tier": self.tier.name,
                "bucket": self._bucket,
                "capacity_used_pct": f"{cap.usage_pct * 100:.1f}%",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.name,
                "tier": self.tier.name,
                "error": str(e),
            }


class SmartStorageOrchestrator:
    """Intelligent storage orchestrator that manages multiple providers.

    Features:
    - Environment-aware provider selection (SYSTEM_MODE)
    - Proactive capacity monitoring and tier migration
    - Zero-cost enforcement: auto-migrates before free-tier limits
    - Health-based failover between providers
    - Data locality awareness for optimal performance

    The orchestrator maintains a priority-ordered list of providers for
    each SYSTEM_MODE and automatically selects the best available provider
    for each operation. When a provider approaches its capacity limit,
    the orchestrator proactively migrates data to the next available tier.
    """

    def __init__(
        self,
        system_mode: Optional[SystemMode] = None,
        zfs_provider: Optional[ZFSStorageProvider] = None,
        minio_provider: Optional[MinIOStorageProvider] = None,
        ceph_provider: Optional[CephStorageProvider] = None,
        r2_provider: Optional[SmartStorageProvider] = None,
        oci_provider: Optional[SmartStorageProvider] = None,
    ):
        self._mode = system_mode or self._detect_mode()
        self._providers: Dict[StorageTier, SmartStorageProvider] = {}
        self._capacity_cache: Dict[StorageTier, TierCapacity] = {}
        self._last_capacity_check: float = 0.0
        self._capacity_check_interval: float = 60.0  # seconds

        # Register providers
        if zfs_provider:
            self._providers[StorageTier.ZFS] = zfs_provider
        if minio_provider:
            self._providers[StorageTier.MINIO] = minio_provider
        if ceph_provider:
            self._providers[StorageTier.CEPH] = ceph_provider
        if r2_provider:
            self._providers[StorageTier.R2] = r2_provider
        if oci_provider:
            self._providers[StorageTier.OCI] = oci_provider

    @staticmethod
    def _detect_mode() -> SystemMode:
        """Detect SYSTEM_MODE from environment."""
        raw = os.getenv("SYSTEM_MODE", "TRUE_NAS").upper()
        try:
            return SystemMode(raw)
        except ValueError:
            return SystemMode.TRUE_NAS

    def _get_priority_order(self) -> List[StorageTier]:
        """Get the provider priority order for the current SYSTEM_MODE."""
        if self._mode == SystemMode.TRUE_NAS:
            return [StorageTier.ZFS, StorageTier.MINIO, StorageTier.CEPH]
        elif self._mode == SystemMode.HYBRID:
            return [StorageTier.ZFS, StorageTier.MINIO, StorageTier.CEPH, StorageTier.R2, StorageTier.OCI]
        else:  # CLOUD_ONLY
            return [StorageTier.R2, StorageTier.OCI]

    async def _select_provider(
        self,
        preferred_tier: Optional[StorageTier] = None,
    ) -> Tuple[SmartStorageProvider, StorageTier]:
        """Select the best available storage provider.

        Priority:
        1. Preferred tier if specified and available
        2. Highest-priority tier that is available and not critical
        3. Any available tier (fallback)
        """
        order = self._get_priority_order()

        # If preferred tier specified, try it first
        if preferred_tier and preferred_tier in self._providers:
            cap = await self._get_tier_capacity(preferred_tier)
            if cap.is_available and not cap.is_critical:
                return self._providers[preferred_tier], preferred_tier

        # Try providers in priority order
        for tier in order:
            if tier not in self._providers:
                continue
            cap = await self._get_tier_capacity(tier)
            if cap.is_available and not cap.is_critical:
                return self._providers[tier], tier

        # Fallback: any available provider
        for tier in order:
            if tier not in self._providers:
                continue
            cap = await self._get_tier_capacity(tier)
            if cap.is_available:
                return self._providers[tier], tier

        raise RuntimeError("No storage providers available")

    async def _get_tier_capacity(self, tier: StorageTier) -> TierCapacity:
        """Get capacity for a tier, using cache if recent."""
        now = time.time()
        cached = self._capacity_cache.get(tier)
        if cached and (now - cached.last_checked) < self._capacity_check_interval:
            return cached

        provider = self._providers.get(tier)
        if provider is None:
            cap = TierCapacity(tier=tier, is_available=False, last_checked=now)
            self._capacity_cache[tier] = cap
            return cap

        cap = await provider.get_capacity()
        self._capacity_cache[tier] = cap
        return cap

    async def _check_and_migrate(self) -> None:
        """Proactive zero-cost enforcement: migrate data if a tier is critical.

        When any provider reaches critical capacity (>95%), automatically
        migrates its coldest data to the next available tier. This ensures
        the zero-cost mandate is maintained — no tier ever exceeds its
        free-tier limit.
        """
        order = self._get_priority_order()

        for i, tier in enumerate(order):
            if tier not in self._providers:
                continue

            cap = await self._get_tier_capacity(tier)
            if not cap.is_critical:
                continue

            # Find next available tier to migrate to
            target_tier = None
            for j in range(i + 1, len(order)):
                if order[j] in self._providers:
                    target_cap = await self._get_tier_capacity(order[j])
                    if target_cap.is_available and not target_cap.is_critical:
                        target_tier = order[j]
                        break

            if target_tier is None:
                logger.error(
                    "CRITICAL: Tier %s at %.1f%% capacity and no migration target available!",
                    tier.name, cap.usage_pct * 100,
                )
                continue

            logger.warning(
                "PROACTIVE MIGRATION: Tier %s at %.1f%% — migrating cold data to %s",
                tier.name, cap.usage_pct * 100, target_tier.name,
            )
            await self._migrate_cold_data(tier, target_tier)

    async def _migrate_cold_data(
        self,
        source_tier: StorageTier,
        target_tier: StorageTier,
        max_objects: int = 100,
    ) -> int:
        """Migrate cold (oldest/least-accessed) data between tiers."""
        source = self._providers[source_tier]
        target = self._providers[target_tier]

        migrated = 0
        try:
            objects = await source.list()
            # Sort by path (approximate age proxy — older objects typically have earlier timestamps in path)
            objects.sort()

            for obj_path in objects[:max_objects]:
                try:
                    data = await source.read(obj_path)
                    await target.write(obj_path, data)
                    await source.delete(obj_path)
                    migrated += 1
                except Exception as e:
                    logger.warning("Migration failed for %s: %s", obj_path, e)
                    break
        except Exception as e:
            logger.error("Cold data migration error: %s", e)

        logger.info("Migrated %d objects from %s to %s", migrated, source_tier.name, target_tier.name)
        return migrated

    # --- Public API (delegates to selected provider) ---

    async def read(self, path: str) -> bytes:
        """Read data, trying all providers in priority order.

        If the selected provider doesn't have the data, we try ALL other
        providers (not just lower-priority ones), because data may exist on
        any tier due to capacity-aware migration or previous writes when a
        higher-priority provider was unavailable.
        """
        provider, tier = await self._select_provider()
        try:
            return await provider.read(path)
        except FileNotFoundError:
            # Try ALL other providers in priority order
            order = self._get_priority_order()
            for alt_tier in order:
                if alt_tier == tier:
                    continue  # Already tried
                if alt_tier in self._providers:
                    try:
                        return await self._providers[alt_tier].read(path)
                    except FileNotFoundError:
                        continue
                    except Exception as e:
                        logger.warning("Read failed on %s for %s: %s", alt_tier.name, path, e)
                        continue
            raise

    async def write(self, path: str, data: bytes) -> None:
        """Write data to the highest-priority available provider."""
        await self._check_and_migrate()
        provider, tier = await self._select_provider()
        await provider.write(path, data)

    async def delete(self, path: str) -> None:
        """Delete data from all providers where it exists."""
        order = self._get_priority_order()
        for tier in order:
            if tier in self._providers:
                try:
                    if await self._providers[tier].exists(path):
                        await self._providers[tier].delete(path)
                except Exception as e:
                    logger.warning("Delete failed on %s for %s: %s", tier.name, path, e)

    async def list(self, prefix: str = "") -> List[str]:
        """List objects across all providers (deduplicated)."""
        all_objects = set()
        order = self._get_priority_order()
        for tier in order:
            if tier in self._providers:
                try:
                    objs = await self._providers[tier].list(prefix)
                    all_objects.update(objs)
                except Exception as e:
                    logger.warning("List failed on %s: %s", tier.name, e)
        return sorted(all_objects)

    async def exists(self, path: str) -> bool:
        """Check if data exists in any provider."""
        order = self._get_priority_order()
        for tier in order:
            if tier in self._providers:
                try:
                    if await self._providers[tier].exists(path):
                        return True
                except Exception:
                    continue
        return False

    async def health(self) -> Dict[str, Any]:
        """Return comprehensive health status across all providers."""
        tier_healths = {}
        order = self._get_priority_order()
        for tier in order:
            if tier in self._providers:
                try:
                    tier_healths[tier.name] = await self._providers[tier].health()
                except Exception as e:
                    tier_healths[tier.name] = {"status": "error", "error": str(e)}

        return {
            "orchestrator": "SmartStorageOrchestrator",
            "system_mode": self._mode.value,
            "priority_order": [t.name for t in order],
            "tiers": tier_healths,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    async def get_capacity_report(self) -> Dict[str, Any]:
        """Get capacity report for all tiers."""
        report = {}
        for tier in self._get_priority_order():
            cap = await self._get_tier_capacity(tier)
            report[tier.name] = cap.to_dict()
        return report


# ---------------------------------------------------------------------------
# Factory function for easy initialization
# ---------------------------------------------------------------------------

def create_smart_storage(
    system_mode: Optional[str] = None,
    **kwargs,
) -> SmartStorageOrchestrator:
    """Create a SmartStorageOrchestrator with sensible defaults.

    Args:
        system_mode: Override SYSTEM_MODE ("TRUE_NAS", "HYBRID", "CLOUD_ONLY")
        **kwargs: Override any provider configuration
    """
    mode = None
    if system_mode:
        try:
            mode = SystemMode(system_mode.upper())
        except ValueError:
            logger.warning("Invalid SYSTEM_MODE '%s'; defaulting to TRUE_NAS", system_mode)
            mode = SystemMode.TRUE_NAS

    # Create providers based on environment
    zfs_provider = None
    minio_provider = None
    ceph_provider = None

    if mode != SystemMode.CLOUD_ONLY:
        # Local providers only available in TRUE_NAS or HYBRID mode
        zfs_provider = ZFSStorageProvider(
            pool_name=kwargs.get("zfs_pool", os.getenv("ZFS_POOL", "tank")),
            dataset_prefix=kwargs.get("zfs_dataset", "tranc3"),
            mount_root=kwargs.get("zfs_mount", os.getenv("ZFS_MOUNT_ROOT")),
        )
        minio_provider = MinIOStorageProvider(
            endpoint=kwargs.get("minio_endpoint", os.getenv("MINIO_ENDPOINT", "localhost:9000")),
            access_key=kwargs.get("minio_access_key", os.getenv("MINIO_ACCESS_KEY", "minioadmin")),
            secret_key=kwargs.get("minio_secret_key", os.getenv("MINIO_SECRET_KEY", "minioadmin")),
            bucket=kwargs.get("minio_bucket", os.getenv("MINIO_BUCKET", "tranc3")),
        )

    # Ceph available in all modes if configured
    ceph_endpoint = kwargs.get("ceph_endpoint", os.getenv("CEPH_ENDPOINT", ""))
    if ceph_endpoint:
        ceph_provider = CephStorageProvider(
            endpoint=ceph_endpoint,
            access_key=kwargs.get("ceph_access_key", os.getenv("CEPH_ACCESS_KEY", "")),
            secret_key=kwargs.get("ceph_secret_key", os.getenv("CEPH_SECRET_KEY", "")),
            bucket=kwargs.get("ceph_bucket", os.getenv("CEPH_BUCKET", "tranc3")),
        )

    # Cloud providers (R2/OCI) — available in HYBRID and CLOUD_ONLY modes
    r2_provider = None
    oci_provider = None

    r2_account_id = kwargs.get("r2_account_id", os.getenv("R2_ACCOUNT_ID", ""))
    r2_access_key = kwargs.get("r2_access_key", os.getenv("R2_ACCESS_KEY_ID", ""))
    r2_secret_key = kwargs.get("r2_secret_key", os.getenv("R2_SECRET_ACCESS_KEY", ""))
    oci_compartment = kwargs.get("oci_compartment", os.getenv("OCI_COMPARTMENT_ID", ""))

    if r2_account_id and r2_access_key and r2_secret_key:
        r2_provider = CloudflareR2Provider(
            account_id=r2_account_id,
            access_key=r2_access_key,
            secret_key=r2_secret_key,
            bucket=kwargs.get("r2_bucket", os.getenv("R2_BUCKET_NAME", "tranc3")),
        )

    if oci_compartment:
        try:
            oci_provider = OCISmartProvider()
        except ImportError:
            logger.warning("OCI provider not available — install oci-sdk")

    if mode == SystemMode.CLOUD_ONLY and not r2_provider and not oci_provider:
        logger.warning(
            "CLOUD_ONLY mode but no cloud providers configured! "
            "Set R2_ACCOUNT_ID or OCI_COMPARTMENT_ID environment variables."
        )

    return SmartStorageOrchestrator(
        system_mode=mode,
        zfs_provider=zfs_provider,
        minio_provider=minio_provider,
        ceph_provider=ceph_provider,
        r2_provider=r2_provider,
        oci_provider=oci_provider,
    )
