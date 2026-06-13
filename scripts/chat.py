"""
TRANC3 — Local Chat Interface
Run a conversation with your trained model from the terminal.

Usage:
  python scripts/chat.py
  python scripts/chat.py --profile tranc3-builder
  python scripts/chat.py --model models/tranc3-medium_best.pt
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import InferenceConfig, ModelConfig
from src.core.tokenizer import Tranc3Tokenizer
from src.inference.engine import Tranc3Engine, run_cli
from src.personality.matrix import PersonalityMatrix

MODEL_SIZES = {
    "small": {"d_model": 256, "n_layers": 4, "n_heads": 4, "d_ff": 1024},
    "medium": {"d_model": 512, "n_layers": 6, "n_heads": 8, "d_ff": 2048},
    "large": {"d_model": 768, "n_layers": 12, "n_heads": 12, "d_ff": 3072},
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/tranc3-medium_best.pt")
    parser.add_argument("--tokenizer", default="models/tokenizer.model")
    parser.add_argument("--size", default="medium", choices=list(MODEL_SIZES.keys()))
    parser.add_argument("--profile", default="tranc3-base")
    args = parser.parse_args()

    for path in [args.model, args.tokenizer]:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            print("Complete training before running chat: python scripts/train.py")
            sys.exit(1)

    tokenizer = Tranc3Tokenizer(args.tokenizer)

    model_cfg = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        **MODEL_SIZES[args.size],
    )
    inf_cfg = InferenceConfig()
    matrix = PersonalityMatrix()

    engine = Tranc3Engine(
        model_path=args.model,
        tokenizer_path=args.tokenizer,
        model_config=model_cfg,
        inference_config=inf_cfg,
        personality_matrix=matrix,
        active_profile=args.profile,
    )

    run_cli(engine)
