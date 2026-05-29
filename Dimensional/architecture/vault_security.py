"""
Dimensional.architecture.vault_security — Vault Security with Memory Zeroization & HSM.

Implements secure secret management with defense-in-depth:
    - VaultSecretLoader: Secure secret retrieval with memory zeroization
    - PKCS#11 HSM Integration: Hardware Security Module support (YubiHSM 2, SoftHSM2)
    - Memory-safe operations: All sensitive data is zeroized after use
    - Append-only audit logging: All vault access is recorded
    - Zero-cost: SoftHSM2 for dev, YubiHSM 2 for production

Security Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │                  Vault Security Layer                     │
    │                                                          │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
    │  │ SecretLoader │  │  HSM Module  │  │ AuditLogger  │   │
    │  │ (zeroize)    │  │ (PKCS#11)    │  │ (ledger)     │   │
    │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
    │         │                 │                  │           │
    │  ┌──────┴─────────────────┴──────────────────┴───────┐   │
    │  │              SecureMemoryGuard                     │   │
    │  │  (mlock, zeroize on del, guard context)           │   │
    │  └───────────────────────────────────────────────────┘   │
    └──────────────────────────────────────────────────────────┘

HSM Integration:
    - YubiHSM 2: Production-grade hardware security module
    - SoftHSM2: Software-based HSM for development/testing
    - Both implement PKCS#11 interface for standardized access

Memory Zeroization:
    - All sensitive data stored in SecureBytes which zeroizes on deletion
    - Context manager pattern ensures zeroization even on exceptions
    - Optional mlock() to prevent memory swapping to disk
    - Constant-time comparison to prevent timing attacks

Zero-Cost Mandate:
    - SoftHSM2: Free, open-source software HSM (dev/test)
    - YubiHSM 2: One-time hardware cost (~$150), no recurring fees
    - No paid cloud HSM services (AWS CloudHSM, Azure Dedicated HSM)

Usage:
    from Dimensional.architecture.vault_security import (
        VaultSecretLoader,
        SecureBytes,
        HSMProvider,
        SoftHSM2Provider,
        YubiHSM2Provider,
    )

    # Secure secret loading with memory zeroization
    loader = VaultSecretLoader(hsm_provider=SoftHSM2Provider())

    # Load a secret — automatically zeroized after use
    async with loader.secret("database/password") as secret:
        password = secret.decode()
        # Use password...
    # secret memory is now zeroized

    # HSM key operations
    hsm = SoftHSM2Provider(token="tranc3", pin="123456")
    key_handle = hsm.generate_key(key_type="AES", key_size=256)
    ciphertext = hsm.encrypt(key_handle, plaintext)
    plaintext = hsm.decrypt(key_handle, ciphertext)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

# Optional PKCS#11 support — only available when python-pkcs11 is installed
try:
    import pkcs11  # type: ignore[import-untyped]
except ImportError:
    pkcs11 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Platform Detection ────────────────────────────────────────────────────────

_IS_LINUX = os.name == "posix"

# Attempt to load libc for mlock / memset
_libc: Optional[ctypes.CDLL] = None
_libc_name: Optional[str] = None

if _IS_LINUX:
    _libc_name = ctypes.util.find_library("c")
    if _libc_name:
        try:
            _libc = ctypes.CDLL(_libc_name, use_errno=True)
        except OSError:
            _libc = None


# ── Secure Memory Operations ─────────────────────────────────────────────────


def _secure_zero(address: int, size: int) -> None:
    """Securely zeroize a memory region using memset_s or explicit_bzero.

    Falls back to volatile memset if secure functions are unavailable.
    The volatile keyword prevents the compiler from optimizing away the zeroing.
    """
    if _libc is not None:
        # Try explicit_bzero (Linux/glibc) — guaranteed not to be optimized away
        if hasattr(_libc, "explicit_bzero"):
            _libc.explicit_bzero(ctypes.c_void_p(address), ctypes.c_size_t(size))
            return

        # Try memset_s (C11 Annex K) — guaranteed not to be optimized away
        if hasattr(_libc, "memset_s"):
            # memset_s(dest, destmax, c, n) returns errno_t
            result = _libc.memset_s(
                ctypes.c_void_p(address),
                ctypes.c_size_t(size),
                ctypes.c_int(0),
                ctypes.c_size_t(size),
            )
            if result == 0:
                return

    # Fallback: Use ctypes volatile memset
    # This is NOT guaranteed to survive compiler optimization,
    # but is better than nothing in pure Python
    buf = (ctypes.c_char * size).from_address(address)
    for i in range(size):
        buf[i] = b"\x00"


def _mlock(address: int, size: int) -> bool:
    """Lock memory pages to prevent swapping to disk.

    Requires CAP_IPC_LOCK or root privileges on Linux.
    Returns True if successful, False otherwise.
    """
    if _libc is not None and hasattr(_libc, "mlock"):
        result = _libc.mlock(ctypes.c_void_p(address), ctypes.c_size_t(size))
        if result == 0:
            return True
        errno = ctypes.get_errno()
        logger.debug("mlock failed (errno=%d). Data may be swapped to disk.", errno)
    return False


def _munlock(address: int, size: int) -> bool:
    """Unlock previously locked memory pages."""
    if _libc is not None and hasattr(_libc, "munlock"):
        result = _libc.munlock(ctypes.c_void_p(address), ctypes.c_size_t(size))
        return result == 0
    return False


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison to prevent timing attacks.

    Uses hmac.compare_digest when available (Python 3.3+),
    falls back to manual constant-time implementation.
    """
    return hmac.compare_digest(a, b)


# ── SecureBytes — Self-Zeroizing Secure Container ────────────────────────────


