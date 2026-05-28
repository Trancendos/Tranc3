"""
lora_trainer.py — LoRA / QLoRA training loop for Tranc3 models
===============================================================
Wraps the standard Trainer with LoRA-specific logic:

  • Applies LoRA adapters before training begins
  • Only optimises adapter parameters (vastly reduced memory / compute)
  • Saves lightweight adapter checkpoints (not full model weights)
  • Can optionally merge adapters before final export
  • Integrates with ModelEvaluator for per-epoch benchmarking

Usage
-----
    from src.training.lora_trainer import LoRATrainer, LoRATrainingConfig

    cfg = LoRATrainingConfig(
        rank=8,
        alpha=16,
        target_modules=["q_proj", "v_proj"],
        lora_lr=2e-4,
        base_model_path="checkpoints/tranc3_base.pt",
    )
    trainer = LoRATrainer(model, tokenizer, cfg)
    trainer.train(steps=1000)
    trainer.save_adapter("checkpoints/lora_adapter.pt")
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import torch
import torch.nn as nn

from .lora import (
    LoRAConfig,
    LoRASaveLoad,
    apply_lora,
    lora_trainable_params,
    merge_lora,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LoRA training configuration
# ---------------------------------------------------------------------------

@dataclass
class LoRATrainingConfig:
    """Configuration for LoRA fine-tuning.

    Extends LoRAConfig with training-specific hyper-parameters.
    """
    # LoRA adapter settings
    rank: int = 8
    alpha: float = 16.0
    dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "out_proj", "qkv_proj", "down_proj",
    ])
    quantize_4bit: bool = False
    use_dora: bool = False

    # Optimiser
    lora_lr: float = 2e-4
    weight_decay: float = 0.0
    beta1: float = 0.9
    beta2: float = 0.999
    eps: float = 1e-8
    grad_clip: float = 1.0

    # LR schedule
    warmup_steps: int = 100
    total_steps: int = 1000
    lr_schedule: str = "cosine"        # "cosine" | "linear" | "constant"

    # Training loop
    grad_accum_steps: int = 4
    mixed_precision: bool = True       # fp16/bf16 on CUDA, disabled on CPU
    log_every: int = 10
    eval_every: int = 100
    save_every: int = 200

    # Checkpointing
    checkpoint_dir: str = "checkpoints/lora"
    run_name: str = "lora_run"
    base_model_path: Optional[str] = None  # load base weights before applying LoRA
    resume_adapter: Optional[str] = None   # resume from a previous adapter checkpoint

    # Post-training
    merge_on_finish: bool = False       # merge adapters into base weights on completion


# ---------------------------------------------------------------------------
# LR schedule helpers
# ---------------------------------------------------------------------------

def _cosine_lr(step: int, warmup: int, total: int, base_lr: float) -> float:
    if step < warmup:
        return base_lr * step / max(warmup, 1)
    progress = (step - warmup) / max(total - warmup, 1)
    return base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


def _linear_lr(step: int, warmup: int, total: int, base_lr: float) -> float:
    if step < warmup:
        return base_lr * step / max(warmup, 1)
    decay = max(0.0, (total - step) / max(total - warmup, 1))
    return base_lr * decay


def _get_lr(step: int, cfg: LoRATrainingConfig) -> float:
    if cfg.lr_schedule == "cosine":
        return _cosine_lr(step, cfg.warmup_steps, cfg.total_steps, cfg.lora_lr)
    if cfg.lr_schedule == "linear":
        return _linear_lr(step, cfg.warmup_steps, cfg.total_steps, cfg.lora_lr)
    return cfg.lora_lr  # constant


# ---------------------------------------------------------------------------
# LoRA Trainer
# ---------------------------------------------------------------------------

class LoRATrainer:
    """
    Fine-tunes a Tranc3 model using Low-Rank Adaptation.

    The base model weights are frozen; only the LoRA adapter matrices
    (lora_A, lora_B) are updated.  This typically reduces trainable
    parameters to < 1% of the full model while achieving near full
    fine-tuning performance on most downstream tasks.
    """

    def __init__(
        self,
        model: nn.Module,
        train_loader: Any,                      # DataLoader or iterable of batches
        cfg: LoRATrainingConfig,
        val_loader: Optional[Any] = None,
        device: Optional[torch.device] = None,
    ) -> None:
        self.cfg = cfg
        self.device = device or (
            torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        )
        self.model = model.to(self.device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.step = 0
        self._metrics: List[Dict] = []

        # Optionally load base checkpoint
        if cfg.base_model_path:
            self._load_base_model(cfg.base_model_path)

        # Build LoRAConfig from training config
        self.lora_cfg = LoRAConfig(
            rank=cfg.rank,
            alpha=cfg.alpha,
            dropout=cfg.dropout,
            target_modules=cfg.target_modules,
            quantize_4bit=cfg.quantize_4bit,
            use_dora=cfg.use_dora,
        )

        # Apply LoRA adapters (freezes base weights)
        n_layers = apply_lora(self.model, self.lora_cfg)
        trainable, total = lora_trainable_params(self.model)
        logger.info(
            "LoRATrainer ready: %d LoRA layers, %s trainable / %s total params (%.2f%%)",
            n_layers, f"{trainable:,}", f"{total:,}", 100 * trainable / max(total, 1),
        )

        # Optionally resume adapter
        if cfg.resume_adapter:
            LoRASaveLoad.load(self.model, cfg.resume_adapter)

        # Optimiser — only LoRA params
        self.optimiser = torch.optim.AdamW(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=cfg.lora_lr,
            betas=(cfg.beta1, cfg.beta2),
            eps=cfg.eps,
            weight_decay=cfg.weight_decay,
        )

        # Mixed precision
        self.use_amp = (
            cfg.mixed_precision
            and self.device.type == "cuda"
        )
        self.scaler = torch.cuda.amp.GradScaler(enabled=self.use_amp)

        Path(cfg.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, steps: Optional[int] = None) -> List[Dict]:
        """Run the LoRA training loop for *steps* gradient updates.

        If *steps* is None, uses ``cfg.total_steps``.
        Returns a list of per-log-interval metric dicts.
        """
        total_steps = steps or self.cfg.total_steps
        self.model.train()

        loader_iter = self._infinite_loader()
        acc_loss = 0.0
        t0 = time.monotonic()

        while self.step < total_steps:
            batch = next(loader_iter)
            loss_val = self._gradient_step(batch)
            acc_loss += loss_val

            # Log
            if (self.step + 1) % self.cfg.log_every == 0:
                elapsed = time.monotonic() - t0
                lr = _get_lr(self.step, self.cfg)
                avg_loss = acc_loss / self.cfg.log_every
                ppl = math.exp(min(avg_loss, 20))
                record = {
                    "step": self.step + 1,
                    "loss": round(avg_loss, 4),
                    "ppl": round(ppl, 2),
                    "lr": round(lr, 8),
                    "elapsed_s": round(elapsed, 1),
                }
                self._metrics.append(record)
                logger.info(
                    "[LoRA step %d/%d] loss=%.4f ppl=%.2f lr=%.2e",
                    self.step + 1, total_steps, avg_loss, ppl, lr,
                )
                acc_loss = 0.0

            # Evaluation
            if self.val_loader and (self.step + 1) % self.cfg.eval_every == 0:
                val_loss = self._eval_pass()
                logger.info("[LoRA eval step %d] val_loss=%.4f", self.step + 1, val_loss)

            # Checkpoint
            if (self.step + 1) % self.cfg.save_every == 0:
                self.save_adapter(
                    str(Path(self.cfg.checkpoint_dir) / f"{self.cfg.run_name}_step{self.step+1}.pt")
                )

            self.step += 1

        # Final checkpoint
        self.save_adapter(
            str(Path(self.cfg.checkpoint_dir) / f"{self.cfg.run_name}_final.pt")
        )

        if self.cfg.merge_on_finish:
            merged = merge_lora(self.model)
            logger.info("LoRA merged into base weights (%d layers)", merged)

        return self._metrics

    def _gradient_step(self, batch: Any) -> float:
        """Execute one gradient-accumulation mini-step. Returns raw loss value."""
        input_ids, targets = self._unpack_batch(batch)

        with torch.cuda.amp.autocast(enabled=self.use_amp):
            _, loss = self.model(input_ids, targets)
            loss = loss / self.cfg.grad_accum_steps

        self.scaler.scale(loss).backward()

        if (self.step + 1) % self.cfg.grad_accum_steps == 0:
            # Gradient clipping (only LoRA params)
            self.scaler.unscale_(self.optimiser)
            nn.utils.clip_grad_norm_(
                [p for p in self.model.parameters() if p.requires_grad],
                self.cfg.grad_clip,
            )
            self.scaler.step(self.optimiser)
            self.scaler.update()
            self.optimiser.zero_grad(set_to_none=True)

            # Update LR
            lr = _get_lr(self.step, self.cfg)
            for pg in self.optimiser.param_groups:
                pg["lr"] = lr

        return loss.item() * self.cfg.grad_accum_steps

    @torch.no_grad()
    def _eval_pass(self) -> float:
        self.model.eval()
        total_loss, n = 0.0, 0
        for batch in self.val_loader:  # type: ignore[union-attr]
            input_ids, targets = self._unpack_batch(batch)
            _, loss = self.model(input_ids, targets)
            total_loss += loss.item()
            n += 1
            if n >= 50:
                break
        self.model.train()
        return total_loss / max(n, 1)

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------

    def save_adapter(self, path: str) -> None:
        """Save only the LoRA adapter weights (lightweight checkpoint)."""
        LoRASaveLoad.save(
            self.model,
            path,
            config=self.lora_cfg,
            step=self.step,
            metadata={"run_name": self.cfg.run_name},
        )

    def load_adapter(self, path: str) -> None:
        """Load LoRA adapter weights into the current model."""
        LoRASaveLoad.load(self.model, path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_base_model(self, path: str) -> None:
        ckpt = torch.load(path, map_location=self.device, weights_only=True)
        state = ckpt.get("model_state") or ckpt.get("model_state_dict") or ckpt
        self.model.load_state_dict(state, strict=False)
        logger.info("Base model loaded from %s", path)

    def _unpack_batch(
        self, batch: Any
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Unpack a batch dict or tuple into (input_ids, targets)."""
        if isinstance(batch, dict):
            input_ids = batch["input_ids"].to(self.device)
            targets = batch.get("targets", batch.get("labels", input_ids)).to(self.device)
        else:
            input_ids, targets = batch[0].to(self.device), batch[1].to(self.device)
        return input_ids, targets

    def _infinite_loader(self) -> Iterator[Any]:
        """Cycle through the training loader indefinitely."""
        while True:
            yield from self.train_loader
