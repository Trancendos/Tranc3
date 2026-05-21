#!/usr/bin/env python3
# train.py — TRANC3 from-scratch training pipeline
#
# Trains the AdvancedTransformerModel (src/core/advanced_model.py) on your
# own data using the Tranc3 tokenizer. Zero dependency on any external model
# weights — this builds Tranc3 from random initialisation.
#
# Usage:
#   python train.py                              # uses synthetic bootstrap data
#   python train.py --data-dir ./data            # JSONL files in data/{lang}/train.jsonl
#   python train.py --data-dir ./data --epochs 5 --model-size small
#   python train.py --resume ./models/tranc3-v1/checkpoint-500.pt
#
# Model sizes:
#   tiny   —  ~10M params  (384 hidden, 6 layers,  6 heads)   trains on CPU in minutes
#   small  —  ~35M params  (512 hidden, 8 layers,  8 heads)   trains on CPU in hours
#   base   —  ~85M params  (768 hidden, 12 layers, 12 heads)  needs GPU for real training
#   medium — ~125M params  (768 hidden, 12 layers, 12 heads, 4x FFN)
#
# Data format (JSONL):
#   {"instruction": "...", "response": "...", "personality": "tranc3-base", "language": "en"}

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tranc3.train")

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ─── Model size presets ────────────────────────────────────────────────────────

MODEL_SIZES = {
    "tiny":   {"hidden_size": 384,  "num_layers": 6,  "num_heads": 6,  "ffn_mult": 4},
    "small":  {"hidden_size": 512,  "num_layers": 8,  "num_heads": 8,  "ffn_mult": 4},
    "base":   {"hidden_size": 768,  "num_layers": 12, "num_heads": 12, "ffn_mult": 4},
    "medium": {"hidden_size": 1024, "num_layers": 16, "num_heads": 16, "ffn_mult": 4},
}


# ─── Chat dataset ─────────────────────────────────────────────────────────────