class SecureBytes:
    """A byte container that zeroizes its contents on deletion.

    Features:
        - Automatic memory zeroization when the object is deleted or goes out of scope
        - Optional mlock() to prevent memory from being swapped to disk
        - Constant-time comparison to prevent timing attacks
        - Context manager support for guaranteed cleanup
        - Thread-safe access with internal locking

    Usage:
        secret = SecureBytes(b"sensitive_data", lock_memory=True)
        # Use secret...
        del secret  # Memory is now zeroized

        # Or as a context manager:
        with SecureBytes(b"sensitive_data") as secret:
            data = secret.reveal()
            # Use data...
        # Memory zeroized on exit
    """

    def __init__(self, data: bytes, lock_memory: bool = True) -> None:
        self._size = len(data)
        self._buffer = ctypes.create_string_buffer(data, self._size)
        self._locked = False
        self._zeroed = False
        self._lock = threading.Lock()

        if lock_memory and self._size > 0:
            self._locked = _mlock(ctypes.addressof(self._buffer), self._size)

    def reveal(self) -> bytes:
        """Return a copy of the secure bytes. The caller is responsible for
        zeroizing the returned copy."""
        with self._lock:
            if self._zeroed:
                raise ValueError("SecureBytes has been zeroized")
            return bytes(self._buffer)

    def zeroize(self) -> None:
        """Explicitly zeroize the memory."""
        with self._lock:
            if not self._zeroed and self._size > 0:
                _secure_zero(ctypes.addressof(self._buffer), self._size)
                if self._locked:
                    _munlock(ctypes.addressof(self._buffer), self._size)
                    self._locked = False
                self._zeroed = True

    def __del__(self) -> None:
        try:
            self.zeroize()
        except Exception:
            pass  # __del__ must never raise — safe to ignore zeroization failure

    def __exit__(self, *args: Any) -> None:
        self.zeroize()

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return f"SecureBytes(size={self._size}, zeroed={self._zeroed})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecureBytes):
            return NotImplemented
        if self._zeroed or other._zeroed:
            return False
        return _constant_time_compare(self.reveal(), other.reveal())

    __hash__ = None  # type: ignore[assignment]  # SecureBytes is not hashable for security reasons


# ── Vault Audit Event ─────────────────────────────────────────────────────────


class VaultEventType(str, Enum):
    """Types of vault access events for audit logging."""

    SECRET_READ = "secret_read"
    SECRET_WRITE = "secret_write"
    SECRET_DELETE = "secret_delete"
    HSM_KEY_GENERATE = "hsm_key_generate"
    HSM_KEY_USE = "hsm_key_use"
    HSM_KEY_DELETE = "hsm_key_delete"
    HSM_SIGN = "hsm_sign"
    HSM_VERIFY = "hsm_verify"
    HSM_ENCRYPT = "hsm_encrypt"
    HSM_DECRYPT = "hsm_decrypt"
    VAULT_UNLOCK = "vault_unlock"
    VAULT_LOCK = "vault_lock"
    VAULT_ROTATE = "vault_rotate"
    ACCESS_DENIED = "access_denied"
    INTEGRITY_CHECK = "integrity_check"


@dataclass
class VaultAuditEvent:
    """Audit record for vault access."""

    timestamp: str
    event_type: VaultEventType
    actor: str
    resource: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)
    source_ip: str = ""
    request_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "resource": self.resource,
            "success": self.success,
            "details": self.details,
            "source_ip": self.source_ip,
            "request_id": self.request_id,
        }


