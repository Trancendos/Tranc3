"""
tests/test_evaluator.py — Unit tests for src/training/evaluator.py

Tests run without torch / model weights — all heavy paths are mocked or
gated by importorskip so the suite stays fast (< 2s) and zero-cost.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — pure-Python metric functions don't need torch
# ---------------------------------------------------------------------------


class TestGenerationQuality:
    """_generation_quality() — pure Python, always runnable."""

    def _gq(self, seqs):
        from src.training.evaluator import _generation_quality
        return _generation_quality(seqs)

    def test_empty_seqs(self):
        result = self._gq([])
        assert result["avg_length"] == 0.0
        assert result["distinct_1"] == 0.0

    def test_single_token_seq(self):
        result = self._gq([[42]])
        assert result["avg_length"] == 1.0
        assert result["repetition_rate"] == 0.0
        assert result["distinct_1"] == 1.0  # 1 unique / 1 total

    def test_repeated_tokens_max_repetition(self):
        # All same token → high repetition, low distinct-1
        result = self._gq([[7, 7, 7, 7]])
        assert result["repetition_rate"] == pytest.approx(0.75, abs=0.01)  # 3/4 repeated
        assert result["distinct_1"] == pytest.approx(1 / 4, abs=0.01)

    def test_all_unique_zero_repetition(self):
        result = self._gq([[1, 2, 3, 4, 5]])
        assert result["repetition_rate"] == 0.0
        assert result["distinct_1"] == 1.0

    def test_distinct_2_bigrams(self):
        # [1,2,3] → bigrams (1,2),(2,3) — 2 unique bigrams
        result = self._gq([[1, 2, 3]])
        assert result["distinct_2"] == pytest.approx(1.0, abs=0.01)

    def test_multiple_seqs_avg_length(self):
        result = self._gq([[1, 2], [3, 4, 5]])
        assert result["avg_length"] == pytest.approx(2.5, abs=0.01)


class TestEvalMetricsDataclass:
    def test_default_values(self):
        from src.training.evaluator import EvalMetrics
        m = EvalMetrics()
        assert m.perplexity == 0.0
        assert m.token_accuracy == 0.0
        assert m.num_batches == 0

    def test_with_values(self):
        from src.training.evaluator import EvalMetrics
        m = EvalMetrics(perplexity=12.3, token_accuracy=0.87, num_batches=50)
        assert m.perplexity == 12.3
        assert m.token_accuracy == 0.87


class TestBenchmarkResult:
    def test_error_field(self):
        from src.training.evaluator import BenchmarkResult
        r = BenchmarkResult(name="test", prompt="hi", output="", error="boom")
        assert r.error == "boom"
        assert r.tokens_generated == 0

    def test_success_fields(self):
        from src.training.evaluator import BenchmarkResult
        r = BenchmarkResult(
            name="greeting", prompt="Hello", output="Hi there", tokens_generated=3, latency_ms=42.5
        )
        assert r.tokens_generated == 3
        assert r.latency_ms == 42.5
        assert r.error is None


class TestSummarise:
    def _make_report(self, results, eval_metrics=None):
        from src.training.evaluator import BenchmarkReport
        report = BenchmarkReport(
            model_path="test.pt",
            benchmark_results=results,
            eval_metrics=eval_metrics,
        )
        return report

    def test_all_pass(self):
        from src.training.evaluator import BenchmarkResult, _summarise
        results = [BenchmarkResult(name="a", prompt="p", output="o", tokens_generated=5, latency_ms=10.0)]
        report = self._make_report(results)
        summary = _summarise(report)
        assert summary["tasks_run"] == 1
        assert summary["tasks_passed"] == 1
        assert summary["tasks_failed"] == 0
        assert summary["avg_latency_ms"] == 10.0

    def test_failed_task(self):
        from src.training.evaluator import BenchmarkResult, _summarise
        results = [
            BenchmarkResult(name="ok", prompt="p", output="o", latency_ms=5.0),
            BenchmarkResult(name="bad", prompt="p", output="", error="oops", latency_ms=1.0),
        ]
        report = self._make_report(results)
        summary = _summarise(report)
        assert summary["tasks_failed"] == 1
        assert summary["tasks_passed"] == 1

    def test_includes_eval_metrics_when_present(self):
        from src.training.evaluator import EvalMetrics, _summarise
        metrics = EvalMetrics(perplexity=8.5, token_accuracy=0.9, distinct_1=0.7, distinct_2=0.6)
        report = self._make_report([], eval_metrics=metrics)
        summary = _summarise(report)
        assert summary["perplexity"] == 8.5
        assert summary["token_accuracy"] == 0.9


# ---------------------------------------------------------------------------
# ModelEvaluator — mocked torch
# ---------------------------------------------------------------------------


class TestModelEvaluatorMocked:
    """Test ModelEvaluator with a mock model and loader (no torch required)."""

    def _build_mock_batch(self):
        """Build a minimal mock batch using MagicMock."""
        torch = pytest.importorskip("torch")
        batch = {
            "input_ids": torch.zeros(2, 8, dtype=torch.long),
            "targets": torch.ones(2, 8, dtype=torch.long),
        }
        return batch

    def test_evaluator_stub_when_no_torch(self, tmp_path):
        """When torch unavailable, returns stub EvalMetrics without error."""
        from src.training.evaluator import EvalMetrics, ModelEvaluator

        model = MagicMock()
        loader = iter([])
        device = "cpu"

        with patch("src.training.evaluator.torch", None, create=True):
            # Simulate ImportError for torch in evaluator
            import sys
            original = sys.modules.get("torch")
            sys.modules["torch"] = None  # type: ignore[assignment]
            try:
                evaluator = ModelEvaluator(model, loader, device)
                # run() should handle missing torch gracefully
                metrics = evaluator.run()
                assert isinstance(metrics, EvalMetrics)
                assert metrics.num_batches == 0
            finally:
                if original is None:
                    sys.modules.pop("torch", None)
                else:
                    sys.modules["torch"] = original


# ---------------------------------------------------------------------------
# BenchmarkSuite — mocked model
# ---------------------------------------------------------------------------


class TestBenchmarkSuiteMocked:
    def _stub_tokenizer(self):
        tok = MagicMock()
        tok.encode = lambda text: [1, 2, 3]
        tok.decode = lambda tokens: "mock output"
        return tok

    def _stub_model(self):
        """Model that returns zeros for logits and zero loss."""
        try:
            import torch
        except ImportError:
            return MagicMock()

        model = MagicMock()
        # Return (logits, loss) — logits shape [batch, seq, vocab]
        logits = torch.zeros(1, 4, 256)
        model.return_value = (logits, torch.tensor(0.0))
        model.eval = MagicMock()
        model.train = MagicMock()
        return model

    def test_run_returns_report(self, tmp_path):
        from src.training.evaluator import BenchmarkSuite

        suite = BenchmarkSuite(
            model=self._stub_model(),
            tokenizer=self._stub_tokenizer(),
            device="cpu",
            max_new_tokens=4,
            prompts=[("test_task", "test prompt")],
        )
        report = suite.run(model_path="test.pt", step=0)
        assert len(report.benchmark_results) == 1
        assert report.benchmark_results[0].name == "test_task"

    def test_save_creates_json(self, tmp_path):
        from src.training.evaluator import BenchmarkReport, BenchmarkResult, BenchmarkSuite

        report = BenchmarkReport(
            model_path="test.pt",
            benchmark_results=[
                BenchmarkResult(name="a", prompt="p", output="o", tokens_generated=3, latency_ms=5.0)
            ],
            summary={"tasks_run": 1},
        )
        out = str(tmp_path / "report.json")
        BenchmarkSuite.save(report, out)
        data = json.loads(Path(out).read_text())
        assert data["model_path"] == "test.pt"
        assert len(data["benchmark_results"]) == 1

    def test_report_summary_populated(self, tmp_path):
        from src.training.evaluator import BenchmarkSuite

        suite = BenchmarkSuite(
            model=self._stub_model(),
            tokenizer=self._stub_tokenizer(),
            device="cpu",
            max_new_tokens=4,
            prompts=[("t1", "hello"), ("t2", "world")],
        )
        report = suite.run(model_path="ckpt.pt", step=100)
        assert "tasks_run" in report.summary
        assert report.summary["tasks_run"] == 2


# ---------------------------------------------------------------------------
# Default prompts coverage
# ---------------------------------------------------------------------------


class TestDefaultPrompts:
    def test_default_prompts_count(self):
        from src.training.evaluator import DEFAULT_PROMPTS
        assert len(DEFAULT_PROMPTS) >= 6, "Should have at least 6 benchmark prompts"

    def test_default_prompts_have_names_and_text(self):
        from src.training.evaluator import DEFAULT_PROMPTS
        for name, prompt in DEFAULT_PROMPTS:
            assert isinstance(name, str) and name
            assert isinstance(prompt, str) and prompt
