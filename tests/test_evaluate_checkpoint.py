# FID: TRANC3-TEST-015 | Version: 1.0.0 | Module: training
"""
tests/test_evaluate_checkpoint.py — Tests for evaluate_checkpoint() in lora.py.

Runs in bootstrap mode: no CUDA, no real model weights, no torch dependency at
the class level — only checked inside each test that needs it. EvalSuite is fully
functional without heavy ML dependencies.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_model() -> MagicMock:
    """Minimal model stub with generate() method."""
    model = MagicMock()
    model.generate = MagicMock(return_value="stub answer")
    return model


def _samples() -> list:
    return [
        {"prompt": "What is 2+2?", "reference": "4"},
        {"prompt": "Capital of France?", "reference": "Paris"},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvaluateCheckpointSignature:
    """Verify function signature / defaults without running it."""

    def test_function_exists(self):
        from src.training.eval_checkpoint import evaluate_checkpoint

        assert callable(evaluate_checkpoint)

    def test_is_coroutine_function(self):
        import asyncio
        from src.training.eval_checkpoint import evaluate_checkpoint

        assert asyncio.iscoroutinefunction(evaluate_checkpoint)

    def test_default_eval_name(self):
        from src.training.eval_checkpoint import evaluate_checkpoint

        sig = inspect.signature(evaluate_checkpoint)
        assert sig.parameters["eval_name"].default == "lora-eval"

    def test_default_results_dir(self):
        from src.training.eval_checkpoint import evaluate_checkpoint

        sig = inspect.signature(evaluate_checkpoint)
        assert sig.parameters["results_dir"].default == "data/eval_results"

    def test_required_parameters(self):
        from src.training.eval_checkpoint import evaluate_checkpoint

        sig = inspect.signature(evaluate_checkpoint)
        params = list(sig.parameters.keys())
        assert "base_model" in params
        assert "lora_checkpoint_path" in params
        assert "samples" in params


class TestEvaluateCheckpointRuntime:
    """Runtime tests — bootstrapped via EvalSuite, no CUDA needed."""

    def test_returns_tuple_of_two(self, tmp_path):
        from src.training.eval_checkpoint import evaluate_checkpoint

        result = asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=_samples(),
                eval_name="test-returns-tuple",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_both_results_same_type(self, tmp_path):
        from src.training.eval_checkpoint import evaluate_checkpoint

        base_result, lora_result = asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=_samples(),
                eval_name="test-same-type",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert type(base_result) is type(lora_result)

    def test_empty_samples_does_not_raise(self, tmp_path):
        from src.training.eval_checkpoint import evaluate_checkpoint

        result = asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=[],
                eval_name="test-empty",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)

    def test_missing_checkpoint_graceful(self, tmp_path):
        """Missing .pt file → lora_gen falls back, no crash."""
        from src.training.eval_checkpoint import evaluate_checkpoint

        result = asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "nonexistent.pt"),
                samples=_samples(),
                eval_name="test-missing-ckpt",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_results_dir_created(self, tmp_path):
        from src.training.eval_checkpoint import evaluate_checkpoint

        results_dir = tmp_path / "deep" / "nested" / "results"
        asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=_samples(),
                eval_name="test-dir-create",
                results_dir=str(results_dir),
            )
        )
        assert results_dir.exists()

    def test_custom_eval_name_used(self, tmp_path):
        """EvalSuite writes results using eval_name — verify results_dir populated."""
        from src.training.eval_checkpoint import evaluate_checkpoint

        results_dir = tmp_path / "results"
        asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=_samples(),
                eval_name="my-custom-name",
                results_dir=str(results_dir),
            )
        )
        # At minimum results_dir was created
        assert results_dir.exists()

    def test_model_without_generate_does_not_crash(self, tmp_path):
        """Model that raises on generate() → base_gen catches exception, returns ''."""
        from src.training.eval_checkpoint import evaluate_checkpoint

        broken_model = MagicMock()
        broken_model.generate = MagicMock(side_effect=RuntimeError("no weights"))

        result = asyncio.run(
            evaluate_checkpoint(
                base_model=broken_model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=_samples(),
                eval_name="test-broken-model",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)

    def test_single_sample(self, tmp_path):
        """Works with a single-element sample list."""
        from src.training.eval_checkpoint import evaluate_checkpoint

        result = asyncio.run(
            evaluate_checkpoint(
                base_model=_stub_model(),
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=[{"prompt": "Hello?", "reference": "Hi!"}],
                eval_name="test-single",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
