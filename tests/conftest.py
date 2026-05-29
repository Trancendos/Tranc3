# tests/conftest.py
# Shared test fixtures and configuration.
# Sets required environment variables before any test module is imported,
# so that src.core.config (which creates a singleton at import time) doesn't fail.

import os

# These must be set BEFORE any test module imports src.core.config,
# which instantiates Tranc3Config() at module level and requires both.
# Use `or` fallback so CI-injected empty strings are replaced safely.
for _var, _default in (
    ("SECRET_KEY", "test-secret-key-for-unit-tests-0000001"),
    ("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001"),
    ("DATABASE_URL", "sqlite:///./test.db"),
    ("REDIS_URL", "redis://localhost:6379/0"),
):
    os.environ[_var] = os.environ.get(_var) or _default
