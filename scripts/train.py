"""
TRANC3 — Training Launch Script
Kick off model training with a single command.

Usage:
  # Start fresh
  python scripts/train.py

  # Resume from checkpoint
  python scripts/train.py --resume models/tranc3-v1_latest.pt

  # Smaller model for CPU-only machines
  python scripts/train.py --size small

Model sizes:
  small  : d_model=256, layers=4, heads=4  (~10M params, CPU feasible)
  medium : d_model=512, layers=6, heads=8  (~50M params, GPU recommended)
  large  : d_model=768, layers=12, heads=12 (~150M params, Slough-grade)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import ModelConfig, TrainingConfig
from src.core.tokenizer import Tranc3Tokenizer
from src.personality.matrix import PersonalityMatrix
from src.training.trainer import Trainer

MODEL_SIZES = {
    "small": {"d_model": 256, "n_layers": 4, "n_heads": 4, "d_ff": 1024},
    "medium": {"d_model": 512, "n_layers": 6, "n_heads": 8, "d_ff": 2048},
    "large": {"d_model": 768, "n_layers": 12, "n_heads": 12, "d_ff": 3072},
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="medium", choices=list(MODEL_SIZES.keys()))
    parser.add_argument("--resume", default=None, help="Path to checkpoint to resume from")
    parser.add_argument("--profile", default="tranc3-base", help="Personality profile to use during training")
    parser.add_argument("--max_steps", type=int, default=50_000)
    parser.add_argument("--batch_size", type=int, default=16)
    args = parser.parse_args()

    print(f"\n=== TRANC3 Training ({args.size}) ===\n")

    # Load tokenizer
    tokenizer_path = "models/tokenizer.model"
    if not os.path.exists(tokenizer_path):
        print(f"Tokenizer not found at {tokenizer_path}")
        print("Run: python scripts/train_tokenizer.py")
        sys.exit(1)

    tokenizer = Tranc3Tokenizer(tokenizer_path)

    # Build configs
    size_params = MODEL_SIZES[args.size]
    model_cfg = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        **size_params,
    )
    train_cfg = TrainingConfig(
        max_steps=args.max_steps,
        batch_size=args.batch_size,
        run_name=f"tranc3-{args.size}",
    )

    # Load personality for system prompt during training
    matrix = PersonalityMatrix()
    profile = matrix.get(args.profile)

    print(f"Model config: {model_cfg}")
    print(f"Training config: {train_cfg}")
    print(f"Active profile: {args.profile}\n")

    trainer = Trainer(
        model_config=model_cfg,
        train_config=train_cfg,
        tokenizer=tokenizer,
        system_prompt=profile.system_prompt,
    )

    trainer.train(resume_from=args.resume)
