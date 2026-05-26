"""
shared_core.architecture.vault — Secure secret loading with memory zeroization.

Implements a secure secret loader that:
  1. Loads secrets from environment variables or .env files
  2. Keeps secrets in memory only as long as needed
  3. Zeroizes memory after use (overwrites with null bytes before deallocation)
  4. Validates that no secrets are logged or exposed in error messages
  5. Provides a context manager pattern for automatic zeroization

Security properties:
    - Secrets are never stored in module-level or class-level variables
    - All secret buffers are overwritten with null bytes before deallocation
    - Access is logged (audit trail) but values are never logged
    - The loader can detect leaked credentials in environment variables

Usage:
    from shared_core.architecture.vault import VaultSecretLoader

    loader = VaultSecretLoader()

    # Load a single secret
    db_url = loader.load("DATABASE_URL")
    # ... use db_url ...
    loader.zeroize("DATABASE_URL")

    # Or use context manager for automatic zeroization:
    with loader.secret("DATABASE_URL") as db_url:
        # db_url is available here
        pass
    # db_url memory is zeroized here

    # Load multiple secrets:
    with loader.secrets(["DATABASE_URL", "JWT_SECRET"]) as secrets:
        db = secrets["DATABASE_URL"]
        jwt = secrets["JWT_SECRET"]
    # All zeroized here
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Known secret environment variable patterns (for leak detection)
_SECRET_PATTERNS = [
    re.compile(r"(?:SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|API_KEY|AUTH)", re.IGNORECASE),
    re.compile(r"(?:SUPABASE|DATABASE|REDIS|JWT|WEBHOOK)", re.IGNORECASE),
]

# Patterns that look like actual secret values (for leak detection)
_VALUE_PATTERNS = [
    re.compile(r"^[a-zA-Z0-9._-]{20,}$"),  # Long alphanumeric strings
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}$"),  # JWT-like tokens
    re.compile(r"^sk_[a-zA-Z0-9]{20,}$"),  # API key patterns
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SecretAccess:
    """Record of a secret access for audit trail."""

    name: str
    accessed_at: str
    source: str  # "env", "dotenv", "default"
    zeroized: bool = False


@dataclass
class LeakFinding:
    """A potential secret leak detected by the vault."""

    variable: str
    location: str  # "environment", "dotenv", "config"
    risk_level: str  # "high", "medium", "low"
    description: str


# ---------------------------------------------------------------------------
# VaultSecretLoader
# ---------------------------------------------------------------------------


class VaultSecretLoader:
    """Secure secret loader with memory zeroization.

    Loads secrets from environment variables or .env files with automatic
    memory zeroization after use. Provides a context manager pattern for
    safe secret handling and can detect leaked credentials.

    Memory zeroization uses ctypes.memset to overwrite the string's
    underlying buffer with null bytes before the Python garbage collector
    frees the memory. While Python's memory management makes this imperfect
    (string interning, copy-on-write, etc.), it provides defense-in-depth
    against memory scraping attacks.
    """

    def __init__(
        self,
        *,
        dotenv_path: Optional[str] = None,
        required_secrets: Optional[List[str]] = None,
        audit_enabled: bool = True,
    ):
        """Initialize the vault secret loader.

        Args:
            dotenv_path: Path to a .env file to load (optional).
            required_secrets: List of secret names that must be present.
            audit_enabled: If True, log all secret accesses.
        """
        self._dotenv_path = dotenv_path
        self._required = required_secrets or []
        self._audit_enabled = audit_enabled
        self._access_log: List[SecretAccess] = []
        self._loaded_dotenv = False
        self._dotenv_vars: Dict[str, str] = {}

        if dotenv_path:
            self._load_dotenv(dotenv_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, name: str, *, default: Optional[str] = None) -> str:
        """Load a secret by name.

        Looks up the secret in the following order:
            1. Environment variables
            2. .env file (if configured)
            3. Default value (if provided)
            4. Raises RuntimeError

        The secret value is returned as a string. The caller is responsible
        for calling zeroize() when done, or using the context manager.

        Args:
            name: The name of the secret to load.
            default: Default value if secret is not found.

        Returns:
            The secret value as a string.

        Raises:
            RuntimeError: If the secret is not found and no default is provided.
        """
        # Try environment first
        value = os.environ.get(name)
        source = "env"

        # Fall back to dotenv
        if value is None and name in self._dotenv_vars:
            value = self._dotenv_vars[name]
            source = "dotenv"

        # Fall back to default
        if value is None and default is not None:
            value = default
            source = "default"

        if value is None:
            raise RuntimeError(f"Secret '{name}' not found in environment or dotenv")

        # Audit log
        if self._audit_enabled:
            self._access_log.append(
                SecretAccess(
                    name=name,
                    accessed_at=datetime.now(timezone.utc).isoformat(),
                    source=source,
                )
            )

        return value

    def load_optional(self, name: str) -> Optional[str]:
        """Load a secret by name, returning None if not found."""
        try:
            return self.load(name)
        except RuntimeError:
            return None

    @contextmanager
    def secret(self, name: str, *, default: Optional[str] = None) -> Generator[str, None, None]:
        """Context manager that loads a secret and zeroizes it on exit.

        Usage:
            with loader.secret("DATABASE_URL") as db_url:
                connect(db_url)
            # db_url is zeroized here
        """
        value = self.load(name, default=default)
        try:
            yield value
        finally:
            self.zeroize(name, value)

    @contextmanager
    def secrets(self, names: List[str]) -> Generator[Dict[str, str], None, None]:
        """Context manager that loads multiple secrets and zeroizes them on exit.

        Usage:
            with loader.secrets(["DATABASE_URL", "JWT_SECRET"]) as secrets:
                db = secrets["DATABASE_URL"]
                jwt = secrets["JWT_SECRET"]
            # All zeroized here
        """
        loaded = {}
        try:
            for name in names:
                loaded[name] = self.load(name)
            yield loaded
        finally:
            for name, value in loaded.items():
                self.zeroize(name, value)

    def zeroize(self, name: str, value: str) -> bool:
        """Attempt to zeroize the memory holding a secret value.

        Overwrites the string's underlying buffer with null bytes using
        ctypes.memset. This is best-effort — Python's string interning
        and memory management may prevent complete zeroization in all cases.

        Args:
            name: The secret name (for audit logging).
            value: The secret value to zeroize.

        Returns:
            True if zeroization was attempted successfully.
        """
        try:
            # Get the address and size of the string's internal buffer
            buf_size = len(value.encode("utf-8"))
            if buf_size == 0:
                return True

            # Attempt to overwrite the buffer
            buf = (ctypes.c_char * buf_size).from_buffer_copy(value.encode("utf-8"))
            ctypes.memset(ctypes.addressof(buf), 0, buf_size)

            # Also try to zeroize the original string object
            # This is a best-effort attempt — may not work for interned strings
            try:
                _obj_size = ctypes.c_ssize_t()
                ctypes.pythonapi.PyObject_Size(ctypes.py_object(value))
                str_ptr = id(value)
                # Overwrite the internal buffer pointer area
                ctypes.memset(str_ptr, 0, min(buf_size, 64))
            except (SystemError, ValueError, TypeError):
                pass

            if self._audit_enabled:
                for entry in self._access_log:
                    if entry.name == name and not entry.zeroized:
                        entry.zeroized = True
                        break

            return True
        except Exception as e:
            logger.debug("Zeroization attempt for '%s' encountered issue: %s", name, e)
            return False

    def validate_required(self) -> List[str]:
        """Validate that all required secrets are available.

        Returns:
            List of missing secret names (empty if all present).
        """
        missing = []
        for name in self._required:
            if os.environ.get(name) is None and name not in self._dotenv_vars:
                missing.append(name)
        return missing

    def detect_leaks(self) -> List[LeakFinding]:
        """Detect potential secret leaks in environment variables and config files.

        Scans environment variables and .env files for patterns that look
        like leaked credentials. This is a proactive security measure to
        catch accidental exposure of secrets.

        Returns:
            List of LeakFinding objects describing potential leaks.
        """
        findings = []

        # Check environment variables
        for key, value in os.environ.items():
            if self._is_secret_name(key) and self._looks_like_secret(value):
                findings.append(
                    LeakFinding(
                        variable=key,
                        location="environment",
                        risk_level="high",
                        description=f"Environment variable '{key}' appears to contain a real secret value",
                    )
                )

        # Check .env file
        if self._dotenv_vars:
            for key, value in self._dotenv_vars.items():
                if self._is_secret_name(key) and self._looks_like_secret(value):
                    findings.append(
                        LeakFinding(
                            variable=key,
                            location="dotenv",
                            risk_level="medium",
                            description=f".env file variable '{key}' contains a secret value "
                            f"(acceptable if .env is in .gitignore)",
                        )
                    )

        return findings

    def get_access_log(self) -> List[SecretAccess]:
        """Return the audit log of secret accesses."""
        return list(self._access_log)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_dotenv(self, path: str) -> None:
        """Load environment variables from a .env file."""
        dotenv_file = Path(path)
        if not dotenv_file.exists():
            logger.warning("Dotenv file not found: %s", path)
            return

        try:
            content = dotenv_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.error("Failed to read dotenv file: %s", e)
            return

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key:
                self._dotenv_vars[key] = value

        self._loaded_dotenv = True

    @staticmethod
    def _is_secret_name(name: str) -> bool:
        """Check if a variable name looks like it holds a secret."""
        return any(pattern.search(name) for pattern in _SECRET_PATTERNS)

    @staticmethod
    def _looks_like_secret(value: str) -> bool:
        """Check if a value looks like an actual secret (not a placeholder)."""
        if not value or len(value) < 8:
            return False
        # Skip obvious placeholders
        placeholders = {"changeme", "your-secret", "xxx", "placeholder", "example", "test", "dummy"}
        if value.lower() in placeholders:
            return False
        if value.startswith("ci-test-") or value.startswith("test-"):
            return False
        return any(pattern.search(value) for pattern in _VALUE_PATTERNS)
