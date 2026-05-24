"""
Dimensional.infinity.zkp — Zero Knowledge Proof Authentication Module
======================================================================
Phase 23 — Schnorr-based proof of knowledge for privacy-preserving auth.

Implements a self-contained ZKP system using Schnorr-style proofs of knowledge
with NO external cryptographic dependencies. Uses only Python stdlib:
  - hashlib (SHA-256 for commitments and challenges)
  - secrets (cryptographically secure random generation)
  - hmac (keyed hashing for message binding)

Architecture
============

    ┌──────────────────────────────────────────────────────────────────┐
    │                    ZKP Authentication                          │
    │                                                                  │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
    │  │ ZKPProver     │  │ ZKPVerifier  │  │ ZKPRegistry          │  │
    │  │ (generates    │  │ (verifies    │  │ (stores public keys  │  │
    │  │  proofs)      │  │  proofs)     │  │  by entity ID)       │  │
    │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
    │         │                  │                      │              │
    │  ┌──────┴──────────────────┴──────────────────────┴───────────┐  │
    │  │                Proof Generation Flow                       │  │
    │  │                                                             │  │
    │  │  1. Prover generates secret key (x)                        │  │
    │  │  2. Prover computes public key: Y = g^x mod p             │  │
    │  │  3. Prover registers Y with ZKPRegistry                   │  │
    │  │  4. Prover initiates proof:                                │  │
    │  │     a. Commitment: r = g^v mod p (v = random nonce)       │  │
    │  │     b. Challenge: c = H(Y || r || message)                │  │
    │  │     c. Response: s = v - c*x mod q                        │  │
    │  │  5. Verifier checks: r == g^s * Y^c mod p                │  │
    │  └────────────────────────────────────────────────────────────┘  │
    │                                                                  │
    │  ┌────────────────────────────────────────────────────────────┐  │
    │  │  HIL-A Integration                                       │  │
    │  │  ZKP proofs can be attached to EnhancementRequests to     │  │
    │  │  prove tier membership without revealing identity.        │  │
    │  │  Region/location-specific ZKP via HIL-A enhancement.      │  │
    │  └────────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────────┘

Usage
-----
    from Dimensional.infinity.zkp import ZKPProver, ZKPVerifier, ZKPRegistry

    # Setup
    registry = ZKPRegistry()
    prover = ZKPProver(entity_id="agent-001")
    verifier = ZKPVerifier(registry=registry)

    # Registration
    keypair = prover.generate_keypair()
    registry.register("agent-001", keypair.public_key)

    # Proof generation
    proof = prover.create_proof(message="authenticate:infinity-portal")

    # Verification
    result = verifier.verify(proof)
    assert result.valid is True

    # Tier membership proof (prove you're Tier.AI without revealing which AI)
    tier_proof = prover.prove_tier_membership(tier=Tier.AI, shared_secret="tier-ai-secret")
    tier_result = verifier.verify_tier_membership(tier_proof, expected_tier=Tier.AI)
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cryptographic Parameters (Schnorr group — safe primes)
# ---------------------------------------------------------------------------

# Using a well-known safe prime group for Schnorr proofs.
# p = safe prime, q = (p-1)/2, g = generator of order q
# These are medium-security parameters suitable for authentication proofs.
# For production, use larger primes (2048+ bits).

# 256-bit safe prime (p) and its Sophie Germain prime (q = (p-1)/2)
# Generated from a well-known seed for reproducibility
_P = 0xFFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF

_Q = (_P - 1) // 2

# Generator g of order q — g = 2 is a generator for this group
_G = 2


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


def _sha256(*args: bytes) -> int:
    """SHA-256 hash of concatenated bytes, returned as integer."""
    h = hashlib.sha256()
    for a in args:
        h.update(a)
    return int.from_bytes(h.digest(), "big")


def _mod_pow(base: int, exp: int, mod: int) -> int:
    """Modular exponentiation: base^exp mod mod."""
    return pow(base, exp, mod)


def _secure_random(mod: int) -> int:
    """Generate a cryptographically secure random integer in [1, mod-1]."""
    while True:
        r = secrets.randbelow(mod - 1) + 1
        if r > 0:
            return r


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class ZKPKeyPair:
    """A Schnorr key pair for ZKP authentication."""

    entity_id: str
    private_key: int  # x — secret
    public_key: int  # Y = g^x mod p — public
    generator: int = _G
    prime: int = _P
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize public components only (NEVER serialize private key)."""
        return {
            "entity_id": self.entity_id,
            "public_key": str(self.public_key),
            "generator": str(self.generator),
            "prime": str(self.prime),
            "created_at": self.created_at,
        }

    def public_dict(self) -> Dict[str, Any]:
        """Serialize only public components."""
        return self.to_dict()


