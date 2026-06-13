"""
Tests for DNAConfig — src/core/dna_config.py
"""

import pytest
from src.core.dna_config import DNAConfig, Variant


# ── Helpers ───────────────────────────────────────────────────────────────


BASE_CFG = {"batch_size": 32, "cache_ttl": 300, "concurrency": 4}


# ── Tests ─────────────────────────────────────────────────────────────────


def test_register_base_and_get_active():
    """Registering a base config and retrieving it should return same values."""
    dna = DNAConfig(auto_promote=False)
    vid = dna.register_base(BASE_CFG, name="base")
    cfg = dna.get_active_config()
    assert cfg["batch_size"] == 32
    assert cfg["cache_ttl"] == 300
    assert cfg["_variant_id"] == vid


def test_mutate_applies_overrides():
    """A mutation should merge overrides with base config."""
    dna = DNAConfig(auto_promote=False)
    dna.register_base(BASE_CFG)
    mid = dna.mutate({"batch_size": 128}, name="large-batch")
    variant = dna.get_variant(mid)
    assert variant is not None
    assert variant.config["batch_size"] == 128
    assert variant.config["cache_ttl"] == 300  # inherited from base


def test_promote_best_variant():
    """Variant with highest mean score should become active after promote_best."""
    dna = DNAConfig(auto_promote=False, promote_min_samples=3)
    base_id = dna.register_base(BASE_CFG, name="base")
    mut_id = dna.mutate({"concurrency": 16}, name="high-concurrency")

    # Give base variant low scores
    for _ in range(5):
        dna.record_score(base_id, score=0.4)
    # Give mutation high scores
    for _ in range(5):
        dna.record_score(mut_id, score=0.9)

    promoted = dna.promote_best()
    assert promoted == mut_id
    cfg = dna.get_active_config()
    # Allow for exploration jitter but active_id should now be mut_id
    assert dna._active_id == mut_id


def test_no_promotion_below_min_samples():
    """promote_best should not change active_id if no variant meets min_samples."""
    dna = DNAConfig(auto_promote=False, promote_min_samples=10)
    base_id = dna.register_base(BASE_CFG)
    mut_id = dna.mutate({"batch_size": 64})

    for _ in range(3):
        dna.record_score(mut_id, score=0.99)

    result = dna.promote_best()
    assert result is None  # Not enough samples
    assert dna._active_id == base_id


def test_leaderboard_sorted_by_mean_score():
    """Leaderboard must be sorted descending by mean_score."""
    dna = DNAConfig(auto_promote=False, promote_min_samples=1)
    id1 = dna.register_base(BASE_CFG, name="base")
    id2 = dna.mutate({"batch_size": 64}, name="mut-a")
    id3 = dna.mutate({"concurrency": 8}, name="mut-b")

    dna.record_score(id1, 0.5)
    dna.record_score(id2, 0.9)
    dna.record_score(id3, 0.1)

    board = dna.leaderboard()
    assert board[0]["variant_id"] == id2
    assert board[-1]["variant_id"] == id3


def test_deactivate_removes_from_selection():
    """Deactivated variant must not be returned as active."""
    dna = DNAConfig(auto_promote=False, exploration_fraction=0.0)
    base_id = dna.register_base(BASE_CFG)
    mut_id = dna.mutate({"batch_size": 64})
    # Force active to mut_id
    dna._active_id = mut_id

    dna.deactivate(mut_id)
    cfg = dna.get_active_config()
    assert cfg["_variant_id"] != mut_id


def test_sqlite_persistence(tmp_path):
    """Variants should be persisted to and loadable from SQLite."""
    db = str(tmp_path / "dna.db")
    dna1 = DNAConfig(db_path=db, auto_promote=False)
    vid = dna1.register_base(BASE_CFG, name="persistent-base")
    dna1.record_score(vid, 0.7)

    # Load in fresh instance
    dna2 = DNAConfig(db_path=db, auto_promote=False)
    assert vid in dna2._variants
    assert dna2._variants[vid].name == "persistent-base"