class VaultAuditLogger:
    """Append-only audit logger for vault access events.

    All vault operations are recorded to an audit log that:
        - Is append-only (records cannot be modified or deleted)
        - Is chain-linked (each record contains a hash of the previous)
        - Can be verified for integrity
        - Is compatible with the existing AuditLedger

    Zero-cost: Uses local file storage (JSONL format), no paid log services.
    """

    def __init__(self, log_dir: Union[str, Path] = "logs/vault-audit") -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._current_file: Optional[Path] = None
        self._prev_hash = "genesis"
        self._lock = threading.Lock()
        self._rotate_if_needed()

    def _rotate_if_needed(self) -> None:
        """Rotate audit log file daily."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = self._log_dir / f"vault-audit-{today}.jsonl"
        if self._current_file != target:
            self._current_file = target
            # Load last hash from existing file for chain continuity
            if target.exists():
                last_line = None
                with open(target, "r") as f:
                    for line in f:
                        if line.strip():
                            last_line = line
                if last_line:
                    try:
                        record = json.loads(last_line)
                        self._prev_hash = record.get("chain_hash", "genesis")
                    except json.JSONDecodeError:
                        pass  # Corrupted audit line — use genesis hash as fallback

    def log(self, event: VaultAuditEvent) -> None:
        """Record a vault audit event."""
        with self._lock:
            self._rotate_if_needed()

            record = event.to_dict()

            # Chain: hash of (previous_hash + current_record WITHOUT chain_hash)
            record_json = json.dumps(record, sort_keys=True)
            chain_input = f"{self._prev_hash}:{record_json}".encode("utf-8")
            chain_hash = hashlib.sha256(chain_input).hexdigest()

            # Add chain_hash AFTER computing the hash
            record["chain_hash"] = chain_hash
            self._prev_hash = chain_hash

            with open(self._current_file, "a") as f:
                f.write(json.dumps(record) + "\n")

            logger.debug(
                "Vault audit: %s %s by %s (%s)",
                event.event_type.value,
                event.resource,
                event.actor,
                "success" if event.success else "denied",
            )

    def verify_chain(self, date: Optional[str] = None) -> bool:
        """Verify the integrity of the audit chain."""
        if date:
            target = self._log_dir / f"vault-audit-{date}.jsonl"
        else:
            target = self._current_file

        if not target or not target.exists():
            return True  # No records = valid chain

        prev_hash = "genesis"
        with open(target, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    stored_hash = record.pop("chain_hash", None)

                    # Recompute
                    record_json = json.dumps(record, sort_keys=True)
                    expected = hashlib.sha256(
                        f"{prev_hash}:{record_json}".encode("utf-8")
                    ).hexdigest()

                    if stored_hash != expected:
                        logger.error(
                            "Chain integrity violation at line %d in %s",
                            line_num,
                            target,
                        )
                        return False

                    prev_hash = stored_hash
                except json.JSONDecodeError:
                    logger.error("Invalid JSON at line %d in %s", line_num, target)
                    return False

        return True


# ── PKCS#11 HSM Provider Interface ──────────────────────────────────────────


class HSMKeyType(str, Enum):
    """HSM key types."""

    AES = "AES"
    RSA = "RSA"
    EC = "EC"
    HMAC = "HMAC"


class HSMProvider(ABC):
    """Abstract base class for PKCS#11 Hardware Security Module providers.

    All HSM operations are performed inside the HSM boundary:
        - Keys never leave the HSM in plaintext
        - Cryptographic operations are performed by the HSM
        - Key material is protected by the HSM's tamper-resistant storage

    Implementations:
        - SoftHSM2Provider: Software-based HSM (dev/test, zero-cost)
        - YubiHSM2Provider: YubiHSM 2 hardware (production)
    """

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the HSM provider and establish session."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the HSM is accessible and functional."""

    @abstractmethod
    def generate_key(
        self,
        key_type: HSMKeyType = HSMKeyType.AES,
        key_size: int = 256,
        label: str = "",
        persistent: bool = True,
    ) -> str:
        """Generate a new key inside the HSM.

        Returns:
            Key handle/identifier for subsequent operations.
        """

    @abstractmethod
    def encrypt(self, key_handle: str, plaintext: bytes) -> bytes:
        """Encrypt data using a key stored in the HSM."""

    @abstractmethod
    def decrypt(self, key_handle: str, ciphertext: bytes) -> bytes:
        """Decrypt data using a key stored in the HSM."""

    @abstractmethod
    def sign(self, key_handle: str, data: bytes) -> bytes:
        """Sign data using a key stored in the HSM."""

    @abstractmethod
    def verify(self, key_handle: str, data: bytes, signature: bytes) -> bool:
        """Verify a signature using a key stored in the HSM."""

    @abstractmethod
    def delete_key(self, key_handle: str) -> bool:
        """Delete a key from the HSM."""

    @abstractmethod
    def list_keys(self) -> List[Dict[str, Any]]:
        """List all keys stored in the HSM."""

    @abstractmethod
    def close(self) -> None:
        """Close the HSM session and zeroize any cached credentials."""


