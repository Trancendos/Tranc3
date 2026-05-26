"""
tests.test_zkp — Comprehensive tests for the ZKP Authentication Module
======================================================================
Phase 23.3 — Tests cover:
  - Cryptographic utility functions
  - ZKPKeyPair generation and serialization
  - ZKPChallenge / ZKPResponse / ZKPProof data classes
  - ZKPRegistry: register, unregister, lookup, tier secrets, stats
  - ZKPProver: keypair generation, proof creation, tier membership proofs
  - ZKPVerifier: proof verification, tamper detection, replay attacks
  - Tier membership proof creation and verification
  - Convenience functions (create_zkp_session, verify_zkp_auth)
  - Edge cases: uninitialized prover, missing registry entries, wrong keys
  - Schnorr verification equation: g^s * Y^c == r (mod p)
"""

import hashlib
import time

import pytest

from Dimensional.infinity.zkp import (
    _G,
    _P,
    _Q,
    TierMembershipProof,
    ZKPChallenge,
    ZKPKeyPair,
    ZKPProof,
    ZKPProver,
    ZKPRegistry,
    ZKPResponse,
    ZKPVerificationResult,
    ZKPVerifier,
    _mod_pow,
    _secure_random,
    _sha256,
    create_zkp_session,
    verify_zkp_auth,
)

# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


class TestSHA256:
    """Tests for the _sha256 utility function."""

    def test_deterministic(self):
        """Same input produces same output."""
        a = _sha256(b"hello", b"world")
        b = _sha256(b"hello", b"world")
        assert a == b

    def test_different_inputs_differ(self):
        """Different inputs produce different outputs."""
        a = _sha256(b"hello")
        b = _sha256(b"world")
        assert a != b

    def test_order_matters(self):
        """Order of arguments affects the hash."""
        a = _sha256(b"hello", b"world")
        b = _sha256(b"world", b"hello")
        assert a != b

    def test_empty_input(self):
        """Empty input still produces a valid hash."""
        result = _sha256(b"")
        assert isinstance(result, int)
        assert result > 0

    def test_no_args(self):
        """No arguments still produces a valid hash."""
        result = _sha256()
        assert isinstance(result, int)
        assert result > 0

    def test_returns_int(self):
        """Result is always an integer."""
        result = _sha256(b"test")
        assert isinstance(result, int)

    def test_matches_hashlib(self):
        """Result matches manual SHA-256 computation."""
        h = hashlib.sha256()
        h.update(b"hello")
        h.update(b"world")
        expected = int.from_bytes(h.digest(), "big")
        assert _sha256(b"hello", b"world") == expected


class TestModPow:
    """Tests for the _mod_pow utility function."""

    def test_basic(self):
        """2^10 mod 1000 = 1024 mod 1000 = 24."""
        assert _mod_pow(2, 10, 1000) == 24

    def test_identity(self):
        """x^1 mod m = x mod m."""
        assert _mod_pow(7, 1, 100) == 7

    def test_zero_exp(self):
        """x^0 mod m = 1 for any x (when m > 1)."""
        assert _mod_pow(5, 0, 100) == 1

    def test_large_numbers(self):
        """Works with the actual large prime P."""
        result = _mod_pow(2, 100, _P)
        assert isinstance(result, int)
        assert 0 <= result < _P

    def test_python_pow_equivalence(self):
        """Matches Python's built-in pow(base, exp, mod)."""
        for base in [2, 7, 100, 9999]:
            for exp in [0, 1, 10, 100]:
                assert _mod_pow(base, exp, _P) == pow(base, exp, _P)


class TestSecureRandom:
    """Tests for the _secure_random utility function."""

    def test_in_range(self):
        """Result is always in [1, mod-1]."""
        for _ in range(50):
            r = _secure_random(_Q)
            assert 1 <= r < _Q

    def test_never_zero(self):
        """Result is never zero."""
        for _ in range(50):
            r = _secure_random(_Q)
            assert r != 0

    def test_different_each_call(self):
        """Subsequent calls produce different values (with overwhelming probability)."""
        values = {_secure_random(_Q) for _ in range(20)}
        # With 256-bit random values, collisions are astronomically unlikely
        assert len(values) == 20

    def test_small_modulus(self):
        """Works with small modulus."""
        r = _secure_random(10)
        assert 1 <= r < 10


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


