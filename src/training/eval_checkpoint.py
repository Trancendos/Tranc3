# FID: TRANC3-TRAIN-006 | Version: 1.0.0 | Module: training
"""
eval_checkpoint.py — LoRA checkpoint evaluation helper.

Lightweight wrapper around EvalSuite that works in bootstrap mode
(no torch weights, no CUDA) and is importable without pulling in torch.
All heavy imports (torch, LoRASaveLoad) are deferred until runtime.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def evaluate_checkpoint(
    base_model: Any,
    lora_checkpoint_path: str,
    samples: list,
    eval_name: str = "lora-eval",
    results_dir: str = "data/eval_results",
) -> tuple:
    """Compare a base model against a LoRA checkpoint using EvalSuite.

    Works in bootstrap mode (no torch weights needed) — used in CI.

    Parameters
    ----------
    base_model:
        The unwrapped base model; must expose a ``generate(prompt: str)``
        method (or be a MagicMock in tests).
    lora_checkpoint_path:
        Path to the saved LoRA adapter ``.pt`` file.  If the file does not
        exist or fails to load, ``lora_gen`` falls back to the base model
        rather than raising.
    samples:
        List of ``{"prompt": str, "reference": str}`` dicts.
    eval_name:
        Name prefix used by EvalSuite when writing result artefacts.
    results_dir:
        Directory for EvalSuite JSON result files.  Created automatically.

    Returns
    -------
    tuple[EvalResult, EvalResult]
        ``(base_result, lora_result)`` — both are EvalResult objects with
        ``.avg_bleu``, ``.avg_rouge_l``, ``.avg_exact_match``, etc.
    """
    from pathlib import Path as _Path

    from src.evaluation.model_eval import EvalConfig, EvalSuite

    _results = _Path(results_dir)
    _results.mkdir(parents=True, exist_ok=True)
    config = EvalConfig(name=eval_name)
    suite = EvalSuite(results_dir=_results)

    # Base model inference callable
    async def base_gen(prompt: str) -> str:
        try:
            if hasattr(base_model, "generate"):
                out = base_model.generate(prompt)
                return str(out) if out is not None else ""
        except Exception:
            pass
        return ""

    # LoRA model inference callable — load adapter then run
    lora_model_ref: list = [None]  # mutable container for closure

    async def lora_gen(prompt: str) -> str:
        if lora_model_ref[0] is None:
            # Lazy-load LoRA weights on first call (deferred torch import)
            try:
                from src.training.lora import LoRASaveLoad

                LoRASaveLoad.load(base_model, lora_checkpoint_path, strict=False)
                lora_model_ref[0] = base_model
                logger.info(
                    "evaluate_checkpoint: loaded adapter from %s",
                    lora_checkpoint_path,
                )
            except Exception as exc:
                logger.warning(
                    "evaluate_checkpoint: failed to load adapter (%s) — using base model",
                    exc,
                )
                lora_model_ref[0] = base_model
        try:
            if hasattr(lora_model_ref[0], "generate"):
                out = lora_model_ref[0].generate(prompt)
                return str(out) if out is not None else ""
        except Exception:
            pass
        return ""

    return await suite.evaluate_lora_checkpoint(config, base_gen, lora_gen, samples)