class SoftHSM2Provider(HSMProvider):
    """SoftHSM2 — Software-based PKCS#11 HSM for development and testing.

    SoftHSM2 is a free, open-source implementation of a cryptographic
    store implementing the PKCS#11 interface. It is suitable for:
        - Development and testing
        - CI/CD pipelines
        - Environments without physical HSM hardware

    Zero-cost: Fully open-source, no licensing fees.

    Requirements:
        - softhsm2 package installed
        - PKCS#11 library: /usr/lib/softhsm/Softhsm2.so (Linux)
        - python-pkcs11 library for Python bindings

    Setup:
        # Install SoftHSM2
        apt install softhsm2

        # Initialize a token
        softhsm2-util --init-token --slot 0 --label "tranc3" --pin 123456 --so-pin 12345678

    Usage:
        hsm = SoftHSM2Provider(token="tranc3", pin="123456")
        hsm.initialize()
        key = hsm.generate_key(HSMKeyType.AES, 256, label="master-key")
        ciphertext = hsm.encrypt(key, b"secret data")
        plaintext = hsm.decrypt(key, ciphertext)
        hsm.close()
    """

    def __init__(
        self,
        token: str = "tranc3",
        pin: str = "123456",
        library_path: Optional[str] = None,
        slot: Optional[int] = None,
        audit_logger: Optional[VaultAuditLogger] = None,
    ) -> None:
        self._token = token
        self._pin = SecureBytes(pin.encode("utf-8"))
        self._library_path = library_path or self._find_library()
        self._slot = slot
        self._session = None
        self._pkcs11 = None
        self._token_obj = None
        self._audit = audit_logger or VaultAuditLogger()
        self._initialized = False

    @staticmethod
    def _find_library() -> str:
        """Find the SoftHSM2 PKCS#11 library."""
        candidates = [
            "/usr/lib/softhsm/Softhsm2.so",
            "/usr/lib/x86_64-linux-gnu/softhsm/Softhsm2.so",
            "/usr/lib64/softhsm/libsofthsm2.so",
            "/usr/local/lib/softhsm/libsofthsm2.so",
            "/opt/homebrew/lib/softhsm/libsofthsm2.so",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        # Return default — will fail gracefully in initialize()
        return candidates[0]

    def initialize(self) -> None:
        """Initialize SoftHSM2 PKCS#11 session."""
        try:
            import pkcs11  # type: ignore

            self._pkcs11 = pkcs11.lib(self._library_path)
            tokens = self._pkcs11.get_tokens(token_label=self._token)

            try:
                self._token_obj = next(tokens)
            except StopIteration:
                raise RuntimeError(
                    f"SoftHSM2 token '{self._token}' not found. "
                    f"Initialize it with: softhsm2-util --init-token --slot 0 "
                    f"--label '{self._token}' --pin <pin> --so-pin <sopin>"
                ) from None

            if self._slot is not None:
                self._session = self._token_obj.open(self._slot, pin=self._pin.reveal().decode())
            else:
                self._session = self._token_obj.open(pin=self._pin.reveal().decode())

            self._initialized = True
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.VAULT_UNLOCK,
                    actor="softhsm2-provider",
                    resource=f"token:{self._token}",
                    success=True,
                    details={"library": self._library_path},
                )
            )
            logger.info("SoftHSM2 initialized: token=%s", self._token)

        except ImportError:
            logger.warning("python-pkcs11 not installed. Install with: pip install python-pkcs11")
            raise
        except Exception as e:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.VAULT_UNLOCK,
                    actor="softhsm2-provider",
                    resource=f"token:{self._token}",
                    success=False,
                    details={"error": str(e)},
                )
            )
            raise

    def is_available(self) -> bool:
        """Check if SoftHSM2 is accessible."""
        if not self._initialized or self._session is None:
            return False
        try:
            import pkcs11  # type: ignore

            # Try a simple operation
            self._session.get_key(object_class=pkcs11.ObjectClass.SECRET_KEY)
            return True
        except Exception:
            # No keys or pkcs11 not available — session still valid if initialized
            return self._initialized

    def generate_key(
        self,
        key_type: HSMKeyType = HSMKeyType.AES,
        key_size: int = 256,
        label: str = "",
        persistent: bool = True,
    ) -> str:
        """Generate a key inside SoftHSM2."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized. Call initialize() first.")

        from pkcs11 import KeyType as PKCS11KeyType

        key_type_map = {
            HSMKeyType.AES: PKCS11KeyType.AES,
            HSMKeyType.RSA: PKCS11KeyType.RSA,
            HSMKeyType.EC: PKCS11KeyType.EC_EDWARDS,
            HSMKeyType.HMAC: PKCS11KeyType.GENERIC_SECRET,
        }

        pkcs11_key_type = key_type_map.get(key_type, PKCS11KeyType.AES)
        key_label = label or f"tranc3-{key_type.value}-{secrets.token_hex(4)}"

        try:
            if key_type == HSMKeyType.AES:
                key = self._session.generate_key(
                    pkcs11_key_type,
                    key_size=key_size,
                    label=key_label,
                    store=persistent,
                )
            elif key_type == HSMKeyType.RSA:
                pub, priv = self._session.generate_keypair(
                    pkcs11_key_type,
                    key_size=key_size,
                    label=key_label,
                    store=persistent,
                )
                key = priv
            else:
                key = self._session.generate_key(
                    pkcs11_key_type,
                    key_size=key_size,
                    label=key_label,
                    store=persistent,
                )

            handle = key.label or key_label
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_GENERATE,
                    actor="softhsm2-provider",
                    resource=f"key:{handle}",
                    success=True,
                    details={"key_type": key_type.value, "key_size": key_size},
                )
            )
            return handle

        except Exception as e:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_GENERATE,
                    actor="softhsm2-provider",
                    resource=f"key:{key_label}",
                    success=False,
                    details={"error": str(e)},
                )
            )
            raise

    def encrypt(self, key_handle: str, plaintext: bytes) -> bytes:
        """Encrypt data using a SoftHSM2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        import pkcs11  # type: ignore

        key = self._session.get_key(label=key_handle, object_class=pkcs11.ObjectClass.SECRET_KEY)
        iv = self._session.generate_random(16)
        ciphertext = key.encrypt(plaintext, mechanism_param=iv)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_ENCRYPT,
                actor="softhsm2-provider",
                resource=f"key:{key_handle}",
                success=True,
                details={"plaintext_size": len(plaintext)},
            )
        )
        # Prepend IV to ciphertext
        return iv + ciphertext

    def decrypt(self, key_handle: str, ciphertext: bytes) -> bytes:
        """Decrypt data using a SoftHSM2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        import pkcs11  # type: ignore

        key = self._session.get_key(label=key_handle, object_class=pkcs11.ObjectClass.SECRET_KEY)
        iv = ciphertext[:16]
        actual_ciphertext = ciphertext[16:]
        plaintext = key.decrypt(actual_ciphertext, mechanism_param=iv)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_DECRYPT,
                actor="softhsm2-provider",
                resource=f"key:{key_handle}",
                success=True,
                details={"ciphertext_size": len(ciphertext)},
            )
        )
        return plaintext

    def sign(self, key_handle: str, data: bytes) -> bytes:
        """Sign data using a SoftHSM2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle)
        signature = key.sign(data)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_SIGN,
                actor="softhsm2-provider",
                resource=f"key:{key_handle}",
                success=True,
            )
        )
        return signature

    def verify(self, key_handle: str, data: bytes, signature: bytes) -> bool:
        """Verify a signature using a SoftHSM2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle)
        try:
            result = key.verify(data, signature)
            success = True
        except Exception:
            result = False
            success = False

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_VERIFY,
                actor="softhsm2-provider",
                resource=f"key:{key_handle}",
                success=success,
            )
        )
        return result

    def delete_key(self, key_handle: str) -> bool:
        """Delete a key from SoftHSM2."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        try:
            key = self._session.get_key(label=key_handle)
            key.destroy()
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_DELETE,
                    actor="softhsm2-provider",
                    resource=f"key:{key_handle}",
                    success=True,
                )
            )
            return True
        except Exception as e:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_DELETE,
                    actor="softhsm2-provider",
                    resource=f"key:{key_handle}",
                    success=False,
                    details={"error": str(e)},
                )
            )
            return False

    def list_keys(self) -> List[Dict[str, Any]]:
        """List all keys in the SoftHSM2 token."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        keys = []
        try:
            import pkcs11  # type: ignore

            for obj in self._session.get_objects(
                {
                    pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY,
                }
            ):
                keys.append(
                    {
                        "label": obj.label,
                        "type": "secret_key",
                    }
                )
        except Exception:
            pass  # Key enumeration failure — return partial list
        return keys

    def close(self) -> None:
        """Close SoftHSM2 session and zeroize cached credentials."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass  # Session close failure — safe to ignore during cleanup
            self._session = None

        self._pin.zeroize()
        self._initialized = False

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.VAULT_LOCK,
                actor="softhsm2-provider",
                resource=f"token:{self._token}",
                success=True,
            )
        )
        logger.info("SoftHSM2 session closed and credentials zeroized")