class TestZKPKeyPair:
    """Tests for the ZKPKeyPair dataclass."""

    def test_creation(self):
        """Keypair can be created with required fields."""
        kp = ZKPKeyPair(entity_id="test", private_key=123, public_key=456)
        assert kp.entity_id == "test"
        assert kp.private_key == 123
        assert kp.public_key == 456

    def test_defaults(self):
        """Generator and prime default to module constants."""
        kp = ZKPKeyPair(entity_id="test", private_key=1, public_key=2)
        assert kp.generator == _G
        assert kp.prime == _P
        assert kp.created_at > 0

    def test_to_dict(self):
        """to_dict() serializes public components only (not private key)."""
        kp = ZKPKeyPair(entity_id="agent-1", private_key=999, public_key=888)
        d = kp.to_dict()
        assert d["entity_id"] == "agent-1"
        assert d["public_key"] == "888"
        # Private key should NEVER appear in the dict
        assert "private_key" not in d

    def test_public_dict_same_as_to_dict(self):
        """public_dict() returns same as to_dict()."""
        kp = ZKPKeyPair(entity_id="test", private_key=1, public_key=2)
        assert kp.public_dict() == kp.to_dict()

    def test_to_dict_types(self):
        """to_dict() values have correct types."""
        kp = ZKPKeyPair(entity_id="test", private_key=1, public_key=2)
        d = kp.to_dict()
        assert isinstance(d["entity_id"], str)
        assert isinstance(d["public_key"], str)  # Large ints serialized as strings
        assert isinstance(d["created_at"], float)


class TestZKPChallenge:
    """Tests for the ZKPChallenge dataclass."""

    def test_creation(self):
        """Challenge can be created with required fields."""
        c = ZKPChallenge(
            challenge_id="ch-1",
            entity_id="agent-1",
            message="auth",
            challenge_value=42,
        )
        assert c.challenge_id == "ch-1"
        assert c.entity_id == "agent-1"
        assert c.message == "auth"
        assert c.challenge_value == 42

    def test_to_dict(self):
        """to_dict() serializes correctly."""
        c = ZKPChallenge(
            challenge_id="ch-1",
            entity_id="agent-1",
            message="auth",
            challenge_value=42,
        )
        d = c.to_dict()
        assert d["challenge_id"] == "ch-1"
        assert d["challenge_value"] == "42"  # Serialized as string


class TestZKPResponse:
    """Tests for the ZKPResponse dataclass."""

    def test_creation(self):
        """Response can be created with required fields."""
        r = ZKPResponse(
            challenge_id="ch-1",
            entity_id="agent-1",
            commitment=100,
            response_value=200,
            public_key=300,
            message="auth",
        )
        assert r.challenge_id == "ch-1"
        assert r.commitment == 100
        assert r.response_value == 200

    def test_to_dict(self):
        """to_dict() serializes correctly."""
        r = ZKPResponse(
            challenge_id="ch-1",
            entity_id="agent-1",
            commitment=100,
            response_value=200,
            public_key=300,
            message="auth",
        )
        d = r.to_dict()
        assert d["commitment"] == "100"
        assert d["response_value"] == "200"
        assert d["public_key"] == "300"


class TestZKPProof:
    """Tests for the ZKPProof dataclass."""

    def test_creation(self):
        """Proof can be created with required fields."""
        p = ZKPProof(
            proof_id="pf-1",
            entity_id="agent-1",
            message="auth",
            commitment=100,
            challenge_value=42,
            response_value=200,
            public_key=300,
        )
        assert p.proof_id == "pf-1"
        assert p.entity_id == "agent-1"
        assert p.message == "auth"

    def test_defaults(self):
        """Default values are set correctly."""
        p = ZKPProof(
            proof_id="pf-1",
            entity_id="agent-1",
            message="",
            commitment=1,
            challenge_value=1,
            response_value=1,
            public_key=1,
        )
        assert p.generator == _G
        assert p.prime == _P
        assert p.prime_order == _Q
        assert p.metadata == {}

    def test_to_dict(self):
        """to_dict() serializes all fields correctly."""
        p = ZKPProof(
            proof_id="pf-1",
            entity_id="agent-1",
            message="auth",
            commitment=100,
            challenge_value=42,
            response_value=200,
            public_key=300,
            metadata={"key": "value"},
        )
        d = p.to_dict()
        assert d["proof_id"] == "pf-1"
        assert d["commitment"] == "100"
        assert d["challenge_value"] == "42"
        assert d["response_value"] == "200"
        assert d["public_key"] == "300"
        assert d["metadata"] == {"key": "value"}


class TestZKPVerificationResult:
    """Tests for the ZKPVerificationResult dataclass."""

    def test_valid_result(self):
        """Valid result creation."""
        r = ZKPVerificationResult(
            proof_id="pf-1",
            entity_id="agent-1",
            valid=True,
            reason="OK",
        )
        assert r.valid is True
        assert r.reason == "OK"

    def test_invalid_result(self):
        """Invalid result creation."""
        r = ZKPVerificationResult(
            proof_id="pf-1",
            entity_id="agent-1",
            valid=False,
            reason="Failed",
        )
        assert r.valid is False

    def test_to_dict(self):
        """to_dict() serializes correctly."""
        r = ZKPVerificationResult(
            proof_id="pf-1",
            entity_id="agent-1",
            valid=True,
            reason="OK",
        )
        d = r.to_dict()
        assert d["valid"] is True
        assert d["reason"] == "OK"


