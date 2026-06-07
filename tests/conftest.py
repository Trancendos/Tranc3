# tests/conftest.py
# Shared test fixtures and configuration.
# Sets required environment variables before any test module is imported,
# so that src.core.config (which creates a singleton at import time) doesn't fail.

import os
import tempfile
from pathlib import Path

# These must be set BEFORE any test module imports src.core.config,
# which instantiates Tranc3Config() at module level and requires both.
# Use `or` fallback so CI-injected empty strings are replaced safely.
for _var, _default in (
    ("SECRET_KEY", "test-secret-key-for-unit-tests-0000001"),
    ("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001"),
    ("DATABASE_URL", "sqlite:///./test.db"),
    ("REDIS_URL", "redis://localhost:6379/0"),
    ("MASTER_KEY_SEED", "test-master-key-seed-for-unit-tests-0001"),
    ("INTERNAL_SECRET", "test-internal-secret-for-unit-tests-001"),
    ("ENVIRONMENT", "test"),
):
    os.environ[_var] = os.environ.get(_var) or _default

# Workers and storage modules default to /data/* or /mnt/data/* at import time.
_worker_test_data = Path(tempfile.mkdtemp(prefix="tranc3-worker-test-"))
os.environ.setdefault("AUTH_DATABASE_PATH", str(_worker_test_data / "auth.db"))
os.environ.setdefault("USERS_DATABASE_PATH", str(_worker_test_data / "users.db"))
os.environ.setdefault("STORAGE_ROOT", str(_worker_test_data / "storage"))
os.environ.setdefault("MINIO_DATA_DIR", str(_worker_test_data / "minio"))
