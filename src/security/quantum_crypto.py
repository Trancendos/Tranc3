"""
quantum_crypto.py — Post-quantum cryptography layer for the Tranc3 platform.

Primary: attempts to use `pqcrypto` (MIT licence) for CRYSTALS-Kyber / Dilithium.
Fallback: X25519 + ChaCha20-Poly1305 (classical but strong), clearly labelled.

NOTE: The pure-Python fallback does NOT provide post-quantum security.
      It is intended for development / testing only. For production
      post-quantum security, install the `pqcrypto` package.

Part of: Cryptex (Cyber Defence) / The Void integration.
"""

from __future__ import annotations

import logging
import os
import struct
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt pqcrypto import (optional, MIT licence)
# ---------------------------------------------------------------------------
_PQ_AVAILABLE = False
_KEM_MODULE = None
_SIG_MODULE = None

try:
    import pqcrypto.kem.kyber768 as _kyber768  # type: ignore
    import pqcrypto.sign.dilithium3 as _dilithium3  # type: ignore

    _KEM_MODULE = _kyber768
    _SIG_MODULE = _dilithium3
    _PQ_AVAILABLE = True
    logger.info("quantum_crypto: pqcrypto available — using Kyber-768 + Dilithium3")
except ImportError:
    logger.warning(
        "quantum_crypto: pqcrypto not installed — falling back to X25519 + "
        "ChaCha20-Poly1305 (classical, NOT post-quantum). "
        "Install `pip install pqcrypto` for true post-quantum security."
    )

# Always-available classical crypto
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305, AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed25519
from cryptography.exceptions import InvalidSignature


# ---------------------------------------------------------------------------
# Algorithm info
# ---------------------------------------------------------------------------

def get_algorithm_info() -> dict:
    """Return metadata about the algorithms actually in use."""
    if _PQ_AVAILABLE:
        return {
            "kem": "CRYSTALS-Kyber-768 (NIST PQC winner, pqcrypto)",
            "signature": "CRYSTALS-Dilithium3 (NIST PQC winner, pqcrypto)",
            "hybrid_symmetric": "AES-256-GCM",
            "hybrid_kdf": "HKDF-SHA256",
            "post_quantum": True,
            "library": "pqcrypto",
        }
    return {
        "kem": "X25519 (classical ECDH — NOT post-quantum, development fallback)",
        "signature": "Ed25519 (classical — NOT post-quantum, development fallback)",
        "hybrid_symmetric": "ChaCha20-Poly1305",
        "hybrid_kdf": "HKDF-SHA256",
        "post_quantum": False,
        "library": "cryptography (hazmat)",
        "warning": "pqcrypto not installed — no post-quantum protection in this mode",
    }


# ---------------------------------------------------------------------------
# QuantumKEM
# ---------------------------------------------------------------------------

