"""storage-service — configuration"""

from __future__ import annotations

import os
import warnings

WORKER_NAME = "storage-service"
WORKER_PORT = int(os.environ.get("STORAGE_PORT", "8020"))
DB_PATH = os.environ.get("STORAGE_DB_PATH", "/data/storage.db")
LOCAL_ROOT = os.environ.get("STORAGE_LOCAL_ROOT", "/data/objects")

# ── Backends (zero-cost, priority order) ──────────────────────────────────────
# 1. Local filesystem (always available, unlimited)
LOCAL_ENABLED = True

# 2. MinIO — self-hosted S3 (MIT, in docker-compose)
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_DEFAULT_BUCKET", "trancendos")
MINIO_ENABLED = os.environ.get("STORAGE_MINIO", "1") == "1"

# 3. IPFS — distributed content-addressed (in docker-compose)
IPFS_API = os.environ.get("IPFS_API_URL", "http://ipfs:5001")
IPFS_GATEWAY = os.environ.get("IPFS_GATEWAY_URL", "http://ipfs:8080")
IPFS_ENABLED = os.environ.get("STORAGE_IPFS", "1") == "1"

# 4. Valkey — Redis-fork blob store (in docker-compose)
VALKEY_URL = os.environ.get("VALKEY_URL", "redis://valkey:6379/0")
VALKEY_ENABLED = os.environ.get("STORAGE_VALKEY", "1") == "1"
VALKEY_MAX_OBJECT_BYTES = int(os.environ.get("STORAGE_VALKEY_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB

# 5. SeaweedFS — self-hosted distributed (Apache 2.0, optional)
SEAWEEDFS_MASTER = os.environ.get("SEAWEEDFS_MASTER", "http://seaweedfs-master:9333")
SEAWEEDFS_ENABLED = os.environ.get("STORAGE_SEAWEEDFS", "0") == "1"

# 6. Garage — self-hosted S3-compatible (AGPL, optional)
GARAGE_ENDPOINT = os.environ.get("GARAGE_ENDPOINT", "http://garage:3900")
GARAGE_ACCESS_KEY = os.environ.get("GARAGE_ACCESS_KEY", "")
GARAGE_SECRET_KEY = os.environ.get("GARAGE_SECRET_KEY", "")
GARAGE_ENABLED = os.environ.get("STORAGE_GARAGE", "0") == "1"

# 7. DuckDB blob table — in-process analytics + blob (always available)
DUCKDB_PATH = os.environ.get("STORAGE_DUCKDB_PATH", "/data/storage.duckdb")
DUCKDB_ENABLED = os.environ.get("STORAGE_DUCKDB", "1") == "1"

# 8. Offline stub (always available — never blocks)
# Always enabled as final fallback

# ── ACO / ThresholdGuard ──────────────────────────────────────────────────────
PHEROMONE_DECAY = float(os.environ.get("STORAGE_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW_SECONDS = int(os.environ.get("STORAGE_QUOTA_WINDOW", "3600"))
QUOTA_MAX_CALLS = int(os.environ.get("STORAGE_QUOTA_MAX_CALLS", "50000"))
PROBE_TIMEOUT = float(os.environ.get("STORAGE_PROBE_TIMEOUT", "3.0"))
OP_TIMEOUT = float(os.environ.get("STORAGE_OP_TIMEOUT", "30.0"))

# ── Internal auth ─────────────────────────────────────────────────────────────
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
if not INTERNAL_SECRET:
    warnings.warn("INTERNAL_SECRET not set — inter-service auth disabled", stacklevel=1)

TLS_VERIFY = os.environ.get("STORAGE_TLS_VERIFY", "0") != "0"
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
