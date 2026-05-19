"""
TRANC3 — Training Engine
Full training loop with:
  - Gradient accumulation (train on large effective batch without large GPU RAM)
  - Cosine LR schedule with warmup
  - Mixed precision (fp16 on GPU, auto-disabled on CPU)
  - Checkpoint save/resume
  - Validation loop with perplexity reporting
"""

import os
import math
import time
import json
import torch
import torch.nn as nn
from pathlib import Path
from typing import Optional
from torch.cuda.amp import GradScaler, autocast

from ..core.model import Tranc3Model
from ..core.config import ModelConfig, TrainingConfig
from ..core.tokenizer import Tranc3Tokenizer
from ..training.dataset import ConversationDataset, build_dataloader


def get_device(config: TrainingConfig) -> torch.device:
    if config.device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(config.device)


def cosine_lr(step: int, warmup: int, total: int, base_lr: float) -> float:
    """Cosine decay with linear warmup."""
    if step < warmup:
        return base_lr * step / max(warmup, 1)
    progress = (step - warmup) / max(total - warmup, 1)
    return base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


class Trainer:
    def __init__(
        self,
        model_config: ModelConfig,
        train_config: TrainingConfig,
        tokenizer: Tranc3Tokenizer,
        system_prompt: str = "",
    ):
        self.cfg = train_config
        self.device = get_device(train_config)
        print(f"[Trainer] Device: {self.device}")

        # Model
        self.model = Tranc3Model(model_config).to(self.device)
        print(f"[Trainer] Parameters — {self.model.parameter_count()}")

        # Optimiser — AdamW with decoupled weight decay
        self.optimiser = torch.optim.AdamW(
            self.model.parameters(),
            lr=train_config.learning_rate,
            betas=(train_config.beta1, train_config.beta2),
            weight_decay=train_config.weight_decay,
        )

        # Mixed precision scaler (only active on CUDA)
        self.use_amp = train_config.mixed_precision and self.device.type == "cuda"
        self.scaler = GradScaler(enabled=self.use_amp)

        # Datasets
        self.train_dataset = ConversationDataset(
            train_config.data_dir,
            tokenizer,
            split="train",
            max_seq_len=model_config.max_seq_len,
            system_prompt=system_prompt,
        )
        self.val_dataset = ConversationDataset(
            train_config.data_dir,
            tokenizer,
            split="val",
            max_seq_len=model_config.max_seq_len,
            system_prompt=system_prompt,
        )

        self.train_loader = build_dataloader(self.train_dataset, train_config.batch_size)
        self.val_loader = build_dataloader(self.val_dataset, train_config.batch_size, shuffle=False)

        self.step = 0
        self.best_val_loss = float("inf")

        os.makedirs(train_config.checkpoint_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------

    def _train_step(self, batch) -> float:
        input_ids = batch["input_ids"].to(self.device)
        targets = batch["targets"].to(self.device)

        with autocast(enabled=self.use_amp):
            _, loss = self.model(input_ids, targets)
            loss = loss / self.cfg.grad_accum_steps

        self.scaler.scale(loss).backward()
        return loss.item() * self.cfg.grad_accum_steps

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @torch.no_grad()
    def evaluate(self) -> float:
        self.model.eval()
        total_loss = 0.0
        n_batches = 0

        for batch in self.val_loader:
            input_ids = batch["input_ids"].to(self.device)
            targets = batch["targets"].to(self.device)
            _, loss = self.model(input_ids, targets)
            total_loss += loss.item()
            n_batches += 1
            if n_batches >= 50:   # cap validation at 50 batches for speed
                break

        self.model.train()
        avg_loss = total_loss / max(n_batches, 1)
        perplexity = math.exp(min(avg_loss, 20))   # cap to avoid overflow display
        return avg_loss, perplexity

    # ------------------------------------------------------------------
    # Checkpoint save / load
    # ------------------------------------------------------------------

    def save_checkpoint(self, tag: str = "latest"):
        path = Path(self.cfg.checkpoint_dir) / f"{self.cfg.run_name}_{tag}.pt"
        torch.save({
            "step": self.step,
            "model_state": self.model.state_dict(),
            "optimiser_state": self.optimiser.state_dict(),
            "best_val_loss": self.best_val_loss,
        }, path)
        print(f"[Checkpoint] Saved → {path}")

    def load_checkpoint(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state"])
        self.optimiser.load_state_dict(ckpt["optimiser_state"])
        self.step = ckpt["step"]
        self.best_val_loss = ckpt.get("best_val_loss", float("inf"))
        print(f"[Checkpoint] Resumed from step {self.step}")

    # ------------------------------------------------------------------
    # Main training loop
    # ------------------------------------------------------------------

    def train(self, resume_from: Optional[str] = None):
        if resume_from:
            self.load_checkpoint(resume_from)

        self.model.train()
        data_iter = iter(self.train_loader)
        accum_loss = 0.0
        t0 = time.time()

        print(f"\n[Trainer] Starting training — {self.cfg.max_steps:,} steps")
        print(f"[Trainer] Effective batch size: "
              f"{self.cfg.batch_size * self.cfg.grad_accum_steps}\n")

        while self.step < self.cfg.max_steps:

            # Gradient accumulation loop
            self.optimiser.zero_grad()
            for _ in range(self.cfg.grad_accum_steps):
                try:
                    batch = next(data_iter)
                except StopIteration:
                    data_iter = iter(self.train_loader)
                    batch = next(data_iter)
                accum_loss += self._train_step(batch)

            # Gradient clipping
            self.scaler.unscale_(self.optimiser)
            nn.utils.clip_grad_norm_(self.model.parameters(), self.cfg.grad_clip)

            # LR schedule
            lr = cosine_lr(
                self.step,
                self.cfg.warmup_steps,
                self.cfg.max_steps,
                self.cfg.learning_rate,
            )
            for param_group in self.optimiser.param_groups:
                param_group["lr"] = lr

            self.scaler.step(self.optimiser)
            self.scaler.update()
            self.step += 1

            # Logging
            if self.step % self.cfg.log_interval == 0:
                elapsed = time.time() - t0
                avg_loss = accum_loss / self.cfg.log_interval
                accum_loss = 0.0
                print(
                    f"step {self.step:6d}/{self.cfg.max_steps} | "
                    f"loss {avg_loss:.4f} | "
                    f"lr {lr:.2e} | "
                    f"{elapsed:.1f}s"
                )
                t0 = time.time()

            # Evaluation
            if self.step % self.cfg.eval_every == 0:
                val_loss, ppl = self.evaluate()
                print(f"  → val_loss: {val_loss:.4f} | perplexity: {ppl:.2f}")
                if val_loss < self.best_val_loss:
                    self.best_val_loss = val_loss
                    self.save_checkpoint("best")

            # Periodic save
            if self.step % self.cfg.save_every == 0:
                self.save_checkpoint("latest")

        self.save_checkpoint("final")
        print("\n[Trainer] Training complete.")