@dataclass
class ZKPChallenge:
    """A challenge issued by the verifier."""

    challenge_id: str
    entity_id: str
    message: str
    challenge_value: int  # c = H(Y || r || message)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "entity_id": self.entity_id,
            "message": self.message,
            "challenge_value": str(self.challenge_value),
            "timestamp": self.timestamp,
        }


@dataclass
class ZKPResponse:
    """A response from the prover to a challenge."""

    challenge_id: str
    entity_id: str
    commitment: int  # r = g^v mod p
    response_value: int  # s = v - c*x mod q
    public_key: int  # Y = g^x mod p
    message: str
    generator: int = _G
    prime: int = _P
    prime_order: int = _Q
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "entity_id": self.entity_id,
            "commitment": str(self.commitment),
            "response_value": str(self.response_value),
            "public_key": str(self.public_key),
            "message": self.message,
            "generator": str(self.generator),
            "prime": str(self.prime),
            "prime_order": str(self.prime_order),
            "timestamp": self.timestamp,
        }


@dataclass
class ZKPProof:
    """A complete Zero Knowledge Proof — commitment + challenge + response."""

    proof_id: str
    entity_id: str
    message: str
    commitment: int  # r = g^v mod p
    challenge_value: int  # c = H(Y || r || message)
    response_value: int  # s = v - c*x mod q
    public_key: int  # Y = g^x mod p
    generator: int = _G
    prime: int = _P
    prime_order: int = _Q
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "entity_id": self.entity_id,
            "message": self.message,
            "commitment": str(self.commitment),
            "challenge_value": str(self.challenge_value),
            "response_value": str(self.response_value),
            "public_key": str(self.public_key),
            "generator": str(self.generator),
            "prime": str(self.prime),
            "prime_order": str(self.prime_order),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ZKPVerificationResult:
    """Result of verifying a ZKP proof."""

    proof_id: str
    entity_id: str
    valid: bool
    reason: str = ""
    verified_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "entity_id": self.entity_id,
            "valid": self.valid,
            "reason": self.reason,
            "verified_at": self.verified_at,
        }


@dataclass
class TierMembershipProof:
    """A proof of tier membership — proves the entity belongs to a specific tier
    without revealing which entity they are. Uses a shared tier secret."""

    proof_id: str
    entity_id: str  # Pseudonym (not real identity)
    tier: int  # Tier value
    commitment: int
    challenge_value: int
    response_value: int
    public_key: int  # Derived from tier secret, not entity identity
    message: str
    generator: int = _G
    prime: int = _P
    prime_order: int = _Q
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "entity_id": self.entity_id,
            "tier": self.tier,
            "commitment": str(self.commitment),
            "challenge_value": str(self.challenge_value),
            "response_value": str(self.response_value),
            "public_key": str(self.public_key),
            "message": self.message,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# ZKP Registry
# ---------------------------------------------------------------------------