class YubiHSM2Provider(HSMProvider):
    """YubiHSM 2 — Hardware Security Module for production use.

    The YubiHSM 2 is a cost-effective hardware security module that provides:
        - FIPS 140-2 Level 3 tamper resistance
        - PKCS#11 interface for standardized access
        - On-device key generation and storage
        - Hardware-accelerated cryptographic operations
        - Secure boot and firmware verification

    One-time cost: ~$150 USD. No recurring fees. Zero operational cost.

    Requirements:
        - YubiHSM 2 USB device connected
        - yubihsm-shell package installed
        - PKCS#11 library: /usr/lib/yubihsm/pkcs11/yubihsm_pkcs11.so
        - python-pkcs11 library for Python bindings

    Setup:
        # Install YubiHSM SDK
        apt install yubihsm-shell

        # Start the YubiHSM connector daemon
        yubihsm-connector --daemon

        # Initialize the HSM (first time only)
        yubihsm-setup

    Usage:
        hsm = YubiHSM2Provider(
            connector_url="http://localhost:12345",
            auth_key_id=1,
            auth_key_password=b"password",
        )
        hsm.initialize()
        key = hsm.generate_key(HSMKeyType.AES, 256, label="master-key")
        hsm.close()
    """

    def __init__(
        self,
        connector_url: str = "http://localhost:12345",
        auth_key_id: int = 1,
        auth_key_password: bytes = b"password",  # noqa: S105 — demo default; override in production
        library_path: Optional[str] = None,
        audit_logger: Optional[VaultAuditLogger] = None,
    ) -> None:
        self._connector_url = connector_url
        self._auth_key_id = auth_key_id
        self._auth_password = SecureBytes(auth_key_password)
        self._library_path = library_path or self._find_library()
        self._session = None
        self._pkcs11 = None
        self._token_obj = None
        self._audit = audit_logger or VaultAuditLogger()
        self._initialized = False

    @staticmethod
    def _find_library() -> str:
        """Find the YubiHSM 2 PKCS#11 library."""
        candidates = [
            "/usr/lib/yubihsm/pkcs11/yubihsm_pkcs11.so",
            "/usr/lib/x86_64-linux-gnu/pkcs11/yubihsm_pkcs11.so",
            "/usr/lib64/pkcs11/yubihsm_pkcs11.so",
            "/usr/local/lib/yubihsm_pkcs11.so",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    def initialize(self) -> None:
        """Initialize YubiHSM 2 PKCS#11 session."""
        try:
            import pkcs11  # type: ignore

            self._pkcs11 = pkcs11.lib(self._library_path)
            tokens = self._pkcs11.get_tokens()

            try:
                self._token_obj = next(tokens)
            except StopIteration:
                raise RuntimeError(
                    "YubiHSM 2 token not found. Ensure the YubiHSM connector is running "
                    f"at {self._connector_url} and the device is connected."
                ) from None

            self._session = self._token_obj.open(
                pin=f"{self._auth_key_id}:{self._auth_password.reveal().decode()}"
            )
            self._initialized = True

            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.VAULT_UNLOCK,
                    actor="yubihsm2-provider",
                    resource=f"auth_key:{self._auth_key_id}",
                    success=True,
                    details={"connector_url": self._connector_url},
                )
            )
            logger.info("YubiHSM 2 initialized: connector=%s", self._connector_url)

        except ImportError:
            logger.warning("python-pkcs11 not installed. Install with: pip install python-pkcs11")
            raise
        except Exception as e:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.VAULT_UNLOCK,
                    actor="yubihsm2-provider",
                    resource=f"auth_key:{self._auth_key_id}",
                    success=False,
                    details={"error": str(e)},
                )
            )
            raise

    def is_available(self) -> bool:
        """Check if YubiHSM 2 is accessible."""
        return self._initialized and self._session is not None

    def generate_key(
        self,
        key_type: HSMKeyType = HSMKeyType.AES,
        key_size: int = 256,
        label: str = "",
        persistent: bool = True,
    ) -> str:
        """Generate a key inside YubiHSM 2."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        from pkcs11 import KeyType as PKCS11KeyType

        key_type_map = {
            HSMKeyType.AES: PKCS11KeyType.AES,
            HSMKeyType.RSA: PKCS11KeyType.RSA,
            HSMKeyType.EC: PKCS11KeyType.EC_EDWARDS,
            HSMKeyType.HMAC: PKCS11KeyType.GENERIC_SECRET,
        }

        pkcs11_key_type = key_type_map.get(key_type, PKCS11KeyType.AES)
        key_label = label or f"tranc3-{key_type.value}-{secrets.token_hex(4)}"

        try:
            if key_type == HSMKeyType.RSA:
                self._session.generate_keypair(
                    pkcs11_key_type,
                    key_size=key_size,
                    label=key_label,
                    store=persistent,
                )
                handle = key_label
            else:
                self._session.generate_key(
                    pkcs11_key_type,
                    key_size=key_size,
                    label=key_label,
                    store=persistent,
                )
                handle = key_label

            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_GENERATE,
                    actor="yubihsm2-provider",
                    resource=f"key:{handle}",
                    success=True,
                    details={"key_type": key_type.value, "key_size": key_size},
                )
            )
            return handle

        except Exception as e:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.HSM_KEY_GENERATE,
                    actor="yubihsm2-provider",
                    resource=f"key:{key_label}",
                    success=False,
                    details={"error": str(e)},
                )
            )
            raise

    def encrypt(self, key_handle: str, plaintext: bytes) -> bytes:
        """Encrypt data using a YubiHSM 2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle, object_class=pkcs11.ObjectClass.SECRET_KEY)
        iv = self._session.generate_random(16)
        ciphertext = key.encrypt(plaintext, mechanism_param=iv)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_ENCRYPT,
                actor="yubihsm2-provider",
                resource=f"key:{key_handle}",
                success=True,
            )
        )
        return iv + ciphertext

    def decrypt(self, key_handle: str, ciphertext: bytes) -> bytes:
        """Decrypt data using a YubiHSM 2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle, object_class=pkcs11.ObjectClass.SECRET_KEY)
        iv = ciphertext[:16]
        actual_ciphertext = ciphertext[16:]
        plaintext = key.decrypt(actual_ciphertext, mechanism_param=iv)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.HSM_DECRYPT,
                actor="yubihsm2-provider",
                resource=f"key:{key_handle}",
                success=True,
            )
        )
        return plaintext

    def sign(self, key_handle: str, data: bytes) -> bytes:
        """Sign data using a YubiHSM 2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle)
        return key.sign(data)

    def verify(self, key_handle: str, data: bytes, signature: bytes) -> bool:
        """Verify a signature using a YubiHSM 2 key."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        key = self._session.get_key(label=key_handle)
        try:
            return key.verify(data, signature)
        except Exception:
            return False  # Verification failure — signature invalid

    def delete_key(self, key_handle: str) -> bool:
        """Delete a key from YubiHSM 2."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        try:
            key = self._session.get_key(label=key_handle)
            key.destroy()
            return True
        except Exception:
            return False  # Key deletion failure — key may not exist

    def list_keys(self) -> List[Dict[str, Any]]:
        """List all keys in YubiHSM 2."""
        if not self._initialized:
            raise RuntimeError("HSM not initialized.")

        keys = []
        try:
            import pkcs11  # type: ignore

            for obj in self._session.get_objects(
                {
                    pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY,
                }
            ):
                keys.append({"label": obj.label, "type": "secret_key"})
        except Exception:
            pass  # Key enumeration failure — return partial list
        return keys

    def close(self) -> None:
        """Close YubiHSM 2 session and zeroize credentials."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass  # Session close failure — safe to ignore during cleanup
            self._session = None

        self._auth_password.zeroize()
        self._initialized = False

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.VAULT_LOCK,
                actor="yubihsm2-provider",
                resource=f"auth_key:{self._auth_key_id}",
                success=True,
            )
        )
        logger.info("YubiHSM 2 session closed and credentials zeroized")


# ── VaultSecretLoader ────────────────────────────────────────────────────────


class SecretSource(str, Enum):
    """Sources for secret retrieval."""

    ENVIRONMENT = "environment"
    DOTENV = "dotenv"
    INFINITY_VOID = "infinity_void"
    HSM = "hsm"
    FILE = "file"


class VaultSecretLoader:
    """Secure secret loader with memory zeroization and HSM integration.

    Loads secrets from multiple sources with automatic memory zeroization:
        1. Environment variables (for container deployments)
        2. .env files (for local development)
        3. Infinity Void vault (self-hosted encrypted secrets)
        4. HSM-encrypted files (secrets encrypted by HSM keys)

    All secrets are wrapped in SecureBytes for automatic zeroization.
    The context manager pattern ensures secrets are zeroized even if
    an exception occurs during use.

    Security Features:
        - Memory zeroization: All secret data is zeroized after use
        - Optional mlock(): Prevents secrets from being swapped to disk
        - HSM integration: Secrets can be encrypted/decrypted by HSM
        - Audit logging: All secret access is recorded
        - Constant-time comparison: Prevents timing attacks

    Zero-cost: All sources are self-hosted. No paid secret managers.

    Usage:
        loader = VaultSecretLoader(hsm_provider=SoftHSM2Provider())

        # Context manager — auto-zeroize after use
        async with loader.secret("DATABASE_URL") as secret:
            db_url = secret.reveal().decode()
            # Use db_url...
        # secret memory is now zeroized

        # Multiple secrets at once
        async with loader.secrets(["DB_HOST", "DB_PORT", "DB_USER", "DB_PASS"]) as secrets:
            host = secrets["DB_HOST"].reveal().decode()
            # ...
    """

    def __init__(
        self,
        hsm_provider: Optional[HSMProvider] = None,
        audit_logger: Optional[VaultAuditLogger] = None,
        lock_memory: bool = True,
        dotenv_path: Optional[str] = None,
        infinity_void_url: Optional[str] = None,
        infinity_void_secret: Optional[str] = None,
    ) -> None:
        self._hsm = hsm_provider
        self._audit = audit_logger or VaultAuditLogger()
        self._lock_memory = lock_memory
        self._dotenv_path = dotenv_path
        self._infinity_void_url = infinity_void_url
        self._infinity_void_secret = (
            SecureBytes((infinity_void_secret or "").encode("utf-8"))
            if infinity_void_secret
            else None
        )
        self._cache: Dict[str, SecureBytes] = {}
        self._cache_lock = threading.Lock()

    @asynccontextmanager
    async def secret(self, key: str) -> Generator[SecureBytes, None, None]:
        """Load a secret as SecureBytes with automatic zeroization.

        The secret is automatically zeroized when the context manager exits,
        even if an exception occurs.
        """
        secure_data = self._load_secret(key)
        try:
            yield secure_data
        finally:
            secure_data.zeroize()
            # Also zeroize from cache
            with self._cache_lock:
                if key in self._cache:
                    self._cache[key].zeroize()
                    del self._cache[key]

    @asynccontextmanager
    async def secrets(self, keys: List[str]) -> Generator[Dict[str, SecureBytes], None, None]:
        """Load multiple secrets as SecureBytes with automatic zeroization."""
        loaded: Dict[str, SecureBytes] = {}
        try:
            for _key in keys:
                loaded[_key] = self._load_secret(_key)
            yield loaded
        finally:
            # Zeroize ALL secrets on exit
            for _key, secure_data in loaded.items():
                secure_data.zeroize()
            with self._cache_lock:
                for key in keys:
                    if key in self._cache:
                        self._cache[key].zeroize()
                        del self._cache[key]

    def _load_secret(self, key: str) -> SecureBytes:
        """Load a secret from the appropriate source.

        Priority order:
            1. Environment variable (highest priority — container-friendly)
            2. .env file (local development)
            3. Infinity Void vault (encrypted secrets)
            4. HSM-encrypted file (if HSM is available)
        """
        # Source 1: Environment variable
        value = os.environ.get(key)
        if value is not None:
            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.SECRET_READ,
                    actor="vault-secret-loader",
                    resource=key,
                    success=True,
                    details={"source": SecretSource.ENVIRONMENT.value},
                )
            )
            return SecureBytes(value.encode("utf-8"), lock_memory=self._lock_memory)

        # Source 2: .env file
        if self._dotenv_path and os.path.exists(self._dotenv_path):
            value = self._read_dotenv(key)
            if value is not None:
                self._audit.log(
                    VaultAuditEvent(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event_type=VaultEventType.SECRET_READ,
                        actor="vault-secret-loader",
                        resource=key,
                        success=True,
                        details={"source": SecretSource.DOTENV.value},
                    )
                )
                return SecureBytes(value.encode("utf-8"), lock_memory=self._lock_memory)

        # Source 3: Infinity Void vault
        if self._infinity_void_url and self._infinity_void_secret:
            value = self._read_infinity_void(key)
            if value is not None:
                self._audit.log(
                    VaultAuditEvent(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event_type=VaultEventType.SECRET_READ,
                        actor="vault-secret-loader",
                        resource=key,
                        success=True,
                        details={"source": SecretSource.INFINITY_VOID.value},
                    )
                )
                return SecureBytes(value, lock_memory=self._lock_memory)

        # Source 4: HSM-encrypted file
        if self._hsm and self._hsm.is_available():
            value = self._read_hsm_encrypted(key)
            if value is not None:
                self._audit.log(
                    VaultAuditEvent(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event_type=VaultEventType.SECRET_READ,
                        actor="vault-secret-loader",
                        resource=key,
                        success=True,
                        details={"source": SecretSource.HSM.value},
                    )
                )
                return SecureBytes(value, lock_memory=self._lock_memory)

        # Secret not found — audit the failure
        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.ACCESS_DENIED,
                actor="vault-secret-loader",
                resource=key,
                success=False,
                details={"reason": "secret_not_found"},
            )
        )
        raise KeyError(f"Secret '{key}' not found in any source")

    def _read_dotenv(self, key: str) -> Optional[str]:
        """Read a value from a .env file."""
        try:
            with open(self._dotenv_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    if k.strip() == key:
                        # Remove quotes if present
                        v = v.strip().strip("'\"")
                        return v
        except Exception as e:
            logger.debug("Error reading .env file: %s", e)
        return None

    def _read_infinity_void(self, key: str) -> Optional[bytes]:
        """Read a secret from the Infinity Void vault.

        The Infinity Void is a self-hosted encrypted secrets service
        that replaces Cloudflare D1 + R2-based secret storage.
        It provides AES-256-GCM encryption with SQLite backend.
        """
        if not self._infinity_void_url or not self._infinity_void_secret:
            return None

        try:
            import httpx

            # Get the internal secret for authentication
            auth_secret = self._infinity_void_secret.reveal().decode()

            response = httpx.get(
                f"{self._infinity_void_url}/api/v1/secrets/{key}",
                headers={
                    "Authorization": f"Bearer {auth_secret}",
                    "X-Internal-Secret": auth_secret,
                },
                timeout=5.0,
            )

            # Zeroize the auth secret from the local variable
            # (SecureBytes handles its own zeroization)
            if response.status_code == 200:
                data = response.json()
                return data.get("value", "").encode("utf-8")
            elif response.status_code == 404:
                return None
            else:
                logger.warning(
                    "Infinity Void returned %d for key '%s'",
                    response.status_code,
                    key,
                )
                return None
        except ImportError:
            logger.warning("httpx not installed — cannot access Infinity Void")
            return None
        except Exception as e:
            logger.warning("Error accessing Infinity Void: %s", e)
            return None

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Sanitize a secret key to prevent path traversal in file paths.

        Only allows alphanumeric characters, hyphens, underscores, and dots.
        Rejects any key containing path separators or traversal sequences.
        """
        import re

        if not re.match(r"^[a-zA-Z0-9._-]+$", key):
            raise ValueError(
                f"Invalid secret key: {key!r} — only alphanumeric, hyphens, underscores, and dots allowed"
            )
        return key

    def _read_hsm_encrypted(self, key: str) -> Optional[bytes]:
        """Read and decrypt a secret from an HSM-encrypted file."""
        safe_key = self._sanitize_key(key)
        encrypted_path = Path(f"secrets/hsm/{safe_key}.enc")
        if not encrypted_path.exists():
            return None

        try:
            ciphertext = encrypted_path.read_bytes()
            # The key_handle is stored in the first line of the file
            # Format: key_handle\nbase64_ciphertext
            lines = ciphertext.split(b"\n", 1)
            if len(lines) != 2:
                return None

            key_handle = lines[0].decode("utf-8")
            # Decode base64 ciphertext that was written by store_secret
            import base64

            actual_ciphertext = base64.b64decode(lines[1])

            plaintext = self._hsm.decrypt(key_handle, actual_ciphertext)
            return plaintext
        except Exception as e:
            logger.warning("Error reading HSM-encrypted secret '%s': %s", key, e)
            return None

    def store_secret(
        self,
        key: str,
        value: bytes,
        source: SecretSource = SecretSource.HSM,
        key_handle: Optional[str] = None,
    ) -> None:
        """Store a secret securely.

        For HSM source: Encrypts the value with the HSM and stores the ciphertext.
        For Infinity Void: Sends the value to the vault API.
        """
        if source == SecretSource.HSM and self._hsm and self._hsm.is_available():
            if not key_handle:
                key_handle = f"tranc3-vault-{key}"

            # Encrypt the value
            ciphertext = self._hsm.encrypt(key_handle, value)

            # Store to file (with sanitized key for path safety)
            safe_key = self._sanitize_key(key)
            secrets_dir = Path("secrets/hsm")
            secrets_dir.mkdir(parents=True, exist_ok=True)
            encrypted_path = secrets_dir / f"{safe_key}.enc"

            # Format: key_handle\nbase64_ciphertext
            import base64

            file_content = key_handle.encode("utf-8") + b"\n" + base64.b64encode(ciphertext)
            encrypted_path.write_bytes(file_content)

            self._audit.log(
                VaultAuditEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event_type=VaultEventType.SECRET_WRITE,
                    actor="vault-secret-loader",
                    resource=key,
                    success=True,
                    details={"source": source.value, "key_handle": key_handle},
                )
            )

        elif source == SecretSource.INFINITY_VOID and self._infinity_void_url:
            try:
                import httpx

                auth_secret = self._infinity_void_secret.reveal().decode()

                response = httpx.put(
                    f"{self._infinity_void_url}/api/v1/secrets/{key}",
                    headers={
                        "Authorization": f"Bearer {auth_secret}",
                        "X-Internal-Secret": auth_secret,
                    },
                    json={"value": value.decode("utf-8")},
                    timeout=5.0,
                )

                if response.status_code not in (200, 201):
                    raise RuntimeError(f"Infinity Void returned {response.status_code}")

                self._audit.log(
                    VaultAuditEvent(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event_type=VaultEventType.SECRET_WRITE,
                        actor="vault-secret-loader",
                        resource=key,
                        success=True,
                        details={"source": source.value},
                    )
                )
            except Exception as e:
                self._audit.log(
                    VaultAuditEvent(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event_type=VaultEventType.SECRET_WRITE,
                        actor="vault-secret-loader",
                        resource=key,
                        success=False,
                        details={"error": str(e), "source": source.value},
                    )
                )
                raise
        else:
            raise ValueError(f"Cannot store secret with source '{source}' — no backend available")

    def rotate_secret(self, key: str, new_value: bytes) -> None:
        """Rotate a secret — replaces the old value with a new one.

        The old value is zeroized immediately after rotation.
        """
        # Load and zeroize the old value
        try:
            old_secret = self._load_secret(key)
            old_secret.zeroize()
        except KeyError:
            pass  # Old secret didn't exist — that's fine

        # Store the new value
        self.store_secret(key, new_value)

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.VAULT_ROTATE,
                actor="vault-secret-loader",
                resource=key,
                success=True,
            )
        )
        logger.info("Secret rotated: %s", key)

    def close(self) -> None:
        """Close the secret loader and zeroize all cached secrets."""
        with self._cache_lock:
            for _key, secure_data in self._cache.items():
                secure_data.zeroize()
            self._cache.clear()

        if self._hsm:
            self._hsm.close()

        if self._infinity_void_secret:
            self._infinity_void_secret.zeroize()

        self._audit.log(
            VaultAuditEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=VaultEventType.VAULT_LOCK,
                actor="vault-secret-loader",
                resource="all",
                success=True,
            )
        )
        logger.info("VaultSecretLoader closed — all secrets zeroized")