class TestTierMembershipProof:
    """Tests for the TierMembershipProof dataclass."""

    def test_creation(self):
        """TierMembershipProof can be created with required fields."""
        p = TierMembershipProof(
            proof_id="tp-1",
            entity_id="pseudonym",
            tier=3,
            commitment=100,
            challenge_value=42,
            response_value=200,
            public_key=300,
            message="auth",
        )
        assert p.proof_id == "tp-1"
        assert p.tier == 3
        assert p.entity_id == "pseudonym"

    def test_to_dict(self):
        """to_dict() serializes correctly."""
        p = TierMembershipProof(
            proof_id="tp-1",
            entity_id="pseudonym",
            tier=3,
            commitment=100,
            challenge_value=42,
            response_value=200,
            public_key=300,
            message="auth",
        )
        d = p.to_dict()
        assert d["tier"] == 3
        assert d["commitment"] == "100"
        assert d["entity_id"] == "pseudonym"


# ---------------------------------------------------------------------------
# ZKP Registry
# ---------------------------------------------------------------------------


class TestZKPRegistry:
    """Tests for the ZKPRegistry class."""

    def test_register_and_get(self):
        """Can register a public key and retrieve it."""
        reg = ZKPRegistry()
        reg.register("agent-1", 12345)
        assert reg.get_public_key("agent-1") == 12345

    def test_get_unregistered(self):
        """Getting an unregistered entity returns None."""
        reg = ZKPRegistry()
        assert reg.get_public_key("nonexistent") is None

    def test_is_registered(self):
        """is_registered() correctly reports registration status."""
        reg = ZKPRegistry()
        assert reg.is_registered("agent-1") is False
        reg.register("agent-1", 99999)
        assert reg.is_registered("agent-1") is True

    def test_unregister(self):
        """Unregistering removes the entity."""
        reg = ZKPRegistry()
        reg.register("agent-1", 12345)
        reg.unregister("agent-1")
        assert reg.is_registered("agent-1") is False
        assert reg.get_public_key("agent-1") is None

    def test_unregister_nonexistent(self):
        """Unregistering a non-existent entity is a no-op."""
        reg = ZKPRegistry()
        reg.unregister("ghost")  # Should not raise

    def test_register_overwrite(self):
        """Re-registering overwrites the previous key."""
        reg = ZKPRegistry()
        reg.register("agent-1", 100)
        reg.register("agent-1", 200)
        assert reg.get_public_key("agent-1") == 200

    def test_register_with_metadata(self):
        """Can register with metadata."""
        reg = ZKPRegistry()
        reg.register("agent-1", 100, metadata={"tier": 3})
        # Metadata is stored but not directly accessible via public API
        # Just verify it doesn't crash

    def test_list_registered(self):
        """list_registered() returns all entity IDs."""
        reg = ZKPRegistry()
        reg.register("a", 1)
        reg.register("b", 2)
        reg.register("c", 3)
        ids = reg.list_registered()
        assert sorted(ids) == ["a", "b", "c"]

    def test_list_registered_empty(self):
        """list_registered() returns empty list when nothing is registered."""
        reg = ZKPRegistry()
        assert reg.list_registered() == []

    def test_get_stats(self):
        """get_stats() returns correct counts."""
        reg = ZKPRegistry()
        reg.register("a", 1)
        reg.register("b", 2)
        stats = reg.get_stats()
        assert stats["registered_entities"] == 2
        assert stats["registered_tiers"] == 0

    def test_register_tier_secret(self):
        """Can register a tier secret and retrieve the tier public key."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="tier-3-secret")
        pub_key = reg.get_tier_public_key(3)
        assert pub_key is not None
        # Tier public key should be g^secret mod p
        secret_hash = hashlib.sha256("tier-3-secret".encode()).digest()
        expected_secret = int.from_bytes(secret_hash, "big") % _Q
        expected_key = pow(_G, expected_secret, _P)
        assert pub_key == expected_key

    def test_get_tier_public_key_unregistered(self):
        """Getting public key for unregistered tier returns None."""
        reg = ZKPRegistry()
        assert reg.get_tier_public_key(99) is None

    def test_tier_secret_in_stats(self):
        """Tier secrets are counted in stats."""
        reg = ZKPRegistry()
        reg.register_tier_secret(3, "secret-3")
        reg.register_tier_secret(2, "secret-2")
        stats = reg.get_stats()
        assert stats["registered_tiers"] == 2

    def test_register_multiple_entities(self):
        """Multiple entities can be registered independently."""
        reg = ZKPRegistry()
        prover1 = ZKPProver("entity-1")
        prover2 = ZKPProver("entity-2")
        kp1 = prover1.generate_keypair()
        kp2 = prover2.generate_keypair()
        reg.register("entity-1", kp1.public_key)
        reg.register("entity-2", kp2.public_key)
        assert reg.get_public_key("entity-1") == kp1.public_key
        assert reg.get_public_key("entity-2") == kp2.public_key


# ---------------------------------------------------------------------------
# ZKP Prover
# ---------------------------------------------------------------------------


class TestZKPProver:
    """Tests for the ZKPProver class."""

    def test_init(self):
        """Prover can be initialized with entity_id."""
        prover = ZKPProver(entity_id="agent-1")
        assert prover.entity_id == "agent-1"
        assert prover.keypair is None
        assert prover.is_initialized is False

    def test_init_with_keypair(self):
        """Prover can be initialized with an existing keypair."""
        kp = ZKPKeyPair(entity_id="agent-1", private_key=1, public_key=2)
        prover = ZKPProver(entity_id="agent-1", keypair=kp)
        assert prover.is_initialized is True
        assert prover.keypair is kp

    def test_generate_keypair(self):
        """generate_keypair() creates a valid keypair."""
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        assert kp.entity_id == "agent-1"
        assert kp.private_key > 0
        assert kp.public_key > 0
        assert prover.is_initialized is True

    def test_generate_keypair_different_each_time(self):
        """Each keypair generation produces different keys."""
        prover = ZKPProver(entity_id="agent-1")
        kp1 = prover.generate_keypair()
        kp2 = prover.generate_keypair()
        assert kp1.private_key != kp2.private_key
        assert kp1.public_key != kp2.public_key

    def test_keypair_public_key_consistent(self):
        """Public key Y = g^x mod p for the generated private key x."""
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        expected_Y = pow(_G, kp.private_key, _P)
        assert kp.public_key == expected_Y

    def test_create_proof_without_keypair_raises(self):
        """create_proof() raises ValueError if keypair not initialized."""
        prover = ZKPProver(entity_id="agent-1")
        with pytest.raises(ValueError, match="Keypair not initialized"):
            prover.create_proof(message="test")

    def test_create_proof(self):
        """create_proof() produces a valid ZKPProof."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="authenticate")
        assert isinstance(proof, ZKPProof)
        assert proof.entity_id == "agent-1"
        assert proof.message == "authenticate"
        assert proof.commitment > 0
        assert proof.challenge_value > 0
        assert proof.response_value >= 0  # Can be 0 if v == c*x
        assert proof.public_key > 0
        assert proof.proof_id  # Non-empty string

    def test_create_proof_deterministic_challenge(self):
        """Same inputs produce the same challenge value."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        # Create two proofs — commitments will differ (different nonce),
        # but the structure should be consistent
        proof1 = prover.create_proof(message="test")
        proof2 = prover.create_proof(message="test")
        # Different nonces → different commitments → different challenges
        assert proof1.proof_id != proof2.proof_id
        assert proof1.commitment != proof2.commitment

    def test_proof_schnorr_equation(self):
        """Verify the Schnorr equation: g^s * Y^c == r (mod p)."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="verify-me")

        # g^s mod p
        g_s = pow(proof.generator, proof.response_value, proof.prime)
        # Y^c mod p
        Y_c = pow(proof.public_key, proof.challenge_value, proof.prime)
        # g^s * Y^c mod p
        lhs = (g_s * Y_c) % proof.prime
        # Should equal r (commitment)
        assert lhs == proof.commitment

    def test_create_proof_empty_message(self):
        """create_proof() works with empty message."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="")
        assert proof.message == ""
        # Should still satisfy the Schnorr equation
        g_s = pow(proof.generator, proof.response_value, proof.prime)
        Y_c = pow(proof.public_key, proof.challenge_value, proof.prime)
        lhs = (g_s * Y_c) % proof.prime
        assert lhs == proof.commitment

    def test_create_proof_default_message(self):
        """create_proof() works with default (no) message."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof()
        assert proof.message == ""