class ZKPRegistry:
    """Stores public keys for ZKP verification. Each entity registers their
    public key here, and verifiers look up the key to verify proofs."""

    def __init__(self):
        self._keys: Dict[str, int] = {}  # entity_id → public_key
        self._key_metadata: Dict[str, Dict[str, Any]] = {}  # entity_id → metadata
        self._tier_secrets: Dict[int, int] = {}  # tier_value → shared_secret

    def register(self, entity_id: str, public_key: int, metadata: Optional[Dict[str, Any]] = None):
        """Register a public key for an entity."""
        self._keys[entity_id] = public_key
        self._key_metadata[entity_id] = metadata or {}
        logger.info("ZKP registry: registered public key for %s", entity_id)

    def get_public_key(self, entity_id: str) -> Optional[int]:
        """Get the public key for an entity."""
        return self._keys.get(entity_id)

    def is_registered(self, entity_id: str) -> bool:
        """Check if an entity is registered."""
        return entity_id in self._keys

    def unregister(self, entity_id: str):
        """Remove an entity's public key from the registry."""
        self._keys.pop(entity_id, None)
        self._key_metadata.pop(entity_id, None)

    def register_tier_secret(self, tier: int, shared_secret: str):
        """Register a shared secret for a tier. This enables tier membership proofs."""
        # Derive a numeric secret from the string
        secret_hash = hashlib.sha256(shared_secret.encode()).digest()
        self._tier_secrets[tier] = int.from_bytes(secret_hash, "big") % _Q
        logger.info("ZKP registry: registered tier secret for tier %d", tier)

    def get_tier_public_key(self, tier: int) -> Optional[int]:
        """Get the public key derived from the tier's shared secret."""
        secret = self._tier_secrets.get(tier)
        if secret is None:
            return None
        return _mod_pow(_G, secret, _P)

    def list_registered(self) -> List[str]:
        """List all registered entity IDs."""
        return list(self._keys.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "registered_entities": len(self._keys),
            "registered_tiers": len(self._tier_secrets),
        }


# ---------------------------------------------------------------------------
# ZKP Prover
# ---------------------------------------------------------------------------


class ZKPProver:
    """Generates Zero Knowledge Proofs using Schnorr-style construction.

    The prover can:
    1. Generate key pairs
    2. Create proof of knowledge (knows private key without revealing it)
    3. Create tier membership proofs (proves tier membership without revealing identity)
    """

    def __init__(self, entity_id: str, keypair: Optional[ZKPKeyPair] = None):
        self.entity_id = entity_id
        self._keypair = keypair

    @property
    def keypair(self) -> Optional[ZKPKeyPair]:
        return self._keypair

    @property
    def is_initialized(self) -> bool:
        return self._keypair is not None

    def generate_keypair(self) -> ZKPKeyPair:
        """Generate a new Schnorr key pair."""
        # Private key: random x in [1, q-1]
        x = _secure_random(_Q)

        # Public key: Y = g^x mod p
        Y = _mod_pow(_G, x, _P)

        self._keypair = ZKPKeyPair(
            entity_id=self.entity_id,
            private_key=x,
            public_key=Y,
        )

        logger.info("ZKP prover: generated keypair for %s", self.entity_id)
        return self._keypair

    def create_proof(self, message: str = "", registry: Optional[ZKPRegistry] = None) -> ZKPProof:
        """Create a Schnorr proof of knowledge.

        Steps:
        1. Choose random nonce v in [1, q-1]
        2. Compute commitment r = g^v mod p
        3. Compute challenge c = H(Y || r || message)
        4. Compute response s = (v - c*x) mod q
        5. Return proof (r, c, s, Y)
        """
        if self._keypair is None:
            raise ValueError("Keypair not initialized. Call generate_keypair() first.")

        # Step 1: Random nonce
        v = _secure_random(_Q)

        # Step 2: Commitment
        r = _mod_pow(_G, v, _P)

        # Step 3: Challenge (Fiat-Shamir heuristic — non-interactive)
        Y_bytes = str(self._keypair.public_key).encode()
        r_bytes = str(r).encode()
        msg_bytes = message.encode() if message else b""
        c = _sha256(Y_bytes, r_bytes, msg_bytes) % _Q

        # Step 4: Response
        s = (v - c * self._keypair.private_key) % _Q

        proof_id = secrets.token_hex(16)

        proof = ZKPProof(
            proof_id=proof_id,
            entity_id=self.entity_id,
            message=message,
            commitment=r,
            challenge_value=c,
            response_value=s,
            public_key=self._keypair.public_key,
            generator=_G,
            prime=_P,
            prime_order=_Q,
        )

        logger.info("ZKP prover: created proof %s for %s", proof_id[:8], self.entity_id)
        return proof

    def prove_tier_membership(
        self,
        tier: int,
        shared_secret: str,
        message: str = "",
    ) -> TierMembershipProof:
        """Prove membership in a specific tier without revealing identity.

        Uses the tier's shared secret to generate a proof that the prover
        knows the secret, without revealing which specific entity they are.
        """
        # Derive the tier secret
        secret_hash = hashlib.sha256(shared_secret.encode()).digest()
        tier_secret = int.from_bytes(secret_hash, "big") % _Q

        # Generate a pseudonym for this proof
        pseudonym = f"tier-{tier}-{secrets.token_hex(4)}"

        # Public key for the tier
        Y_tier = _mod_pow(_G, tier_secret, _P)

        # Random nonce
        v = _secure_random(_Q)

        # Commitment
        r = _mod_pow(_G, v, _P)

        # Challenge
        Y_bytes = str(Y_tier).encode()
        r_bytes = str(r).encode()
        msg_bytes = message.encode() if message else b""
        c = _sha256(Y_bytes, r_bytes, msg_bytes) % _Q

        # Response
        s = (v - c * tier_secret) % _Q

        proof_id = secrets.token_hex(16)

        return TierMembershipProof(
            proof_id=proof_id,
            entity_id=pseudonym,
            tier=tier,
            commitment=r,
            challenge_value=c,
            response_value=s,
            public_key=Y_tier,
            message=message,
        )


