# tests/conftest.py
# Shared test fixtures and configuration.
# Sets required environment variables before any test module is imported,
# so that src.core.config (which creates a singleton at import time) doesn't fail.

import os

# These must be set BEFORE any test module imports src.core.config,
# which instantiates Tranc3Config() at module level and requires both.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-0000001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-00001")