# ---------------------------------------------------------------------------
# ZKP Verifier
# ---------------------------------------------------------------------------


class TestZKPVerifier:
    """Tests for the ZKPVerifier class."""

    def test_init_default(self):
        """Verifier can be initialized without a registry."""
        verifier = ZKPVerifier()
        assert verifier.registry is not None

    def test_init_with_registry(self):
        """Verifier can be initialized with a specific registry."""
        reg = ZKPRegistry()
        verifier = ZKPVerifier(registry=reg)
        assert verifier.registry is reg

    def test_verify_valid_proof(self):
        """Valid proof verifies successfully."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")
        result = verifier.verify(proof)
        assert result.valid is True
        assert result.entity_id == "agent-1"
        assert "verified successfully" in result.reason.lower()

    def test_verify_proof_not_in_registry(self):
        """Proof from unregistered entity still verifies (registry is optional)."""
        prover = ZKPProver(entity_id="unregistered")
        prover.generate_keypair()
        # No registry registration
        reg = ZKPRegistry()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")
        result = verifier.verify(proof)
        # Should still verify because the Schnorr equation holds
        assert result.valid is True

    def test_verify_tampered_commitment(self):
        """Tampered commitment causes verification to fail."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")
        # Tamper with commitment
        tampered = ZKPProof(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            message=proof.message,
            commitment=proof.commitment + 1,  # Changed!
            challenge_value=proof.challenge_value,
            response_value=proof.response_value,
            public_key=proof.public_key,
        )
        result = verifier.verify(tampered)
        assert result.valid is False

    def test_verify_tampered_response(self):
        """Tampered response value causes verification to fail."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier()

        proof = prover.create_proof(message="auth")
        tampered = ZKPProof(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            message=proof.message,
            commitment=proof.commitment,
            challenge_value=proof.challenge_value,
            response_value=proof.response_value + 1,  # Changed!
            public_key=proof.public_key,
        )
        result = verifier.verify(tampered)
        assert result.valid is False

    def test_verify_tampered_public_key(self):
        """Tampered public key causes verification to fail."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier()

        proof = prover.create_proof(message="auth")
        tampered = ZKPProof(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            message=proof.message,
            commitment=proof.commitment,
            challenge_value=proof.challenge_value,
            response_value=proof.response_value,
            public_key=proof.public_key + 1,  # Changed!
        )
        result = verifier.verify(tampered)
        assert result.valid is False

    def test_verify_tampered_message(self):
        """Tampered message causes challenge mismatch."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier()

        proof = prover.create_proof(message="original")
        tampered = ZKPProof(
            proof_id=proof.proof_id,
            entity_id=proof.entity_id,
            message="tampered",  # Changed!
            commitment=proof.commitment,
            challenge_value=proof.challenge_value,
            response_value=proof.response_value,
            public_key=proof.public_key,
        )
        result = verifier.verify(tampered)
        assert result.valid is False

    def test_verify_replay_attack(self):
        """Same proof cannot be verified twice (replay attack detection)."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")

        # First verification succeeds
        result1 = verifier.verify(proof)
        assert result1.valid is True

        # Second verification fails (replay)
        result2 = verifier.verify(proof)
        assert result2.valid is False
        assert "replay" in result2.reason.lower()

    def test_verify_different_verifiers_independent(self):
        """Different verifiers maintain independent replay tracking."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)

        proof = prover.create_proof(message="auth")

        verifier1 = ZKPVerifier(registry=reg)
        verifier2 = ZKPVerifier(registry=reg)

        result1 = verifier1.verify(proof)
        result2 = verifier2.verify(proof)
        # Both should succeed — different verifier instances
        assert result1.valid is True
        assert result2.valid is True

    def test_verify_public_key_mismatch(self):
        """Public key mismatch with registry causes failure."""
        reg = ZKPRegistry()
        # Register a different key for agent-1
        reg.register("agent-1", 99999)

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")
        result = verifier.verify(proof)
        assert result.valid is False
        assert "mismatch" in result.reason.lower()

    def test_is_proof_used(self):
        """is_proof_used() correctly tracks verified proofs."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier()

        proof = prover.create_proof(message="auth")
        assert verifier.is_proof_used(proof.proof_id) is False

        verifier.verify(proof)
        assert verifier.is_proof_used(proof.proof_id) is True

    def test_get_stats(self):
        """get_stats() returns correct counts."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)
        verifier = ZKPVerifier(registry=reg)

        proof = prover.create_proof(message="auth")
        verifier.verify(proof)

        stats = verifier.get_stats()
        assert stats["verified_proofs"] == 1
        assert stats["registered_entities"] == 1


# ---------------------------------------------------------------------------
# Tier Membership Proofs
# ---------------------------------------------------------------------------


class TestTierMembershipProofs:
    """Tests for tier membership proof creation and verification."""

    def test_prove_tier_membership(self):
        """Can create a tier membership proof."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")
        assert isinstance(proof, TierMembershipProof)
        assert proof.tier == 3
        assert proof.commitment > 0
        assert proof.challenge_value > 0
        assert proof.response_value >= 0
        assert proof.public_key > 0
        # Entity ID should be a pseudonym, not the real ID
        assert proof.entity_id != "agent-1"
        assert proof.entity_id.startswith("tier-3-")

    def test_verify_tier_membership(self):
        """Tier membership proof can be verified."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="tier-3-secret")

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")
        result = verifier.verify_tier_membership(proof, expected_tier=3)
        assert result.valid is True

    def test_verify_tier_membership_wrong_tier(self):
        """Tier membership proof fails when expected tier doesn't match."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="tier-3-secret")

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")
        result = verifier.verify_tier_membership(proof, expected_tier=2)
        assert result.valid is False
        assert "mismatch" in result.reason.lower()

    def test_verify_tier_membership_no_secret_registered(self):
        """Tier membership verification fails when tier secret not registered."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")
        result = verifier.verify_tier_membership(proof, expected_tier=3)
        assert result.valid is False
        assert "no tier secret" in result.reason.lower()

    def test_verify_tier_membership_wrong_secret(self):
        """Tier membership proof fails when using wrong shared secret."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="correct-secret")

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        # Use wrong secret
        proof = prover.prove_tier_membership(tier=3, shared_secret="wrong-secret")
        result = verifier.verify_tier_membership(proof, expected_tier=3)
        assert result.valid is False

    def test_verify_tier_membership_no_expected(self):
        """Tier membership verification works without specifying expected_tier."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="tier-3-secret")

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")
        result = verifier.verify_tier_membership(proof)  # No expected_tier
        assert result.valid is True

    def test_tier_proof_schnorr_equation(self):
        """Tier membership proof satisfies the Schnorr verification equation."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")

        # g^s * Y^c == r (mod p)
        g_s = pow(proof.generator, proof.response_value, proof.prime)
        Y_c = pow(proof.public_key, proof.challenge_value, proof.prime)
        lhs = (g_s * Y_c) % proof.prime
        assert lhs == proof.commitment

    def test_tier_proof_pseudonym_unique(self):
        """Each tier membership proof gets a unique pseudonym."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof1 = prover.prove_tier_membership(tier=3, shared_secret="secret")
        proof2 = prover.prove_tier_membership(tier=3, shared_secret="secret")
        assert proof1.entity_id != proof2.entity_id
        assert proof1.proof_id != proof2.proof_id

    def test_multiple_tiers(self):
        """Can create and verify proofs for multiple tiers."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=2, shared_secret="prime-secret")
        reg.register_tier_secret(tier=3, shared_secret="ai-secret")
        reg.register_tier_secret(tier=4, shared_secret="agent-secret")

        prover = ZKPProver(entity_id="entity")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        for tier_val, secret in [(2, "prime-secret"), (3, "ai-secret"), (4, "agent-secret")]:
            proof = prover.prove_tier_membership(tier=tier_val, shared_secret=secret)
            result = verifier.verify_tier_membership(proof, expected_tier=tier_val)
            assert result.valid is True, f"Tier {tier_val} proof failed: {result.reason}"

    def test_tier_proof_replay_detection(self):
        """Tier membership proofs are subject to replay detection."""
        reg = ZKPRegistry()
        reg.register_tier_secret(tier=3, shared_secret="tier-3-secret")

        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier(registry=reg)

        proof = prover.prove_tier_membership(tier=3, shared_secret="tier-3-secret")

        result1 = verifier.verify_tier_membership(proof, expected_tier=3)
        assert result1.valid is True

        result2 = verifier.verify_tier_membership(proof, expected_tier=3)
        assert result2.valid is False
        assert "replay" in result2.reason.lower()


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


