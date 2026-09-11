"""Characterisation of the percentage-rollout bucketer — SEC-019.

CodeQL reports `py/weak-sensitive-data-hashing` (security-severity 7.5) at
`src/nanoservices/feature_flags/feature_flags.py:296`:

    def _hash_bucket(self, key: str) -> float:
        h = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

called as ``_hash_bucket(f"{flag_key}:{user_id}")``. The rule fires because
``user_id`` is classified as sensitive; the code already passes
``usedforsecurity=False``, which this rule does not consider.

It is a **false positive**. The digest is not a credential, not a stored
identifier, and not compared against anything an attacker supplies. It is
consumed on the next line as ``bucket < rule.percentage / 100.0`` and discarded;
it is never persisted, never returned in a `FlagEvaluation`, and
``_hash_bucket`` has no caller outside this module.

**The reason this file exists is that the obvious "fix" is not free.** Swapping
MD5 for SHA-256 or BLAKE2 changes every user's bucket, which silently moves an
arbitrary fraction of users into or out of every active percentage rollout —
features appearing and disappearing for real people, with nothing in the diff
saying so. A one-line hash change would look like tidying.

So the assignments are pinned here instead. Anyone changing the hash gets a
failure naming the users whose rollout membership they are about to change,
which is the decision they should be making deliberately rather than as a side
effect of clearing a scanner finding.
"""

from __future__ import annotations

import hashlib

import pytest

from src.nanoservices.feature_flags.feature_flags import FeatureFlagService


@pytest.fixture
def service() -> FeatureFlagService:
    return FeatureFlagService()


# A fixed sample. The point is not these particular users but that the mapping
# is stable: regenerate this table ONLY alongside a deliberate, announced
# re-bucketing of every live percentage rollout.
_PINNED = [
    ("new-checkout:user-0001", 0.7591835928054488),
    ("new-checkout:user-0002", 0.8353098397691059),
    ("new-checkout:user-0003", 0.9424230700690353),
    ("dark-mode:user-0001", 0.379184484104436),
    ("dark-mode:user-0002", 0.11857151545550942),
    ("beta-search:alice@example.com", 0.7090319454923812),
]


class TestBucketAssignmentsAreStable:
    @pytest.mark.parametrize(("key", "expected"), _PINNED)
    def test_pinned(self, service: FeatureFlagService, key: str, expected: float) -> None:
        assert service._hash_bucket(key) == pytest.approx(expected, abs=1e-12)

    def test_changing_the_hash_would_move_users(self, service: FeatureFlagService) -> None:
        """Quantifies the cost, so the docstring above is not just an assertion.

        At a 50% rollout, this is how many of the sampled users would cross the
        threshold if the digest changed — the concrete thing a "just use SHA-256"
        patch would do.
        """

        def sha_bucket(key: str) -> float:
            return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF

        moved = [
            key
            for key, _ in _PINNED
            if (service._hash_bucket(key) < 0.5) != (sha_bucket(key) < 0.5)
        ]
        assert moved, (
            "The two digests agree on every sampled user, which makes this "
            "sample useless as evidence — widen it before trusting it."
        )


class TestBucketIsAFractionNotAnIdentifier:
    @pytest.mark.parametrize("n", range(200))
    def test_always_in_unit_interval(self, service: FeatureFlagService, n: int) -> None:
        """A bucket outside [0, 1) would make percentage comparisons meaningless."""
        assert 0.0 <= service._hash_bucket(f"flag:user-{n}") < 1.0

    def test_roughly_uniform(self, service: FeatureFlagService) -> None:
        """A 10% rollout must reach about 10% of users, or the feature is broken.

        This is what the hash is actually for, and it is the property any
        replacement has to preserve.
        """
        sample = [service._hash_bucket(f"flag:user-{n}") for n in range(5000)]
        share = sum(1 for b in sample if b < 0.10) / len(sample)
        assert 0.08 < share < 0.12, share

    def test_same_user_same_answer(self, service: FeatureFlagService) -> None:
        """Stickiness: a user must not flip in and out between evaluations."""
        assert service._hash_bucket("flag:u") == service._hash_bucket("flag:u")

    def test_different_flags_bucket_independently(self, service: FeatureFlagService) -> None:
        """Otherwise every 10% rollout would target the same 10% of users."""
        assert service._hash_bucket("flag-a:u") != service._hash_bucket("flag-b:u")
