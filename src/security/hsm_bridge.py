"""
hsm_bridge.py — HSM (Hardware Security Module) bridge for the Tranc3 platform.

Priority:
  1. SoftHSM2 via PKCS#11 (python-pkcs11, BSD licence) — zero cost
  2. YubiHSM2 via python-pkcs11 (same library, different slot)
  3. Software fallback using cryptography.hazmat (in-process key store)

Environment variables:
  HSM_SLOT   — PKCS#11 slot index (default: 0)
  HSM_PIN    — PKCS#11 PIN (default: "1234" for development)
  HSM_TOKEN  — PKCS#11 token label (default: "tranc3")

Part of: The Void / Cryptex (Cyber Defence)
"""

from __future__ import annotations

import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt PKCS#11 import (python-pkcs11, BSD licence)
# ---------------------------------------------------------------------------
_PKCS11_AVAILABLE = False
_pkcs11_lib = None

_SOFTHSM_PATHS = [
    "/usr/lib/softhsm/libsofthsm2.so",
    "/usr/local/lib/softhsm/libsofthsm2.so",
    "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",
    "/usr/lib64/softhsm/libsofthsm2.so",
]

try:
    import pkcs11  # type: ignore
    _PKCS11_AVAILABLE = True
    logger.debug("python-pkcs11 available")
except ImportError:
    logger.debug("python-pkcs11 not installed — will use software fallback")

# ---------------------------------------------------------------------------
# Attempt cryptography import (always available in Tranc3 venv)
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    logger.warning("cryptography package not available — HSM software fallback disabled")


# ---------------------------------------------------------------------------
# Helper: software key store entry
# ---------------------------------------------------------------------------

