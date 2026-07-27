# tests/test_models_matrix.py
# Tests for src/models/matrix.py — Trancendos Models Matrix base tiers +
# specialized variants.

from __future__ import annotations

from src.entities.platform import PLATFORM_ENTITIES, get_orchestration_tier
from src.models.matrix import (
    MODEL_VARIANTS,
    get_variant,
    list_variants,
    matrix_summary,
    resolve_effective_model,
    tier_rank,
)


class TestBaseTierResolution:
    def test_unspecialized_ai_resolves_to_bare_base_tier(self):
        # "Zimik" (The Library's Lead AI) has no earned specialization.
        assert resolve_effective_model("Zimik") == "Tranc3"

    def test_prime_resolves_to_t2ance(self):
        assert resolve_effective_model("Dorris Fontaine") == "T2ance"

    def test_sovereign_resolves_to_trance_one(self):
        assert resolve_effective_model("Cornelius MacIntyre") == "Trance-One"


class TestSpecializedVariants:
    def test_the_dr_expands_to_t2ance_code(self):
        assert resolve_effective_model("The Dr. (Nikolai O'denhime)") == "T2ance-CODE"

    def test_george_porter_expands_to_tranc3_crypto(self):
        assert resolve_effective_model("George Porter") == "Tranc3-Crypto"

    def test_get_variant_returns_none_for_unspecialized_ai(self):
        assert get_variant("Zimik") is None

    def test_get_variant_returns_full_record(self):
        variant = get_variant("George Porter")
        assert variant is not None
        assert variant.base_tier == "Tranc3"
        assert variant.skill_domain == "Crypto Tokens"

    def test_list_variants_returns_every_seeded_variant(self):
        names = {v.ai_name for v in list_variants()}
        assert names == set(MODEL_VARIANTS.keys())


class TestVariantIntegrityAgainstTierSourceOfTruth:
    """The _validate() import-time check already guards this, but exercise
    it explicitly so a future regression fails a named test, not just a
    module-import crash somewhere else in the suite."""

    def test_every_variant_base_tier_matches_orchestration_tier(self):
        for variant in MODEL_VARIANTS.values():
            assert get_orchestration_tier(variant.ai_name) == variant.base_tier

    def test_every_variant_ai_name_is_a_real_platform_lead_ai(self):
        known = {
            name
            for entity in PLATFORM_ENTITIES.values()
            for name in (entity.lead_ais or [entity.lead_ai])
        }
        for variant in MODEL_VARIANTS.values():
            assert variant.ai_name in known


class TestTierRank:
    def test_trance_one_is_most_capable(self):
        assert tier_rank("Trance-One") < tier_rank("T2ance") < tier_rank("Tranc3")


class TestMatrixSummary:
    def test_covers_every_named_ai_across_all_locations(self):
        summary = matrix_summary()
        # 43 Locations, 4 of which run more than one named AI (TateKing x2,
        # The Lab x2, Infinity x2, Arcadian Exchange x5) => 43 - 4 + 2+2+2+5
        assert summary["total_ais"] == 50

    def test_specialized_count_matches_seed_table(self):
        summary = matrix_summary()
        assert summary["specialized_count"] == len(MODEL_VARIANTS)

    def test_ai_rows_carry_specialization_when_present(self):
        summary = matrix_summary()
        rows = {row["ai_name"]: row for row in summary["ais"]}
        assert rows["George Porter"]["specialized_name"] == "Tranc3-Crypto"
        assert rows["Zimik"]["specialized_name"] is None