class QuantumKEM:
    """
    Key Encapsulation Mechanism.

    With pqcrypto: Kyber-768
    Without:       X25519 (classical ECDH)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_keypair(self) -> tuple[bytes, bytes]:
        """
        Generate a KEM key pair.

        Returns:
            (public_key_bytes, private_key_bytes)
        """
        try:
            if _PQ_AVAILABLE and _KEM_MODULE is not None:
                pk, sk = _KEM_MODULE.generate_keypair()
                return bytes(pk), bytes(sk)
            return self._x25519_generate_keypair()
        except Exception as exc:
            logger.error("QuantumKEM.generate_keypair failed: %s", exc)
            return b"", b""

    def encapsulate(self, public_key: bytes) -> tuple[bytes, bytes]:
        """
        Encapsulate a fresh shared secret using the recipient's public key.

        Returns:
            (ciphertext, shared_secret)  — both bytes.
            Returns (b"", b"") on failure.
        """
        try:
            if _PQ_AVAILABLE and _KEM_MODULE is not None:
                ct, ss = _KEM_MODULE.encapsulate(public_key)
                return bytes(ct), bytes(ss)
            return self._x25519_encapsulate(public_key)
        except Exception as exc:
            logger.error("QuantumKEM.encapsulate failed: %s", exc)
            return b"", b""

    def decapsulate(self, ciphertext: bytes, private_key: bytes) -> bytes:
        """
        Recover the shared secret from a ciphertext and private key.

        Returns:
            shared_secret bytes, or b"" on failure.
        """
        try:
            if _PQ_AVAILABLE and _KEM_MODULE is not None:
                ss = _KEM_MODULE.decapsulate(ciphertext, private_key)
                return bytes(ss)
            return self._x25519_decapsulate(ciphertext, private_key)
        except Exception as exc:
            logger.error("QuantumKEM.decapsulate failed: %s", exc)
            return b""

    # ------------------------------------------------------------------
    # X25519 classical fallback helpers
    # ------------------------------------------------------------------

    def _x25519_generate_keypair(self) -> tuple[bytes, bytes]:
        priv = X25519PrivateKey.generate()
        pub = priv.public_key()
        priv_bytes = priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        pub_bytes = pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return pub_bytes, priv_bytes

    def _x25519_encapsulate(self, peer_public_bytes: bytes) -> tuple[bytes, bytes]:
        # Generate ephemeral key pair
        eph_priv = X25519PrivateKey.generate()
        eph_pub = eph_priv.public_key()

        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        peer_pub = X25519PublicKey.from_public_bytes(peer_public_bytes)
        raw_ss = eph_priv.exchange(peer_pub)

        # ciphertext = ephemeral public key (receiver needs it to reconstruct SS)
        eph_pub_bytes = eph_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

        # Derive a proper shared secret via HKDF
        ss = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"x25519-kem-shared-secret",
        ).derive(raw_ss)

        return eph_pub_bytes, ss

    def _x25519_decapsulate(self, ciphertext: bytes, private_key_bytes: bytes) -> bytes:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        # ciphertext IS the ephemeral public key
        eph_pub = X25519PublicKey.from_public_bytes(ciphertext)
        priv = X25519PrivateKey.from_private_bytes(private_key_bytes)
        raw_ss = priv.exchange(eph_pub)

        ss = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"x25519-kem-shared-secret",
        ).derive(raw_ss)
        return ss


# ---------------------------------------------------------------------------
# QuantumSignature
# ---------------------------------------------------------------------------

class QuantumSignature:
    """
    Post-quantum digital signatures.

    With pqcrypto: Dilithium3
    Without:       Ed25519 (classical)
    """

    def generate_keypair(self) -> tuple[bytes, bytes]:
        """
        Returns:
            (public_key_bytes, private_key_bytes)
        """
        try:
            if _PQ_AVAILABLE and _SIG_MODULE is not None:
                pk, sk = _SIG_MODULE.generate_keypair()
                return bytes(pk), bytes(sk)
            return self._ed25519_generate_keypair()
        except Exception as exc:
            logger.error("QuantumSignature.generate_keypair failed: %s", exc)
            return b"", b""

    def sign(self, message: bytes, private_key: bytes) -> bytes:
        """
        Returns:
            signature bytes, or b"" on failure.
        """
        try:
            if _PQ_AVAILABLE and _SIG_MODULE is not None:
                sig = _SIG_MODULE.sign(message, private_key)
                return bytes(sig)
            return self._ed25519_sign(message, private_key)
        except Exception as exc:
            logger.error("QuantumSignature.sign failed: %s", exc)
            return b""

    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        """
        Returns:
            True if signature is valid, False otherwise.
        """
        try:
            if _PQ_AVAILABLE and _SIG_MODULE is not None:
                _SIG_MODULE.verify(message, signature, public_key)
                return True
            return self._ed25519_verify(message, signature, public_key)
        except Exception as exc:
            logger.debug("QuantumSignature.verify: invalid — %s", exc)
            return False

    # ------------------------------------------------------------------
    # Ed25519 classical fallback helpers
    # ------------------------------------------------------------------

    def _ed25519_generate_keypair(self) -> tuple[bytes, bytes]:
        priv = _ed25519.Ed25519PrivateKey.generate()
        pub = priv.public_key()
        priv_bytes = priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        pub_bytes = pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return pub_bytes, priv_bytes

    def _ed25519_sign(self, message: bytes, private_key_bytes: bytes) -> bytes:
        priv = _ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        return priv.sign(message)

    def _ed25519_verify(
        self, message: bytes, signature: bytes, public_key_bytes: bytes
    ) -> bool:
        try:
            pub = _ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            pub.verify(signature, message)
            return True
        except InvalidSignature:
            return False


# ---------------------------------------------------------------------------
# HybridEncryption
# ---------------------------------------------------------------------------

class HybridEncryption:
    """
    Hybrid encryption: quantum-resistant KEM + AES-256-GCM (or ChaCha20-Poly1305).

    Encrypted blob format (dict):
    {
        "version":          int  (1),
        "kem_ciphertext":   hex str  — KEM ciphertext (ephemeral pub key or Kyber CT),
        "aes_iv":           hex str  — 12-byte GCM nonce,
        "aes_tag":          hex str  — 16-byte GCM authentication tag,
        "aes_ciphertext":   hex str  — AES-256-GCM (or ChaCha20) ciphertext,
        "algorithm":        str,
    }

    The AES/ChaCha symmetric key is derived from the KEM shared secret via HKDF-SHA256.
    """

    def __init__(self) -> None:
        self._kem = QuantumKEM()

    def encrypt(self, plaintext: bytes, recipient_public_key: bytes) -> dict:
        """
        Encrypt *plaintext* for the holder of *recipient_public_key*.

        Returns:
            Encrypted blob dict, or empty dict on failure.
        """
        try:
            kem_ct, shared_secret = self._kem.encapsulate(recipient_public_key)
            if not kem_ct or not shared_secret:
                raise ValueError("KEM encapsulation failed")

            sym_key = self._derive_sym_key(shared_secret)
            iv, tag, ct = self._sym_encrypt(sym_key, plaintext)

            algo = get_algorithm_info()
            return {
                "version": 1,
                "kem_ciphertext": kem_ct.hex(),
                "aes_iv": iv.hex(),
                "aes_tag": tag.hex(),
                "aes_ciphertext": ct.hex(),
                "algorithm": f"{algo['kem']} + {algo['hybrid_symmetric']}",
            }
        except Exception as exc:
            logger.error("HybridEncryption.encrypt failed: %s", exc)
            return {}

    def decrypt(self, encrypted_blob: dict, recipient_private_key: bytes) -> bytes:
        """
        Decrypt an *encrypted_blob* using *recipient_private_key*.

        Returns:
            plaintext bytes, or b"" on failure.
        """
        try:
            kem_ct = bytes.fromhex(encrypted_blob["kem_ciphertext"])
            iv = bytes.fromhex(encrypted_blob["aes_iv"])
            tag = bytes.fromhex(encrypted_blob["aes_tag"])
            aes_ct = bytes.fromhex(encrypted_blob["aes_ciphertext"])

            shared_secret = self._kem.decapsulate(kem_ct, recipient_private_key)
            if not shared_secret:
                raise ValueError("KEM decapsulation failed")

            sym_key = self._derive_sym_key(shared_secret)
            return self._sym_decrypt(sym_key, iv, tag, aes_ct)
        except Exception as exc:
            logger.error("HybridEncryption.decrypt failed: %s", exc)
            return b""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _derive_sym_key(self, shared_secret: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"hybrid-encryption-sym-key",
        ).derive(shared_secret)

    def _sym_encrypt(self, key: bytes, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        """Returns (iv, tag, ciphertext)."""
        iv = os.urandom(12)
        if _PQ_AVAILABLE:
            # AES-256-GCM
            aesgcm = AESGCM(key)
            combined = aesgcm.encrypt(iv, plaintext, None)
            # AESGCM appends tag to ciphertext
            ct = combined[:-16]
            tag = combined[-16:]
        else:
            # ChaCha20-Poly1305 (same nonce size)
            chacha = ChaCha20Poly1305(key)
            combined = chacha.encrypt(iv, plaintext, None)
            ct = combined[:-16]
            tag = combined[-16:]
        return iv, tag, ct

    def _sym_decrypt(self, key: bytes, iv: bytes, tag: bytes, ciphertext: bytes) -> bytes:
        combined = ciphertext + tag
        if _PQ_AVAILABLE:
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(iv, combined, None)
        chacha = ChaCha20Poly1305(key)
        return chacha.decrypt(iv, combined, None)