class _SoftwareKey:
    """In-process software-simulated HSM key."""

    def __init__(self, key_id: str, key_type: str) -> None:
        self.key_id = key_id
        self.key_type = key_type
        self.created_at = time.time()
        # AES keys
        self._aes_key: bytes | None = None
        # RSA keys
        self._rsa_private = None
        self._rsa_public = None

        if key_type.upper() in ("AES128", "AES192", "AES256"):
            bits = int(key_type[3:])
            self._aes_key = secrets.token_bytes(bits // 8)
            logger.info("Software HSM: generated %s key '%s'", key_type, key_id)
        elif key_type.upper().startswith("RSA"):
            bits = int(key_type[3:]) if len(key_type) > 3 else 2048
            if _CRYPTO_AVAILABLE:
                self._rsa_private = rsa.generate_private_key(
                    public_exponent=65537, key_size=bits, backend=default_backend()
                )
                self._rsa_public = self._rsa_private.public_key()
            logger.info("Software HSM: generated %s key '%s'", key_type, key_id)
        else:
            raise ValueError(f"Unsupported key type for software HSM: {key_type}")


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class HSMBridge:
    """
    Unified HSM bridge supporting SoftHSM2, YubiHSM2, and a software fallback.

    Key material is NEVER logged or exported (public keys excepted).
    """

    def __init__(self, hsm_type: str = "auto") -> None:
        self._hsm_type = hsm_type
        self._slot = int(os.environ.get("HSM_SLOT", "0"))
        self._pin = os.environ.get("HSM_PIN", "1234")
        self._token_label = os.environ.get("HSM_TOKEN", "tranc3")

        # PKCS#11 state
        self._pkcs11_lib_path: str | None = None
        self._pkcs11_token = None

        # Software fallback key store
        self._sw_keys: dict[str, _SoftwareKey] = {}

        self._active_backend = self._init_backend(hsm_type)
        logger.info("HSMBridge initialised: backend=%s", self._active_backend)

    def _init_backend(self, hsm_type: str) -> str:
        if hsm_type == "software":
            return "software"

        if _PKCS11_AVAILABLE:
            # Try SoftHSM2
            if hsm_type in ("auto", "softhsm2"):
                for path in _SOFTHSM_PATHS:
                    if os.path.exists(path):
                        try:
                            self._pkcs11_lib_path = path
                            self._pkcs11_token = self._open_pkcs11_token(path)
                            logger.info("HSMBridge: SoftHSM2 loaded from %s", path)
                            return "softhsm2"
                        except Exception as exc:
                            logger.debug("SoftHSM2 at %s failed: %s", path, exc)

            # YubiHSM2 is also exposed via PKCS#11 but uses a different library
            # (yubihsm-connector). We treat any non-softhsm PKCS#11 as yubihsm2.
            if hsm_type == "yubihsm2":
                yubilib = os.environ.get("YUBIHSM_PKCS11_LIB", "/usr/lib/pkcs11/yubihsm_pkcs11.so")
                if os.path.exists(yubilib):
                    try:
                        self._pkcs11_lib_path = yubilib
                        self._pkcs11_token = self._open_pkcs11_token(yubilib)
                        return "yubihsm2"
                    except Exception as exc:
                        logger.debug("YubiHSM2 init failed: %s", exc)

        if not _CRYPTO_AVAILABLE:
            logger.warning(
                "HSMBridge: no HSM hardware and cryptography package missing — "
                "key operations will fail"
            )
            return "none"

        logger.warning(
            "HSMBridge: no HSM hardware found — degrading to in-process software HSM. "
            "NOT suitable for production."
        )
        return "software"

    def _open_pkcs11_token(self, lib_path: str):
        """Open a PKCS#11 session on the configured slot."""
        lib = pkcs11.lib(lib_path)
        slots = lib.get_slots(token_present=True)
        if not slots:
            raise RuntimeError("No PKCS#11 slots with token present")
        slot = slots[self._slot] if self._slot < len(slots) else slots[0]
        token = slot.get_token()
        return token

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def generate_key(self, key_id: str, key_type: str = "AES256") -> bool:
        """Generate and store a key in the HSM. Returns True on success."""
        try:
            if self._active_backend == "software":
                if key_id in self._sw_keys:
                    logger.warning("Key '%s' already exists in software HSM", key_id)
                    return False
                self._sw_keys[key_id] = _SoftwareKey(key_id, key_type)
                return True

            if self._active_backend in ("softhsm2", "yubihsm2"):
                return self._pkcs11_generate(key_id, key_type)

            logger.error("generate_key: no usable HSM backend")
            return False
        except Exception as exc:
            logger.error("generate_key('%s'): %s", key_id, exc)
            return False

    def _pkcs11_generate(self, key_id: str, key_type: str) -> bool:
        try:
            with self._pkcs11_token.open(rw=True, user_pin=self._pin) as session:
                kt = key_type.upper()
                if kt.startswith("AES"):
                    bits = int(kt[3:]) if len(kt) > 3 else 256
                    session.generate_key(
                        pkcs11.KeyType.AES,
                        bits,
                        label=key_id,
                        id=key_id.encode()[:32],
                        store=True,
                        capabilities=pkcs11.MechanismFlag.ENCRYPT | pkcs11.MechanismFlag.DECRYPT,
                    )
                elif kt.startswith("RSA"):
                    bits = int(kt[3:]) if len(kt) > 3 else 2048
                    session.generate_keypair(
                        pkcs11.KeyType.RSA,
                        bits,
                        label=key_id,
                        id=key_id.encode()[:32],
                        store=True,
                    )
                else:
                    raise ValueError(f"Unsupported key type: {key_type}")
            logger.info("PKCS#11: generated %s key '%s'", key_type, key_id)
            return True
        except Exception as exc:
            logger.error("PKCS#11 generate_key('%s'): %s", key_id, exc)
            return False

    # ------------------------------------------------------------------
    # Encrypt / Decrypt
    # ------------------------------------------------------------------

    def encrypt(self, key_id: str, plaintext: bytes) -> bytes:
        """Encrypt *plaintext* using the HSM key identified by *key_id*."""
        try:
            if self._active_backend == "software":
                return self._sw_encrypt(key_id, plaintext)
            if self._active_backend in ("softhsm2", "yubihsm2"):
                return self._pkcs11_encrypt(key_id, plaintext)
            raise RuntimeError("No usable HSM backend")
        except Exception as exc:
            logger.error("encrypt(key_id='%s'): %s", key_id, exc)
            raise

    def _sw_encrypt(self, key_id: str, plaintext: bytes) -> bytes:
        key = self._sw_keys.get(key_id)
        if key is None:
            raise KeyError(f"Key '{key_id}' not found in software HSM")
        if key._aes_key is None:
            raise TypeError(f"Key '{key_id}' is not an AES key")
        iv = secrets.token_bytes(12)
        ct = AESGCM(key._aes_key).encrypt(iv, plaintext, None)
        return iv + ct  # 12-byte IV + ciphertext+tag

    def _pkcs11_encrypt(self, key_id: str, plaintext: bytes) -> bytes:
        with self._pkcs11_token.open(user_pin=self._pin) as session:
            keys = list(session.get_objects({
                pkcs11.Attribute.LABEL: key_id,
                pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY,
            }))
            if not keys:
                raise KeyError(f"PKCS#11: key '{key_id}' not found")
            iv = secrets.token_bytes(12)
            ct = keys[0].encrypt(plaintext, mechanism=pkcs11.Mechanism.AES_GCM, mechanism_param=iv)
            return iv + bytes(ct)

    def decrypt(self, key_id: str, ciphertext: bytes) -> bytes:
        """Decrypt *ciphertext* using the HSM key identified by *key_id*."""
        try:
            if self._active_backend == "software":
                return self._sw_decrypt(key_id, ciphertext)
            if self._active_backend in ("softhsm2", "yubihsm2"):
                return self._pkcs11_decrypt(key_id, ciphertext)
            raise RuntimeError("No usable HSM backend")
        except Exception as exc:
            logger.error("decrypt(key_id='%s'): %s", key_id, exc)
            raise

    def _sw_decrypt(self, key_id: str, ciphertext: bytes) -> bytes:
        key = self._sw_keys.get(key_id)
        if key is None:
            raise KeyError(f"Key '{key_id}' not found in software HSM")
        if key._aes_key is None:
            raise TypeError(f"Key '{key_id}' is not an AES key")
        iv, ct = ciphertext[:12], ciphertext[12:]
        return AESGCM(key._aes_key).decrypt(iv, ct, None)

    def _pkcs11_decrypt(self, key_id: str, ciphertext: bytes) -> bytes:
        with self._pkcs11_token.open(user_pin=self._pin) as session:
            keys = list(session.get_objects({
                pkcs11.Attribute.LABEL: key_id,
                pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY,
            }))
            if not keys:
                raise KeyError(f"PKCS#11: key '{key_id}' not found")
            iv, ct = ciphertext[:12], ciphertext[12:]
            return bytes(keys[0].decrypt(ct, mechanism=pkcs11.Mechanism.AES_GCM, mechanism_param=iv))

    # ------------------------------------------------------------------
    # Sign / Verify
    # ------------------------------------------------------------------

    def sign(self, key_id: str, data: bytes, mechanism: str = "SHA256_RSA_PKCS") -> bytes:
        """Sign *data* using the HSM private key identified by *key_id*."""
        try:
            if self._active_backend == "software":
                return self._sw_sign(key_id, data)
            if self._active_backend in ("softhsm2", "yubihsm2"):
                return self._pkcs11_sign(key_id, data, mechanism)
            raise RuntimeError("No usable HSM backend")
        except Exception as exc:
            logger.error("sign(key_id='%s'): %s", key_id, exc)
            raise

    def _sw_sign(self, key_id: str, data: bytes) -> bytes:
        key = self._sw_keys.get(key_id)
        if key is None:
            raise KeyError(f"Key '{key_id}' not found")
        if key._rsa_private is None:
            raise TypeError(f"Key '{key_id}' is not an RSA key")
        return key._rsa_private.sign(data, padding.PKCS1v15(), hashes.SHA256())

    def _pkcs11_sign(self, key_id: str, data: bytes, mechanism: str) -> bytes:
        with self._pkcs11_token.open(user_pin=self._pin) as session:
            keys = list(session.get_objects({
                pkcs11.Attribute.LABEL: key_id,
                pkcs11.Attribute.CLASS: pkcs11.ObjectClass.PRIVATE_KEY,
            }))
            if not keys:
                raise KeyError(f"PKCS#11: private key '{key_id}' not found")
            mech = getattr(pkcs11.Mechanism, mechanism, pkcs11.Mechanism.SHA256_RSA_PKCS)
            return bytes(keys[0].sign(data, mechanism=mech))

    def verify(self, key_id: str, data: bytes, signature: bytes) -> bool:
        """Verify *signature* over *data* using the HSM public key."""
        try:
            if self._active_backend == "software":
                return self._sw_verify(key_id, data, signature)
            if self._active_backend in ("softhsm2", "yubihsm2"):
                return self._pkcs11_verify(key_id, data, signature)
            return False
        except Exception as exc:
            logger.debug("verify(key_id='%s'): %s", key_id, exc)
            return False

    def _sw_verify(self, key_id: str, data: bytes, signature: bytes) -> bool:
        key = self._sw_keys.get(key_id)
        if key is None or key._rsa_public is None:
            return False
        try:
            key._rsa_public.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def _pkcs11_verify(self, key_id: str, data: bytes, signature: bytes) -> bool:
        try:
            with self._pkcs11_token.open(user_pin=self._pin) as session:
                keys = list(session.get_objects({
                    pkcs11.Attribute.LABEL: key_id,
                    pkcs11.Attribute.CLASS: pkcs11.ObjectClass.PUBLIC_KEY,
                }))
                if not keys:
                    return False
                keys[0].verify(data, signature, mechanism=pkcs11.Mechanism.SHA256_RSA_PKCS)
                return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Key listing / deletion
    # ------------------------------------------------------------------

    def list_keys(self) -> list[dict]:
        """List available keys (metadata only — no key material)."""
        if self._active_backend == "software":
            return [
                {
                    "key_id": k.key_id,
                    "key_type": k.key_type,
                    "created_at": k.created_at,
                    "backend": "software",
                }
                for k in self._sw_keys.values()
            ]
        if self._active_backend in ("softhsm2", "yubihsm2"):
            try:
                with self._pkcs11_token.open(user_pin=self._pin) as session:
                    objs = list(session.get_objects())
                    result = []
                    for obj in objs:
                        try:
                            label = obj[pkcs11.Attribute.LABEL]
                            cls = obj[pkcs11.Attribute.CLASS]
                            result.append({"key_id": label, "class": str(cls), "backend": self._active_backend})
                        except Exception:
                            pass
                    return result
            except Exception as exc:
                logger.error("list_keys: %s", exc)
        return []

    def delete_key(self, key_id: str) -> bool:
        """Delete a key from the HSM."""
        try:
            if self._active_backend == "software":
                if key_id in self._sw_keys:
                    del self._sw_keys[key_id]
                    logger.info("Software HSM: deleted key '%s'", key_id)
                    return True
                return False
            if self._active_backend in ("softhsm2", "yubihsm2"):
                with self._pkcs11_token.open(rw=True, user_pin=self._pin) as session:
                    objs = list(session.get_objects({pkcs11.Attribute.LABEL: key_id}))
                    for obj in objs:
                        obj.destroy()
                    logger.info("PKCS#11: deleted key '%s'", key_id)
                    return bool(objs)
        except Exception as exc:
            logger.error("delete_key('%s'): %s", key_id, exc)
        return False

    def export_public_key(self, key_id: str) -> bytes | None:
        """Export the PEM-encoded public key. Private keys are NEVER exported."""
        try:
            if self._active_backend == "software":
                key = self._sw_keys.get(key_id)
                if key and key._rsa_public and _CRYPTO_AVAILABLE:
                    return key._rsa_public.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                return None
            if self._active_backend in ("softhsm2", "yubihsm2"):
                with self._pkcs11_token.open(user_pin=self._pin) as session:
                    keys = list(session.get_objects({
                        pkcs11.Attribute.LABEL: key_id,
                        pkcs11.Attribute.CLASS: pkcs11.ObjectClass.PUBLIC_KEY,
                    }))
                    if keys:
                        # python-pkcs11 exposes DER via CKA_VALUE for RSA public keys
                        der = keys[0].get(pkcs11.Attribute.VALUE, None)
                        return der
        except Exception as exc:
            logger.error("export_public_key('%s'): %s", key_id, exc)
        return None

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return HSM health and configuration status."""
        status: dict = {
            "backend": self._active_backend,
            "pkcs11_available": _PKCS11_AVAILABLE,
            "crypto_available": _CRYPTO_AVAILABLE,
            "slot": self._slot,
            "softhsm_path": self._pkcs11_lib_path,
            "healthy": self._active_backend != "none",
        }
        if self._active_backend == "software":
            status["key_count"] = len(self._sw_keys)
        elif self._active_backend in ("softhsm2", "yubihsm2"):
            try:
                keys = self.list_keys()
                status["key_count"] = len(keys)
                status["healthy"] = True
            except Exception as exc:
                status["healthy"] = False
                status["error"] = str(exc)
        return status
