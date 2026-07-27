# tests/test_models_benchmark.py
# Tests for src/models/benchmark.py — the Models Matrix benchmark history.

from __future__ import annotations

import pytest

from src.models.benchmark import BenchmarkRegistry, compute_advancement_pct


@pytest.fixture
def registry(tmp_path):
    reg = BenchmarkRegistry(db_path=tmp_path / "benchmark_test.db")
    yield reg
    reg.close()


class TestComputeAdvancementPct:
    def test_positive_advancement(self):
        assert compute_advancement_pct(70.0, 85.0) == pytest.approx(21.4286, abs=1e-3)

    def test_regression_is_negative(self):
        assert compute_advancement_pct(85.0, 70.0) < 0

    def test_no_change_is_zero(self):
        assert compute_advancement_pct(50.0, 50.0) == 0.0

    def test_zero_prior_score_is_treated_as_zero_not_infinite(self):
        assert compute_advancement_pct(0.0, 50.0) == 0.0

    def test_negative_prior_score_is_treated_as_zero(self):
        assert compute_advancement_pct(-10.0, 50.0) == 0.0


class TestRecordBenchmark:
    def test_record_and_read_back(self, registry):
        result = registry.record_benchmark("Tranc3-Crypto", "Crypto Tokens", 62.5, notes="scan #1")
        assert result.id > 0
        assert result.model_name == "Tranc3-Crypto"
        assert result.score == 62.5

    def test_history_orders_newest_first(self, registry):
        registry.record_benchmark("T2ance-CODE", "Coder", 50.0)
        registry.record_benchmark("T2ance-CODE", "Coder", 60.0)
        registry.record_benchmark("T2ance-CODE", "Coder", 70.0)
        history = registry.history("T2ance-CODE", "Coder")
        assert [r.score for r in history] == [70.0, 60.0, 50.0]

    def test_history_filters_by_skill_domain(self, registry):
        registry.record_benchmark("T2ance-CODE", "Coder", 50.0)
        registry.record_benchmark("T2ance-CODE", "Review", 90.0)
        coder_only = registry.history("T2ance-CODE", skill_domain="Coder")
        assert len(coder_only) == 1
        assert coder_only[0].skill_domain == "Coder"

    def test_history_without_skill_domain_returns_all(self, registry):
        registry.record_benchmark("T2ance-CODE", "Coder", 50.0)
        registry.record_benchmark("T2ance-CODE", "Review", 90.0)
        assert len(registry.history("T2ance-CODE")) == 2


class TestLatestTwo:
    def test_returns_none_none_when_empty(self, registry):
        latest, prior = registry.latest_two("Nonexistent", "None")
        assert latest is None
        assert prior is None

    def test_returns_latest_none_with_one_scan(self, registry):
        registry.record_benchmark("Tranc3-Crypto", "Crypto Tokens", 40.0)
        latest, prior = registry.latest_two("Tranc3-Crypto", "Crypto Tokens")
        assert latest is not None
        assert latest.score == 40.0
        assert prior is None

    def test_returns_both_with_two_or_more_scans(self, registry):
        registry.record_benchmark("Tranc3-Crypto", "Crypto Tokens", 40.0)
        registry.record_benchmark("Tranc3-Crypto", "Crypto Tokens", 55.0)
        latest, prior = registry.latest_two("Tranc3-Crypto", "Crypto Tokens")
        assert latest.score == 55.0
        assert prior.score == 40.0


class TestPersistenceAcrossReconnect:
    def test_survives_reopen(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = BenchmarkRegistry(db_path=db_path)
        reg1.record_benchmark("T2ance-CODE", "Coder", 50.0)
        reg1.close()
        reg2 = BenchmarkRegistry(db_path=db_path)
        assert len(reg2.history("T2ance-CODE")) == 1
        reg2.close()
