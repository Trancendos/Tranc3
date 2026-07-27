# tests/test_models_knowledge.py
# Tests for src/models/knowledge.py — the Models Matrix <-> The Library
# integration (read: library_context_for; write: publish_advancement_article).

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.library.knowledge_base import Library
from src.models.benchmark import BenchmarkRegistry
from src.models.governance import ModelGovernanceRegistry, ProposalStage
from src.models.knowledge import (
    ADVANCEMENT_TAG,
    job_description_for_ai,
    library_context_for,
    publish_advancement_article,
)

DR = "The Dr. (Nikolai O'denhime)"
GEORGE_PORTER = "George Porter"


class TestJobDescriptionForAi:
    def test_resolves_job_description_for_a_lead_ai(self):
        assert job_description_for_ai(DR) == "Chief Engineering Officer"

    def test_resolves_job_description_for_a_multi_ai_location_member(self):
        # George Porter is one of Arcadian Exchange's lead_ais, not the
        # primary lead_ai — still needs to resolve.
        assert job_description_for_ai(GEORGE_PORTER) is not None

    def test_unknown_ai_returns_none(self):
        assert job_description_for_ai("Nonexistent AI") is None


class TestLibraryContextFor:
    def test_returns_articles_tagged_with_skill_domain(self):
        test_lib = Library()
        test_lib.create(title="Prior Coder insight", body="...", tags=["Coder"])
        with patch("src.library.knowledge_base.get_library", return_value=test_lib):
            results = library_context_for("Coder")
        assert len(results) == 1
        assert results[0]["title"] == "Prior Coder insight"

    def test_returns_empty_list_for_unmatched_tag(self):
        test_lib = Library()
        with patch("src.library.knowledge_base.get_library", return_value=test_lib):
            results = library_context_for("NoSuchSkillDomain")
        assert results == []

    def test_never_raises_when_library_unavailable(self):
        with patch(
            "src.library.knowledge_base.get_library", side_effect=RuntimeError("unavailable")
        ):
            results = library_context_for("Coder")
        assert results == []


class TestPublishAdvancementArticle:
    @pytest.fixture
    def governance(self, tmp_path):
        bench = BenchmarkRegistry(db_path=tmp_path / "bench.db")
        gov = ModelGovernanceRegistry(db_path=tmp_path / "gov.db", benchmark_registry=bench)
        yield gov, bench
        gov.close()
        bench.close()

    def test_publishes_on_approval_with_expected_tags(self, governance):
        gov, bench = governance
        test_lib = Library()
        with patch("src.library.knowledge_base.get_library", return_value=test_lib):
            bench.record_benchmark(DR, "Coder", 60.0)
            bench.record_benchmark(DR, "Coder", 90.0)
            proposal = gov.submit_proposal(DR, "Coder")
            proposal = gov.cornelius_review(proposal.id, notes="approved")
        assert proposal.stage == ProposalStage.APPROVED

        published = [a for a in test_lib.recent(limit=20) if a.source == "models-governance"]
        assert len(published) == 1
        art = published[0]
        assert ADVANCEMENT_TAG in art.tags
        assert "Coder" in art.tags
        assert "T2ance" in art.tags
        assert "Chief Engineering Officer" in art.tags
        assert art.author == DR

    def test_does_not_publish_when_rejected(self, governance):
        gov, bench = governance
        test_lib = Library()
        with patch("src.library.knowledge_base.get_library", return_value=test_lib):
            bench.record_benchmark(GEORGE_PORTER, "Trading", 100.0)
            bench.record_benchmark(GEORGE_PORTER, "Trading", 100.5)  # minimal advancement
            proposal = gov.submit_proposal(GEORGE_PORTER, "Trading")
            proposal = gov.prime_review(proposal.id, reviewer="Dorris Fontaine")
        assert proposal.stage == ProposalStage.REJECTED_BY_PRIME
        published = [a for a in test_lib.recent(limit=20) if a.source == "models-governance"]
        assert published == []

    def test_direct_call_returns_none_when_library_unavailable(self, governance):
        gov, bench = governance
        throwaway_lib = Library()
        with patch("src.library.knowledge_base.get_library", return_value=throwaway_lib):
            bench.record_benchmark(DR, "Coder", 60.0)
            bench.record_benchmark(DR, "Coder", 90.0)
            proposal = gov.submit_proposal(DR, "Coder")
            proposal = gov.cornelius_review(proposal.id)
        with patch(
            "src.library.knowledge_base.get_library", side_effect=RuntimeError("unavailable")
        ):
            result = publish_advancement_article(proposal)
        assert result is None
