# shared_core/architecture/oci_storage.py — Oracle Cloud Infrastructure Object Storage Provider
# Zero-Cost Mandate: OCI Always-Free tier includes 10GB Object Storage + 10TB outbound/month
#
# Features:
#   - S3-compatible interface via OCI's standard SDK
#   - Lazy client initialization (only loads when actually needed)
#   - Automatic namespace resolution
#   - Full StorageProvider interface compliance
#   - Graceful fallback when OCI credentials are not configured

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared_core.architecture.storage_factory import StorageProvider, SystemMode
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class OCIObjectStorageProvider(StorageProvider):
    """Oracle Cloud Infrastructure Object Storage provider.

    OCI Always-Free Tier includes:
    - 10 GB Object Storage (standard)
    - 10 TB outbound data transfer/month
    - 2 Autonomous Database instances
    - 2 AMD Compute VMs (1/8 OCPU + 1GB RAM each)

    This provider uses the OCI Python SDK (oci package) to interact
    with Object Storage. The SDK is lazily imported — if not installed,
    clear error messages guide the user.

    Required environment variables:
        OCI_CONFIG_FILE: Path to OCI config file (default: ~/.oci/config)
        OCI_COMPARTMENT_ID: OCI compartment OCID
        OCI_BUCKET_NAME: Object storage bucket name
        OCI_NAMESPACE: OCI Object Storage namespace (auto-detected if not set)
    """

    def __init__(self):
        self._mode = SystemMode.CLOUD_ONLY
        self._compartment_id = os.getenv("OCI_COMPARTMENT_ID", "")
        self._bucket_name = os.getenv("OCI_BUCKET_NAME", "tranc3-data")
        self._namespace = os.getenv("OCI_NAMESPACE", "")
        self._client = None
        self._config = None

    def _get_client(self):
        """Lazy-initialize the OCI Object Storage client."""
        if self._client is not None:
            return self._client

        try:
            import oci
        except ImportError:
            raise RuntimeError(
                "oci package is required for OCI Object Storage. "
                "Install it with: pip install oci"
            )

        # Load OCI config
        config_file = os.getenv("OCI_CONFIG_FILE", os.path.expanduser("~/.oci/config"))
        if os.path.exists(config_file):
            self._config = oci.config.from_file(config_file)
        else:
            # Try instance principal auth (when running on OCI compute)
            logger.info("No OCI config file found, attempting instance principal auth")
            try:
                signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
                self._config = {"region": os.getenv("OCI_REGION", "us-ashburn-1")}
                self._client = oci.object_storage.ObjectStorageClient(
                    config=self._config, signer=signer
                )
            except Exception:
                raise RuntimeError(
                    "OCI authentication failed. Either provide a config file at "
                    f"{config_file} or run on an OCI compute instance with "
                    "instance principals enabled."
                )
            return self._client

        self._client = oci.object_storage.ObjectStorageClient(self._config)

        # Auto-detect namespace if not set
        if not self._namespace:
            try:
                namespace = self._client.get_namespace().data
                self._namespace = namespace
                logger.info("OCI namespace auto-detected: %s", namespace)
            except Exception as e:
                logger.warning("Could not auto-detect OCI namespace: %s", e)

        return self._client

    async def read(self, path: str) -> bytes:
        client = self._get_client()
        try:
            response = client.get_object(
                namespace_name=self._namespace,
                bucket_name=self._bucket_name,
                object_name=path,
            )
            return response.data.content.read()
        except Exception as e:
            error_str = str(e)
            if "ObjectNotFound" in error_str or "404" in error_str:
                raise FileNotFoundError(f"Storage path not found: {path}")
            raise

    async def write(self, path: str, data: bytes) -> None:
        client = self._get_client()
        import io
        client.put_object(
            namespace_name=self._namespace,
            bucket_name=self._bucket_name,
            object_name=path,
            put_object_body=io.BytesIO(data),
            content_length=len(data),
        )
        logger.debug("Wrote %d bytes to OCI://%s/%s", len(data), self._bucket_name, sanitize_for_log(path))

    async def delete(self, path: str) -> None:
        client = self._get_client()
        try:
            client.delete_object(
                namespace_name=self._namespace,
                bucket_name=self._bucket_name,
                object_name=path,
            )
        except Exception as e:
            if "ObjectNotFound" in str(e):
                raise FileNotFoundError(f"Storage path not found: {path}")
            raise

    async def list(self, prefix: str = "") -> List[str]:
        client = self._get_client()
        results: List[str] = []
        try:
            response = client.list_objects(
                namespace_name=self._namespace,
                bucket_name=self._bucket_name,
                prefix=prefix if prefix else None,
            )
            for obj in response.data.objects:
                results.append(obj.name)
        except Exception as e:
            logger.error("OCI list failed: %s", sanitize_for_log(str(e)))
        return sorted(results)

    async def exists(self, path: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(
                namespace_name=self._namespace,
                bucket_name=self._bucket_name,
                object_name=path,
            )
            return True
        except Exception:
            return False

    async def health(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            client.get_bucket(
                namespace_name=self._namespace,
                bucket_name=self._bucket_name,
            )
            return {
                "status": "healthy",
                "mode": self._mode.value,
                "bucket": self._bucket_name,
                "namespace": self._namespace,
                "provider": "oci-object-storage",
                "free_tier": "10GB storage + 10TB outbound/month",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "mode": self._mode.value,
                "bucket": self._bucket_name,
                "namespace": self._namespace,
                "provider": "oci-object-storage",
                "error": str(e),
            }