class TestCreateZKPSession:
    """Tests for the create_zkp_session() convenience function."""

    def test_basic(self):
        """create_zkp_session() returns a prover and registry."""
        prover, reg = create_zkp_session("agent-1")
        assert isinstance(prover, ZKPProver)
        assert isinstance(reg, ZKPRegistry)
        assert prover.is_initialized is True
        assert reg.is_registered("agent-1") is True

    def test_with_existing_registry(self):
        """create_zkp_session() can use an existing registry."""
        reg = ZKPRegistry()
        prover, same_reg = create_zkp_session("agent-1", registry=reg)
        assert same_reg is reg
        assert reg.is_registered("agent-1") is True

    def test_keypair_registered(self):
        """The generated keypair's public key is registered."""
        prover, reg = create_zkp_session("agent-1")
        registered_key = reg.get_public_key("agent-1")
        assert registered_key == prover.keypair.public_key

    def test_can_create_proof_after_session(self):
        """After creating a session, prover can create valid proofs."""
        prover, reg = create_zkp_session("agent-1")
        proof = prover.create_proof(message="test")
        verifier = ZKPVerifier(registry=reg)
        result = verifier.verify(proof)
        assert result.valid is True


class TestVerifyZKPAuth:
    """Tests for the verify_zkp_auth() convenience function."""

    def test_basic(self):
        """verify_zkp_auth() creates and verifies a proof."""
        prover, reg = create_zkp_session("agent-1")
        result = verify_zkp_auth(
            entity_id="agent-1",
            message="authenticate",
            registry=reg,
            prover=prover,
        )
        assert result.valid is True

    def test_different_messages(self):
        """Different messages produce different proofs but all verify."""
        prover, reg = create_zkp_session("agent-1")
        for msg in ["auth", "login", "transfer"]:
            result = verify_zkp_auth(
                entity_id="agent-1",
                message=msg,
                registry=reg,
                prover=prover,
            )
            assert result.valid is True


