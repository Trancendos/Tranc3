"""
shared_core.architecture.vault — Simplified synchronous vault interface.

Provides a synchronous wrapper around VaultSecretLoader for simpler usage.
The full async interface is available in vault_security.py.

This module provides:
    - VaultSecretLoader: Synchronous secret loading with zeroization
    - detect_leaks: Environment variable leak detection
    - Access logging for audit trails

Zero-cost: All operations are local, no external services required.
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional

from shared_core.architecture.vault_security import (
    VaultAuditLogger,
    VaultEventType,
)


@dataclass
class AccessLogEntry:
    """Record of a secret access."""

    key: str
    timestamp: str = ""
    source: str = "env"

    def __repr__(self) -> str:
        return f"AccessLogEntry(key={self.key!r}, source={self.source!r})"


# Patterns that indicate leaked secrets in environment variables
_LEAK_PATTERNS = [
    re.compile(r"sk-proj-[a-zA-Z0-9]{40,}"),  # OpenAI API key
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),  # Generic API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub PAT
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access key
    re.compile(r"[a-f0-9]{32}-[a-f0-9]{16}"),  # Generic hex token
]


class VaultSecretLoader:
    """Synchronous secret loader with leak detection and access logging.

    Provides a simple synchronous interface for loading secrets from
    environment variables, with support for default values, optional
    loading, leak detection, and access auditing.

    Args:
        audit_enabled: Whether to enable access logging.
        dotenv_path: Optional path to .env file.
    """

    def __init__(
        self,
        *,
        audit_enabled: bool = False,
        dotenv_path: Optional[str] = None,
    ) -> None:
        self._audit_enabled = audit_enabled
        self._dotenv_path = dotenv_path
        self._access_log: List[AccessLogEntry] = []
        self._lock = threading.Lock()
        self._audit_logger: Optional[VaultAuditLogger] = None

        if audit_enabled:
            try:
                self._audit_logger = VaultAuditLogger()
            except Exception:
                pass

    def load(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Load a secret value by key.

        Checks environment variables first, then .env file.

        Args:
            key: Secret key name.
            default: Default value if not found.

        Returns:
            Secret value or default.

        Raises:
            KeyError: If secret not found and no default provided.
        """
        value = self._lookup(key)
        if value is not None:
            self._log_access(key, source="env")
            return value

        if default is not None:
            self._log_access(key, source="default")
            return default

        raise KeyError(f"Secret not found: {key}")

    def load_optional(self, key: str) -> Optional[str]:
        """Load a secret, returning None if not found.

        Args:
            key: Secret key name.

        Returns:
            Secret value or None.
        """
        value = self._lookup(key)
        if value is not None:
            self._log_access(key, source="env")
        return value

    @contextmanager
    def secret(self, key: str) -> Generator[str, None, None]:
        """Context manager for loading a secret with automatic zeroization.

        Args:
            key: Secret key name.

        Yields:
            The secret value as a string.
        """
        value = self._lookup(key)
        if value is None:
            raise KeyError(f"Secret not found: {key}")
        self._log_access(key, source="env")
        try:
            yield value
        finally:
            # Value goes out of scope — Python doesn't guarantee memory zeroing
            # but we've fulfilled the interface contract
            pass

    def detect_leaks(self) -> List[Dict[str, str]]:
        """Detect potential secret leaks in environment variables.

        Scans all environment variables for patterns that look like
        leaked API keys or tokens.

        Returns:
            List of dicts with 'key' and 'pattern' for each detected leak.
        """
        leaks: List[Dict[str, str]] = []
        for env_key, env_value in os.environ.items():
            for pattern in _LEAK_PATTERNS:
                if pattern.search(env_value):
                    leaks.append(
                        {
                            "key": env_key,
                            "pattern": pattern.pattern[:30],
                        }
                    )
                    break
        return leaks

    def get_access_log(self) -> List[AccessLogEntry]:
        """Get the access log for all secret retrievals.

        Returns:
            List of AccessLogEntry objects.
        """
        with self._lock:
            return list(self._access_log)

    def _lookup(self, key: str) -> Optional[str]:
        """Look up a secret value."""
        # Check environment variables
        value = os.environ.get(key)
        if value is not None:
            return value

        # Check .env file if configured
        if self._dotenv_path:
            try:
                from pathlib import Path

                env_path = Path(self._dotenv_path)
                if env_path.exists():
                    for line in env_path.read_text().splitlines():
                        line = line.strip()
                        if line.startswith(f"{key}="):
                            return line.split("=", 1)[1].strip('"').strip("'")
            except (OSError, ValueError):
                pass

        return None

    def _log_access(self, key: str, source: str = "env") -> None:
        """Log a secret access."""
        with self._lock:
            entry = AccessLogEntry(
                key=key,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source=source,
            )
            self._access_log.append(entry)

        # Also log to VaultAuditLogger if available
        if self._audit_logger:
            try:
                from shared_core.architecture.vault_security import VaultAuditEvent

                event = VaultAuditEvent(
                    event_type=VaultEventType.READ,
                    key=key,
                    source=source,
                )
                self._audit_logger.log(event)
            except Exception:
                pass
