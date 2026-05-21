"""
TRANC3 — Tokenizer Training Script
Train the BPE tokenizer on your prepared text data.
Run after prepare_data.py.

Usage:
  python scripts/train_tokenizer.py
  python scripts/train_tokenizer.py --data_dir data/processed --vocab_size 16000
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.tokenizer import train_tokenizer

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="data/processed")
    parser.add_argument("--output_path", default="models/tokenizer.model")
    parser.add_argument("--vocab_size", type=int, default=32000)
    args = parser.parse_args()

    print("\n=== TRANC3 Tokenizer Training ===\n")
    train_tokenizer(
        data_dir=args.data_dir,
        output_path=args.output_path,
        vocab_size=args.vocab_size,
    )
    print("\nNext step: python scripts/train.py")