# ---------------------------------------------------------------------------
# End-to-End Integration
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end integration tests for the full ZKP workflow."""

    def test_full_workflow(self):
        """Complete workflow: generate keypair → register → prove → verify."""
        # Setup
        registry = ZKPRegistry()
        prover = ZKPProver(entity_id="infinity-agent")
        verifier = ZKPVerifier(registry=registry)

        # Generate and register
        keypair = prover.generate_keypair()
        registry.register("infinity-agent", keypair.public_key)

        # Create proof
        proof = prover.create_proof(message="access:infinity-portal")

        # Verify
        result = verifier.verify(proof)
        assert result.valid is True
        assert result.entity_id == "infinity-agent"

    def test_multiple_provers(self):
        """Multiple provers can register and verify independently."""
        registry = ZKPRegistry()

        provers = []
        for i in range(5):
            p = ZKPProver(entity_id=f"agent-{i}")
            kp = p.generate_keypair()
            registry.register(f"agent-{i}", kp.public_key)
            provers.append(p)

        verifier = ZKPVerifier(registry=registry)

        for i, prover in enumerate(provers):
            proof = prover.create_proof(message=f"auth-{i}")
            result = verifier.verify(proof)
            assert result.valid is True, f"Agent {i} proof failed"

    def test_full_workflow_with_tier_proofs(self):
        """Complete workflow with tier membership proofs."""
        registry = ZKPRegistry()
        registry.register_tier_secret(tier=3, shared_secret="ai-tier-secret")
        registry.register_tier_secret(tier=2, shared_secret="prime-tier-secret")

        prover = ZKPProver(entity_id="ai-agent")
        keypair = prover.generate_keypair()
        registry.register("ai-agent", keypair.public_key)

        verifier = ZKPVerifier(registry=registry)

        # Standard proof
        std_proof = prover.create_proof(message="authenticate")
        std_result = verifier.verify(std_proof)
        assert std_result.valid is True

        # Tier membership proof
        tier_proof = prover.prove_tier_membership(tier=3, shared_secret="ai-tier-secret")
        tier_result = verifier.verify_tier_membership(tier_proof, expected_tier=3)
        assert tier_result.valid is True

    def test_tampered_proof_fails_verification(self):
        """Any tampered field causes verification failure."""
        registry = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        registry.register("agent-1", kp.public_key)
        verifier = ZKPVerifier(registry=registry)

        proof = prover.create_proof(message="secure-action")

        # Test tampering each field
        tampered_fields = {
            "commitment": proof.commitment + 1,
            "challenge_value": proof.challenge_value + 1,
            "response_value": proof.response_value + 1,
            "public_key": proof.public_key + 1,
            "message": "tampered-message",
        }

        for field, tampered_value in tampered_fields.items():
            kwargs = {
                "proof_id": proof.proof_id,
                "entity_id": proof.entity_id,
                "message": proof.message,
                "commitment": proof.commitment,
                "challenge_value": proof.challenge_value,
                "response_value": proof.response_value,
                "public_key": proof.public_key,
            }
            kwargs[field] = tampered_value

            tampered = ZKPProof(**kwargs)
            result = verifier.verify(tampered)
            assert result.valid is False, f"Tampered {field} should fail verification"

    def test_serialization_round_trip(self):
        """Proof can be serialized and deserialized (via to_dict)."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="round-trip")

        d = proof.to_dict()
        assert d["entity_id"] == "agent-1"
        assert d["message"] == "round-trip"
        # All int fields should be serialized as strings
        for key in ["commitment", "challenge_value", "response_value", "public_key"]:
            assert isinstance(d[key], str), f"{key} should be string in dict"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_zero_cost_model_keypair(self):
        """Keypair with minimal values still works structurally."""
        kp = ZKPKeyPair(entity_id="min", private_key=1, public_key=pow(_G, 1, _P))
        assert kp.private_key == 1
        assert kp.public_key == pow(_G, 1, _P)

    def test_prover_without_keypair(self):
        """Prover without keypair cannot create proofs."""
        prover = ZKPProver(entity_id="uninitialized")
        with pytest.raises(ValueError):
            prover.create_proof()

    def test_prover_without_keypair_tier_proof(self):
        """Prover without keypair CAN create tier proofs (doesn't need entity keypair)."""
        prover = ZKPProver(entity_id="uninitialized")
        # prove_tier_membership uses the tier secret, not the entity keypair
        proof = prover.prove_tier_membership(tier=3, shared_secret="secret")
        assert isinstance(proof, TierMembershipProof)
        assert proof.tier == 3

    def test_empty_entity_id(self):
        """Prover with empty entity ID works."""
        prover = ZKPProver(entity_id="")
        prover.generate_keypair()
        proof = prover.create_proof(message="test")
        assert proof.entity_id == ""

    def test_empty_message_proof(self):
        """Proof with empty message is valid."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="")
        verifier = ZKPVerifier()
        result = verifier.verify(proof)
        assert result.valid is True

    def test_unicode_message(self):
        """Proof with unicode message is valid."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="认证🔐")
        verifier = ZKPVerifier()
        result = verifier.verify(proof)
        assert result.valid is True

    def test_very_long_message(self):
        """Proof with very long message is valid."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        long_msg = "x" * 10000
        proof = prover.create_proof(message=long_msg)
        verifier = ZKPVerifier()
        result = verifier.verify(proof)
        assert result.valid is True

    def test_proof_timestamps(self):
        """Proof timestamps are reasonable."""
        before = time.time()
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="test")
        after = time.time()
        assert before <= proof.timestamp <= after

    def test_verification_result_timestamp(self):
        """Verification result has a reasonable timestamp."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        proof = prover.create_proof(message="test")
        before = time.time()
        result = ZKPVerifier().verify(proof)
        after = time.time()
        assert before <= result.verified_at <= after

    def test_large_number_of_proofs(self):
        """Can generate and verify many proofs without errors."""
        prover = ZKPProver(entity_id="agent-1")
        prover.generate_keypair()
        verifier = ZKPVerifier()

        for i in range(50):
            proof = prover.create_proof(message=f"batch-{i}")
            result = verifier.verify(proof)
            assert result.valid is True, f"Proof {i} failed"

        stats = verifier.get_stats()
        assert stats["verified_proofs"] == 50

    def test_registry_unregister_during_verification(self):
        """Unregistering an entity after proof creation doesn't affect verification."""
        reg = ZKPRegistry()
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()
        reg.register("agent-1", kp.public_key)

        proof = prover.create_proof(message="auth")

        # Unregister the entity
        reg.unregister("agent-1")

        # Proof should still verify (contains its own public key)
        verifier = ZKPVerifier(registry=reg)
        result = verifier.verify(proof)
        assert result.valid is True

    def test_multiple_keypair_generations(self):
        """Generating multiple keypairs replaces the previous one."""
        prover = ZKPProver(entity_id="agent-1")
        _kp1 = prover.generate_keypair()
        kp2 = prover.generate_keypair()
        # The prover should use the latest keypair
        assert prover.keypair is kp2
        # Proofs should verify with the new keypair
        proof = prover.create_proof(message="test")
        verifier = ZKPVerifier()
        result = verifier.verify(proof)
        assert result.valid is True