class ChatDataset(Dataset):
    """Wraps MultilingualDataset samples into tokenised tensors using Tranc3Tokenizer."""

    def __init__(self, tokenizer, data_dir: str, max_length: int = 512,
                 languages: Optional[List[str]] = None):
        from src.core.dataset import MultilingualDataset
        self.tokenizer = tokenizer
        self.max_length = max_length

        self.raw = MultilingualDataset(
            tokenizer=None,    # we handle tokenisation ourselves
            data_dir=data_dir,
            max_length=max_length,
            languages=languages or ["en"],
            split="train",
        )
        logger.info("ChatDataset: %d raw samples", len(self.raw))

    def __len__(self) -> int:
        return len(self.raw.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.raw.samples[idx]
        instruction = sample.get("instruction", sample.get("text", ""))
        response     = sample.get("response", "")
        personality  = sample.get("personality", "tranc3-base")
        system_prompt = sample.get("system_prompt",
                                   f"You are TRANC3, an advanced AI with {personality} personality.")

        # Encode as a single training sequence:
        # <bos> <p:personality> <sys> system <sep> <usr> instruction <sep> <ast> response <eos>
        ids = self.tokenizer.encode_chat(
            system=system_prompt,
            turns=[
                {"role": "user",      "content": instruction},
                {"role": "assistant", "content": response},
            ],
            personality=personality,
            max_length=self.max_length,
        )

        input_ids  = torch.tensor(ids[:-1], dtype=torch.long)
        labels     = torch.tensor(ids[1:],  dtype=torch.long)

        # Pad / truncate to max_length-1
        L = self.max_length - 1
        if len(input_ids) < L:
            pad_len = L - len(input_ids)
            input_ids = torch.cat([input_ids, torch.full((pad_len,), self.tokenizer.pad_token_id)])
            labels    = torch.cat([labels,    torch.full((pad_len,), -100)])
        else:
            input_ids = input_ids[:L]
            labels    = labels[:L]

        return {"input_ids": input_ids, "labels": labels}


# ─── Training loop ─────────────────────────────────────────────────────────────

def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    # ── Tokenizer ─────────────────────────────────────────────────────────────
    tok_dir = Path(args.tokenizer_dir)
    if tok_dir.exists() and (tok_dir / "tokenizer_meta.json").exists():
        from src.core.tranc3_tokenizer import Tranc3Tokenizer
        tokenizer = Tranc3Tokenizer.load(tok_dir)
        logger.info("Loaded tokenizer from %s (vocab=%d)", tok_dir, len(tokenizer))
    else:
        logger.info("Training tokenizer from scratch ...")
        from src.core.tranc3_tokenizer import Tranc3Tokenizer
        # Collect corpus text for tokenizer training
        corpus_texts: List[str] = []
        data_root = Path(args.data_dir)
        if data_root.exists():
            for jsonl in data_root.rglob("*.jsonl"):
                import json
                for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        rec = json.loads(line)
                        corpus_texts.append(rec.get("instruction", "") + " " + rec.get("response", ""))
                    except Exception:
                        pass
            for txt in data_root.rglob("*.txt"):
                corpus_texts.append(txt.read_text(encoding="utf-8", errors="replace"))

        tokenizer = Tranc3Tokenizer.build_from_corpus(
            texts=corpus_texts or None,
            vocab_size=args.vocab_size,
            save_dir=tok_dir,
        )
        logger.info("Tokenizer ready (vocab=%d) — saved to %s", len(tokenizer), tok_dir)

    # ── Model config ──────────────────────────────────────────────────────────
    size_cfg = MODEL_SIZES[args.model_size]

    class ModelConfig:
        vocab_size           = len(tokenizer)
        hidden_size          = size_cfg["hidden_size"]
        num_layers           = size_cfg["num_layers"]
        num_heads            = size_cfg["num_heads"]
        intermediate_size    = size_cfg["hidden_size"] * size_cfg["ffn_mult"]
        max_sequence_length  = args.max_length
        dropout              = args.dropout

    from src.core.advanced_model import AdvancedTransformerModel

    if args.resume:
        logger.info("Resuming from checkpoint: %s", args.resume)
        checkpoint = torch.load(args.resume, map_location=device)
        model = AdvancedTransformerModel(ModelConfig())
        model.load_state_dict(checkpoint["model_state_dict"])
        start_step = checkpoint.get("step", 0)
    else:
        model = AdvancedTransformerModel(ModelConfig())
        start_step = 0

    model = model.to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model: %s | %.2fM parameters", args.model_size, n_params / 1e6)

    # ── Dataset ───────────────────────────────────────────────────────────────
    dataset = ChatDataset(
        tokenizer=tokenizer,
        data_dir=args.data_dir,
        max_length=args.max_length,
        languages=args.languages.split(","),
    )

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        drop_last=True,
    )

    # ── Optimiser + LR schedule ───────────────────────────────────────────────
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        betas=(0.9, 0.95),
        weight_decay=0.1,
    )

    total_steps = len(loader) * args.epochs
    warmup_steps = min(args.warmup_steps, total_steps // 10)

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return step / max(warmup_steps, 1)
        progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
        return 0.1 + 0.9 * 0.5 * (1.0 + torch.cos(torch.tensor(progress * 3.14159)).item())

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    # ── Output dir ────────────────────────────────────────────────────────────
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Training ──────────────────────────────────────────────────────────────
    logger.info("Starting training: %d epochs, %d steps/epoch, %d total steps",
                args.epochs, len(loader), total_steps)

    global_step = start_step
    best_loss = float("inf")

    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        t0 = time.time()

        for batch_idx, batch in enumerate(loader):
            input_ids = batch["input_ids"].to(device)
            labels    = batch["labels"].to(device)

            # Build causal mask
            B, T = input_ids.shape
            causal_mask = torch.tril(torch.ones(T, T, device=device)).unsqueeze(0).unsqueeze(0)

            # Forward
            outputs = model(input_ids=input_ids, attention_mask=causal_mask)
            logits  = outputs["logits"]  # [B, T, vocab]

            # Compute loss
            loss = loss_fn(logits.view(-1, logits.size(-1)), labels.view(-1))

            # Backward
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()
            scheduler.step()

            global_step += 1
            epoch_loss  += loss.item()

            if global_step % args.log_every == 0:
                elapsed = time.time() - t0
                lr_now  = scheduler.get_last_lr()[0]
                logger.info(
                    "epoch=%d step=%d loss=%.4f lr=%.2e elapsed=%.1fs",
                    epoch + 1, global_step, loss.item(), lr_now, elapsed,
                )

            # Checkpoint
            if global_step % args.save_every == 0:
                _save_checkpoint(model, optimizer, scheduler, global_step, output_dir)

        avg_loss = epoch_loss / len(loader)
        logger.info("Epoch %d complete — avg_loss=%.4f", epoch + 1, avg_loss)

        if avg_loss < best_loss:
            best_loss = avg_loss
            _save_checkpoint(model, optimizer, scheduler, global_step, output_dir, best=True)

    # Final save
    _save_checkpoint(model, optimizer, scheduler, global_step, output_dir, final=True)
    logger.info("Training complete. Model saved to %s", output_dir)
    logger.info("To use: set MODEL_PATH=%s in .env", output_dir / "tranc3-final.pt")


def _save_checkpoint(model, optimizer, scheduler, step, out_dir: Path,
                     best: bool = False, final: bool = False):
    state = {
        "step":                  step,
        "model_state_dict":      model.state_dict(),
        "optimizer_state_dict":  optimizer.state_dict(),
        "scheduler_state_dict":  scheduler.state_dict(),
    }
    if final:
        path = out_dir / "tranc3-final.pt"
    elif best:
        path = out_dir / "tranc3-best.pt"
    else:
        path = out_dir / f"checkpoint-{step}.pt"

    torch.save(state, path)
    logger.info("Checkpoint saved: %s", path)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Train TRANC3 from scratch")
    p.add_argument("--model-size",     default="small",            choices=list(MODEL_SIZES))
    p.add_argument("--data-dir",       default="./data")
    p.add_argument("--output-dir",     default="./models/tranc3-v1")
    p.add_argument("--tokenizer-dir",  default="./models/tokenizer")
    p.add_argument("--vocab-size",     type=int,   default=8192)
    p.add_argument("--epochs",         type=int,   default=3)
    p.add_argument("--batch-size",     type=int,   default=8)
    p.add_argument("--max-length",     type=int,   default=256)
    p.add_argument("--lr",             type=float, default=3e-4)
    p.add_argument("--dropout",        type=float, default=0.1)
    p.add_argument("--grad-clip",      type=float, default=1.0)
    p.add_argument("--warmup-steps",   type=int,   default=100)
    p.add_argument("--log-every",      type=int,   default=50)
    p.add_argument("--save-every",     type=int,   default=500)
    p.add_argument("--languages",      default="en")
    p.add_argument("--resume",         default=None, help="Resume from checkpoint .pt file")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(args)