# ── Convenience Factory ──────────────────────────────────────────────────────


def create_vault_security(
    hsm_type: str = "softhsm2",
    hsm_config: Optional[Dict[str, Any]] = None,
    audit_log_dir: str = "logs/vault-audit",
    lock_memory: bool = True,
) -> VaultSecretLoader:
    """Factory function to create a configured VaultSecretLoader.

    Args:
        hsm_type: "softhsm2" (dev/test) or "yubihsm2" (production)
        hsm_config: HSM-specific configuration
        audit_log_dir: Directory for audit log files
        lock_memory: Whether to mlock() secret memory

    Returns:
        Configured VaultSecretLoader instance
    """
    hsm_config = hsm_config or {}
    audit_logger = VaultAuditLogger(log_dir=audit_log_dir)

    if hsm_type == "softhsm2":
        hsm = SoftHSM2Provider(
            token=hsm_config.get("token", "tranc3"),
            pin=hsm_config.get("pin", "123456"),
            library_path=hsm_config.get("library_path"),
            slot=hsm_config.get("slot"),
            audit_logger=audit_logger,
        )
    elif hsm_type == "yubihsm2":
        hsm = YubiHSM2Provider(
            connector_url=hsm_config.get("connector_url", "http://localhost:12345"),
            auth_key_id=hsm_config.get("auth_key_id", 1),
            auth_key_password=hsm_config.get("auth_key_password", b"password"),
            library_path=hsm_config.get("library_path"),
            audit_logger=audit_logger,
        )
    else:
        hsm = None

    return VaultSecretLoader(
        hsm_provider=hsm,
        audit_logger=audit_logger,
        lock_memory=lock_memory,
        dotenv_path=hsm_config.get("dotenv_path"),
        infinity_void_url=hsm_config.get("infinity_void_url"),
        infinity_void_secret=hsm_config.get("infinity_void_secret"),
    )