# ---------------------------------------------------------------------------
# ZKP Verifier
# ---------------------------------------------------------------------------


class ZKPVerifier:
    """Verifies Zero Knowledge Proofs using Schnorr-style verification.

    The verifier can:
    1. Verify proof of knowledge (verifies prover knows private key)
    2. Verify tier membership proofs (verifies prover belongs to a tier)
    3. Detect tampered/invalid proofs
    """

    def __init__(self, registry: Optional[ZKPRegistry] = None):
        self._registry = registry or ZKPRegistry()
        self._verified_proofs: Set[str] = set()  # Prevent replay attacks

    @property
    def registry(self) -> ZKPRegistry:
        return self._registry

    def verify(self, proof: ZKPProof) -> ZKPVerificationResult:
        """Verify a Schnorr proof of knowledge.

        Verification:
        1. Recompute challenge: c' = H(Y || r || message)
        2. Check: g^s * Y^c == r (mod p)
        """
        # Check for replay attacks
        if proof.proof_id in self._verified_proofs:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Proof has already been used (replay attack detected)",
            )

        # Verify the prover is registered (if we have a registry)
        if self._registry.is_registered(proof.entity_id):
            expected_key = self._registry.get_public_key(proof.entity_id)
            if expected_key != proof.public_key:
                return ZKPVerificationResult(
                    proof_id=proof.proof_id,
                    entity_id=proof.entity_id,
                    valid=False,
                    reason="Public key mismatch — entity may have been re-registered",
                )

        # Step 1: Recompute challenge
        Y_bytes = str(proof.public_key).encode()
        r_bytes = str(proof.commitment).encode()
        msg_bytes = proof.message.encode() if proof.message else b""
        c_computed = _sha256(Y_bytes, r_bytes, msg_bytes) % proof.prime_order

        # Step 2: Verify challenge matches
        if c_computed != proof.challenge_value:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Challenge mismatch — proof may be tampered",
            )

        # Step 3: Verify g^s * Y^c == r (mod p)
        g_s = _mod_pow(proof.generator, proof.response_value, proof.prime)
        Y_c = _mod_pow(proof.public_key, proof.challenge_value, proof.prime)
        lhs = (g_s * Y_c) % proof.prime
        rhs = proof.commitment

        if lhs != rhs:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Verification equation failed — invalid proof",
            )

        # Mark as verified (prevent replay)
        self._verified_proofs.add(proof.proof_id)

        logger.info("ZKP verifier: proof %s verified for %s", proof.proof_id[:8], proof.entity_id)
        return ZKPVerificationResult(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            valid=True,
            reason="Proof verified successfully",
        )

    def verify_tier_membership(
        self,
        proof: TierMembershipProof,
        expected_tier: Optional[int] = None,
    ) -> ZKPVerificationResult:
        """Verify a tier membership proof."""
        # Check tier match
        if expected_tier is not None and proof.tier != expected_tier:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason=f"Tier mismatch: expected {expected_tier}, got {proof.tier}",
            )

        # Check for replay
        if proof.proof_id in self._verified_proofs:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Proof has already been used (replay attack detected)",
            )

        # Verify against the tier's public key
        tier_public_key = self._registry.get_tier_public_key(proof.tier)
        if tier_public_key is None:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason=f"No tier secret registered for tier {proof.tier}",
            )

        if proof.public_key != tier_public_key:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Public key mismatch for tier",
            )

        # Verify the Schnorr proof
        Y_bytes = str(proof.public_key).encode()
        r_bytes = str(proof.commitment).encode()
        msg_bytes = proof.message.encode() if proof.message else b""
        c_computed = _sha256(Y_bytes, r_bytes, msg_bytes) % proof.prime_order

        if c_computed != proof.challenge_value:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Challenge mismatch in tier proof",
            )

        # Verify equation
        g_s = _mod_pow(proof.generator, proof.response_value, proof.prime)
        Y_c = _mod_pow(proof.public_key, proof.challenge_value, proof.prime)
        lhs = (g_s * Y_c) % proof.prime
        rhs = proof.commitment

        if lhs != rhs:
            return ZKPVerificationResult(
                proof_id=proof.proof_id,
                entity_id=proof.entity_id,
                valid=False,
                reason="Verification equation failed in tier proof",
            )

        self._verified_proofs.add(proof.proof_id)

        logger.info(
            "ZKP verifier: tier membership proof %s verified for %s (tier %d)",
            proof.proof_id[:8],
            proof.entity_id,
            proof.tier,
        )
        return ZKPVerificationResult(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            valid=True,
            reason="Tier membership proof verified successfully",
        )

    def is_proof_used(self, proof_id: str) -> bool:
        """Check if a proof ID has already been used."""
        return proof_id in self._verified_proofs

    def get_stats(self) -> Dict[str, Any]:
        """Get verifier statistics."""
        return {
            "verified_proofs": len(self._verified_proofs),
            "registered_entities": self._registry.get_stats()["registered_entities"],
            "registered_tiers": self._registry.get_stats()["registered_tiers"],
        }


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


def create_zkp_session(entity_id: str, registry: Optional[ZKPRegistry] = None) -> tuple:
    """Create a complete ZKP session (prover + keypair + registration).

    Returns (prover, registry) tuple.
    """
    reg = registry or ZKPRegistry()
    prover = ZKPProver(entity_id=entity_id)
    keypair = prover.generate_keypair()
    reg.register(entity_id, keypair.public_key)
    return prover, reg


def verify_zkp_auth(
    entity_id: str,
    message: str,
    registry: ZKPRegistry,
    prover: ZKPProver,
) -> ZKPVerificationResult:
    """Convenience function: prover creates proof, verifier verifies it."""
    proof = prover.create_proof(message=message)
    verifier = ZKPVerifier(registry=registry)
    return verifier.verify(proof)
