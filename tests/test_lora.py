"""
tests/test_lora.py — Unit tests for src/training/lora.py

Tests run without CUDA / bitsandbytes — all heavy paths are mocked or
guarded with importorskip. Suite stays fast (< 2s) and zero-cost.

Covers:
  - LoRAConfig defaults and scale property
  - LoRALinear: shape, init invariant (zero output at init), merge, forward
  - apply_lora: correct layers replaced, frozen/trainable param split
  - remove_lora: layers restored, all params trainable
  - merge_lora: weights baked in, model output identical
  - lora_state_dict: only returns trainable params
  - LoRASaveLoad: round-trip save/load
  - LoRATrainer: train() runs, returns metrics (mocked model + loader)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

torch = pytest.importorskip("torch", reason="PyTorch not installed")
nn = torch.nn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _small_linear(in_f: int = 16, out_f: int = 32, bias: bool = True) -> "nn.Linear":
    lin = nn.Linear(in_f, out_f, bias=bias)
    nn.init.normal_(lin.weight)
    return lin


def _tiny_model() -> "nn.Module":
    """A tiny 2-layer MLP with named linear layers to test apply_lora."""
    class TinyMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.q_proj = nn.Linear(8, 8)
            self.v_proj = nn.Linear(8, 8)
            self.out_proj = nn.Linear(8, 4)
            self.fc = nn.Linear(8, 8)  # not in target_modules

        def forward(self, x):
            return self.out_proj(self.q_proj(x) + self.v_proj(x))

    return TinyMLP()


# ---------------------------------------------------------------------------
# LoRAConfig tests
# ---------------------------------------------------------------------------


class TestLoRAConfig:
    def _cfg(self, **kwargs):
        from src.training.lora import LoRAConfig
        return LoRAConfig(**kwargs)

    def test_default_scale(self):
        cfg = self._cfg(rank=8, alpha=16.0)
        assert cfg.scale == pytest.approx(2.0)

    def test_scale_alpha_equals_rank(self):
        cfg = self._cfg(rank=16, alpha=16.0)
        assert cfg.scale == pytest.approx(1.0)

    def test_default_target_modules_nonempty(self):
        cfg = self._cfg()
        assert len(cfg.target_modules) >= 1

    def test_zero_rank_no_division_error(self):
        cfg = self._cfg(rank=0, alpha=8.0)
        assert cfg.scale == pytest.approx(8.0)  # protected by max(rank, 1)


# ---------------------------------------------------------------------------
# LoRALinear tests
# ---------------------------------------------------------------------------


class TestLoRALinear:
    def _make(self, rank: int = 4, alpha: float = 8.0, bias: bool = True, dora: bool = False):
        from src.training.lora import LoRALinear
        base = _small_linear(bias=bias)
        return LoRALinear(base, rank=rank, alpha=alpha, use_dora=dora)

    def test_output_shape(self):
        lora = self._make()
        x = torch.randn(2, 16)
        out = lora(x)
        assert out.shape == (2, 32)

    def test_zero_init_invariant(self):
        """lora_B is zeros at init → adapter contribution is 0 → output equals base."""
        from src.training.lora import LoRALinear
        base = _small_linear()
        lora = LoRALinear(base, rank=4, alpha=8.0)
        x = torch.randn(3, 16)
        expected = torch.nn.functional.linear(x, lora.weight, lora.bias)
        actual = lora(x)
        assert torch.allclose(actual, expected, atol=1e-6)

    def test_trainable_params(self):
        lora = self._make()
        trainable_names = [n for n, p in lora.named_parameters() if p.requires_grad]
        assert "lora_A" in trainable_names
        assert "lora_B" in trainable_names
        # Base weight and bias should be frozen
        frozen = [n for n, p in lora.named_parameters() if not p.requires_grad]
        assert "weight" in frozen

    def test_merge_returns_plain_linear(self):
        from src.training.lora import LoRALinear
        base = _small_linear()
        lora = LoRALinear(base, rank=4, alpha=8.0)
        merged = lora.merge()
        assert isinstance(merged, nn.Linear)
        assert merged.weight.shape == base.weight.shape

    def test_merge_output_matches(self):
        """Merged linear output equals LoRA output (within fp32 tolerance)."""
        from src.training.lora import LoRALinear
        base = _small_linear()
        lora = LoRALinear(base, rank=4, alpha=8.0)
        # Randomly set lora_B so adapter actually contributes something
        nn.init.normal_(lora.lora_B)
        merged = lora.merge()
        x = torch.randn(5, 16)
        with torch.no_grad():
            lora_out = lora(x)
            merged_out = merged(x)
        assert torch.allclose(lora_out, merged_out, atol=1e-5)

    def test_no_bias(self):
        lora = self._make(bias=False)
        assert lora.bias is None
        x = torch.randn(2, 16)
        out = lora(x)
        assert out.shape == (2, 32)

    def test_dora_variant(self):
        lora = self._make(dora=True)
        x = torch.randn(2, 16)
        out = lora(x)
        assert out.shape == (2, 32)
        assert hasattr(lora, "dora_m")
        assert lora.dora_m.requires_grad

    def test_extra_repr(self):
        lora = self._make()
        r = repr(lora)
        assert "rank" in r or "in=" in r  # extra_repr contains layer info


# ---------------------------------------------------------------------------
# apply_lora / remove_lora / merge_lora tests
# ---------------------------------------------------------------------------


class TestApplyLora:
    def _model(self):
        return _tiny_model()

    def test_apply_replaces_target_layers(self):
        from src.training.lora import LoRAConfig, LoRALinear, apply_lora
        model = self._model()
        cfg = LoRAConfig(rank=4, alpha=8.0, target_modules=["q_proj", "v_proj", "out_proj"])
        n = apply_lora(model, cfg, verbose=False)
        assert n == 3
        assert isinstance(model.q_proj, LoRALinear)
        assert isinstance(model.v_proj, LoRALinear)
        assert isinstance(model.out_proj, LoRALinear)

    def test_non_target_layer_unchanged(self):
        from src.training.lora import LoRAConfig, LoRALinear, apply_lora
        model = self._model()
        cfg = LoRAConfig(rank=4, alpha=8.0, target_modules=["q_proj", "v_proj", "out_proj"])
        apply_lora(model, cfg, verbose=False)
        # fc is NOT in target_modules → should remain plain Linear
        assert isinstance(model.fc, nn.Linear)
        assert not isinstance(model.fc, LoRALinear)

    def test_base_weights_frozen(self):
        from src.training.lora import LoRAConfig, apply_lora
        model = self._model()
        cfg = LoRAConfig(rank=4, alpha=8.0, target_modules=["q_proj", "v_proj", "out_proj"])
        apply_lora(model, cfg, verbose=False)
        # Only lora_A, lora_B should be trainable
        for name, param in model.named_parameters():
            if "lora_A" in name or "lora_B" in name or "dora_m" in name:
                assert param.requires_grad, f"{name} should be trainable"
            else:
                assert not param.requires_grad, f"{name} should be frozen"

    def test_trainable_count_smaller_than_total(self):
        from src.training.lora import LoRAConfig, apply_lora, lora_trainable_params
        model = self._model()
        cfg = LoRAConfig(rank=4, alpha=8.0, target_modules=["q_proj", "v_proj", "out_proj"])
        apply_lora(model, cfg, verbose=False)
        trainable, total = lora_trainable_params(model)
        assert trainable < total
        assert trainable > 0

    def test_apply_returns_count(self):
        from src.training.lora import LoRAConfig, apply_lora
        model = self._model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj"])
        n = apply_lora(model, cfg, verbose=False)
        assert n == 1

    def test_idempotent_double_apply(self):
        """Applying LoRA twice should not double-wrap."""
        from src.training.lora import LoRAConfig, LoRALinear, apply_lora
        model = self._model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj"])
        apply_lora(model, cfg, verbose=False)
        n2 = apply_lora(model, cfg, verbose=False)
        assert n2 == 0  # already wrapped → nothing to do


class TestRemoveLora:
    def test_remove_restores_plain_linear(self):
        from src.training.lora import LoRAConfig, LoRALinear, apply_lora, remove_lora
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj", "v_proj"])
        apply_lora(model, cfg, verbose=False)
        remove_lora(model)
        assert isinstance(model.q_proj, nn.Linear)
        assert not isinstance(model.q_proj, LoRALinear)

    def test_remove_unfreezes_params(self):
        from src.training.lora import LoRAConfig, apply_lora, remove_lora
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj"])
        apply_lora(model, cfg, verbose=False)
        remove_lora(model)
        # After removal all params should be trainable again
        for name, param in model.named_parameters():
            assert param.requires_grad, f"{name} should be trainable after remove_lora"


class TestMergeLora:
    def test_merge_output_identical(self):
        """After merge, model output must match pre-merge output."""
        from src.training.lora import LoRAConfig, apply_lora, merge_lora
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, alpha=8.0, target_modules=["q_proj", "v_proj", "out_proj"])
        apply_lora(model, cfg, verbose=False)
        # Give adapters non-zero values
        for name, p in model.named_parameters():
            if "lora_B" in name:
                nn.init.normal_(p, std=0.01)
        x = torch.randn(3, 8)
        with torch.no_grad():
            pre_out = model(x).clone()
        merge_lora(model)
        with torch.no_grad():
            post_out = model(x)
        assert torch.allclose(pre_out, post_out, atol=1e-5)

    def test_merge_returns_count(self):
        from src.training.lora import LoRAConfig, apply_lora, merge_lora
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj", "v_proj", "out_proj"])
        apply_lora(model, cfg, verbose=False)
        count = merge_lora(model)
        assert count == 3


# ---------------------------------------------------------------------------
# lora_state_dict tests
# ---------------------------------------------------------------------------


class TestLoraStateDict:
    def test_only_trainable_params(self):
        from src.training.lora import LoRAConfig, apply_lora, lora_state_dict
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj", "v_proj"])
        apply_lora(model, cfg, verbose=False)
        sd = lora_state_dict(model)
        for key in sd:
            assert "lora_A" in key or "lora_B" in key or "dora_m" in key

    def test_nonempty_after_apply(self):
        from src.training.lora import LoRAConfig, apply_lora, lora_state_dict
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj"])
        apply_lora(model, cfg, verbose=False)
        sd = lora_state_dict(model)
        assert len(sd) >= 2  # at least lora_A + lora_B


# ---------------------------------------------------------------------------
# LoRASaveLoad round-trip tests
# ---------------------------------------------------------------------------


class TestLoRASaveLoad:
    def test_save_creates_file(self, tmp_path):
        from src.training.lora import LoRAConfig, LoRASaveLoad, apply_lora
        model = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj"])
        apply_lora(model, cfg, verbose=False)
        out = str(tmp_path / "adapter.pt")
        LoRASaveLoad.save(model, out, config=cfg, step=100)
        assert Path(out).exists()
        assert Path(out).stat().st_size > 0

    def test_load_round_trip(self, tmp_path):
        """Save adapter, modify weights, load back — verify weights restored."""
        from src.training.lora import LoRAConfig, LoRASaveLoad, apply_lora
        model_a = _tiny_model()
        model_b = _tiny_model()
        cfg = LoRAConfig(rank=4, target_modules=["q_proj", "v_proj"])

        apply_lora(model_a, cfg, verbose=False)
        apply_lora(model_b, cfg, verbose=False)

        # Give model_a unique adapter weights
        for n, p in model_a.named_parameters():
            if "lora_B" in n:
                nn.init.normal_(p, std=0.5)

        out = str(tmp_path / "adapter.pt")
        LoRASaveLoad.save(model_a, out, config=cfg)
        LoRASaveLoad.load(model_b, out)

        # After loading, model_b lora_B should match model_a
        for (na, pa), (nb, pb) in zip(
            model_a.named_parameters(), model_b.named_parameters()
        ):
            if "lora_B" in na:
                assert torch.allclose(pa, pb, atol=1e-6), f"Mismatch in {na}"


# ---------------------------------------------------------------------------
# LoRATrainer tests (mocked)
# ---------------------------------------------------------------------------


class TestLoRATrainer:
    def _build_loader(self, seq_len: int = 8, batch_size: int = 2, n_batches: int = 5):
        """Build a synthetic data loader that yields (input_ids, targets) dicts."""
        batches = [
            {
                "input_ids": torch.randint(0, 100, (batch_size, seq_len)),
                "targets": torch.randint(0, 100, (batch_size, seq_len)),
            }
            for _ in range(n_batches)
        ]
        return batches

    def _stub_model(self):
        """Tiny model that returns (logits, scalar_loss)."""
        class StubModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.q_proj = nn.Linear(16, 16)
                self.v_proj = nn.Linear(16, 16)

            def forward(self, input_ids, targets=None):
                x = input_ids.float()
                logits = self.q_proj(x[:, :, None].expand(-1, -1, 16).float().mean(-2))
                loss = torch.tensor(1.0, requires_grad=True)
                return logits, loss

        return StubModel()

    def test_trainer_runs_returns_metrics(self, tmp_path):
        from src.training.lora_trainer import LoRATrainer, LoRATrainingConfig

        model = self._stub_model()
        loader = self._build_loader()

        cfg = LoRATrainingConfig(
            rank=4,
            alpha=8.0,
            target_modules=["q_proj", "v_proj"],
            total_steps=10,
            log_every=5,
            save_every=100,
            checkpoint_dir=str(tmp_path / "ckpts"),
            run_name="test_run",
            merge_on_finish=False,
        )

        trainer = LoRATrainer(model, loader, cfg, device=torch.device("cpu"))
        metrics = trainer.train(steps=10)
        assert isinstance(metrics, list)
        assert len(metrics) >= 1
        assert "loss" in metrics[0]
        assert "step" in metrics[0]

    def test_adapter_checkpoint_created(self, tmp_path):
        from src.training.lora_trainer import LoRATrainer, LoRATrainingConfig

        model = self._stub_model()
        loader = self._build_loader()

        cfg = LoRATrainingConfig(
            rank=4,
            target_modules=["q_proj"],
            total_steps=5,
            log_every=5,
            save_every=100,
            checkpoint_dir=str(tmp_path / "ckpts"),
            run_name="ckpt_test",
        )

        trainer = LoRATrainer(model, loader, cfg, device=torch.device("cpu"))
        trainer.train(steps=5)

        ckpt_files = list(Path(tmp_path / "ckpts").glob("*.pt"))
        assert len(ckpt_files) >= 1

    def test_only_lora_params_trainable(self, tmp_path):
        from src.training.lora import lora_trainable_params
        from src.training.lora_trainer import LoRATrainer, LoRATrainingConfig

        model = self._stub_model()
        loader = self._build_loader()

        cfg = LoRATrainingConfig(
            rank=4,
            target_modules=["q_proj", "v_proj"],
            total_steps=1,
            checkpoint_dir=str(tmp_path / "ckpts"),
        )
        trainer = LoRATrainer(model, loader, cfg, device=torch.device("cpu"))
        trainable, total = lora_trainable_params(model)
        assert trainable < total
        assert trainable > 0


# ---------------------------------------------------------------------------
# evaluate_checkpoint() — async LoRA eval integration
# ---------------------------------------------------------------------------


class TestEvaluateCheckpoint:
    """Tests for evaluate_checkpoint() in src/training/lora.py.

    All tests run in bootstrap mode (no real model weights, no CUDA).
    Uses asyncio.run() so no external pytest-asyncio plugin needed.
    """

    @staticmethod
    def _stub_model():
        """Minimal model stub with a generate() method."""
        model = MagicMock()
        model.generate = MagicMock(return_value="stub answer")
        return model

    @staticmethod
    def _samples():
        return [
            {"prompt": "What is 2+2?", "reference": "4"},
            {"prompt": "Capital of France?", "reference": "Paris"},
        ]

    def test_returns_tuple_of_two(self, tmp_path):
        """evaluate_checkpoint should return a (base_result, lora_result) tuple."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        model = self._stub_model()
        result = asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=self._samples(),
                eval_name="test-eval",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_base_result_has_scores(self, tmp_path):
        """base_result should expose bleu and rouge_l attributes."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        model = self._stub_model()
        base_result, _ = asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=self._samples(),
                eval_name="test-base-scores",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert hasattr(base_result, "bleu") or hasattr(base_result, "avg_bleu") or isinstance(base_result, dict)

    def test_lora_result_has_scores(self, tmp_path):
        """lora_result should expose the same score shape as base_result."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        model = self._stub_model()
        base_result, lora_result = asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=self._samples(),
                eval_name="test-lora-scores",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert type(base_result) is type(lora_result)

    def test_empty_samples_does_not_raise(self, tmp_path):
        """evaluate_checkpoint with empty sample list should not raise."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        model = self._stub_model()
        result = asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=[],
                eval_name="test-empty",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)

    def test_missing_checkpoint_gracefully_handled(self, tmp_path):
        """Missing .pt file should not crash — lora_gen falls back gracefully."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        model = self._stub_model()
        # Path does not exist — LoRASaveLoad.load will raise → lora_gen falls back
        result = asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "nonexistent.pt"),
                samples=self._samples(),
                eval_name="test-missing-ckpt",
                results_dir=str(tmp_path / "results"),
            )
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_results_dir_created(self, tmp_path):
        """evaluate_checkpoint should create results_dir if it doesn't exist."""
        import asyncio
        from src.training.lora import evaluate_checkpoint

        results_dir = tmp_path / "deep" / "nested" / "results"
        model = self._stub_model()
        asyncio.run(
            evaluate_checkpoint(
                base_model=model,
                lora_checkpoint_path=str(tmp_path / "fake.pt"),
                samples=self._samples(),
                eval_name="test-dir-creation",
                results_dir=str(results_dir),
            )
        )
        # EvalSuite creates the directory; confirm it exists
        assert results_dir.exists()

    def test_default_eval_name(self, tmp_path):
        """evaluate_checkpoint uses 'lora-eval' as default eval_name."""
        import asyncio
        import inspect
        from src.training.lora import evaluate_checkpoint

        sig = inspect.signature(evaluate_checkpoint)
        assert sig.parameters["eval_name"].default == "lora-eval"

    def test_default_results_dir(self, tmp_path):
        """evaluate_checkpoint uses 'data/eval_results' as default results_dir."""
        import asyncio
        import inspect
        from src.training.lora import evaluate_checkpoint

        sig = inspect.signature(evaluate_checkpoint)
        assert sig.parameters["results_dir"].default == "data/eval_results"