class TestCryptographicProperties:
    """Tests for cryptographic properties of the ZKP system."""

    def test_proof_reveals_nothing_about_private_key(self):
        """Multiple proofs from the same prover don't reveal the private key.
        This is a property test — we can't prove this mathematically in a unit
        test, but we can verify that different proofs have different nonces,
        making it computationally infeasible to extract the private key."""
        prover = ZKPProver(entity_id="agent-1")
        kp = prover.generate_keypair()

        proofs = [prover.create_proof(message=f"msg-{i}") for i in range(10)]

        # All proofs should have different commitments (different nonces)
        commitments = {p.commitment for p in proofs}
        assert len(commitments) == 10  # All unique

        # All proofs should have different response values
        responses = {p.response_value for p in proofs}
        assert len(responses) == 10  # All unique

        # Private key should NOT be recoverable from any single proof
        for proof in proofs:
            # s = v - c*x, but we don't know v, so x is hidden
            # This is the fundamental ZKP property
            assert proof.response_value != kp.private_key

    def test_well_known_prime_group(self):
        """The prime P is a valid safe prime (p = 2q+1 where q is prime)."""
        # P is from RFC 3526 — we just verify it's odd and large
        assert _P % 2 == 1
        assert _P > 2**255  # At least 256 bits

    def test_generator_in_group(self):
        """Generator g=2 is in the multiplicative group mod p."""
        # g^q mod p should be 1 (since q is the order)
        result = pow(_G, _Q, _P)
        assert result == 1

    def test_different_entities_different_keys(self):
        """Different entities generate different keypairs (with overwhelming probability)."""
        keys = set()
        for i in range(20):
            p = ZKPProver(entity_id=f"entity-{i}")
            kp = p.generate_keypair()
            keys.add(kp.public_key)
        # All public keys should be unique
        assert len(keys) == 20
