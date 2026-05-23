"""
TRANC3 — Data Preparation Script
Downloads and converts open-source conversation datasets into the JSONL
format expected by ConversationDataset.

Datasets used:
  1. EmpatheticDialogues (Facebook AI Research) — empathetic conversations
  2. DailyDialog — general multi-turn dialogue

Run this once before training:
  python scripts/prepare_data.py

Output structure:
  data/processed/train/*.jsonl
  data/processed/val/*.jsonl
"""

import argparse
import json
import os
import random
from pathlib import Path

from shared_core.path_validation import validate_path


def write_jsonl(records, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    validate_path(path, os.getcwd())
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  Written: {path} ({len(records):,} records)")


def download_empathetic_dialogues(output_dir: str):
    """
    Downloads EmpatheticDialogues from the HuggingFace datasets hub
    using the datasets library (no API key required — public dataset).
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("  [!] Install datasets library: pip install datasets")
        return []

    print("Downloading EmpatheticDialogues...")
    ds = load_dataset("empathetic_dialogues", trust_remote_code=True)

    records = []
    for split_name in ["train", "validation"]:
        split = ds[split_name]
        # Group by conv_id
        convs = {}
        for row in split:
            cid = row["conv_id"]
            if cid not in convs:
                convs[cid] = []
            convs[cid].append(row)

        for _cid, rows in convs.items():
            rows.sort(key=lambda r: r["utterance_idx"])
            turns = []
            for _i, row in enumerate(rows):
                role = "user" if _i % 2 == 0 else "assistant"
                turns.append({"role": role, "content": row["utterance"].strip()})
            if len(turns) >= 2:
                records.append({"source": "empathetic_dialogues", "turns": turns})

    random.shuffle(records)
    split_idx = int(len(records) * 0.95)
    write_jsonl(records[:split_idx], f"{output_dir}/train/empathetic.jsonl")
    write_jsonl(records[split_idx:], f"{output_dir}/val/empathetic.jsonl")
    return records


def download_daily_dialog(output_dir: str):
    """
    Downloads DailyDialog dataset — general conversation, clean multi-turn.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("  [!] Install datasets library: pip install datasets")
        return []

    print("Downloading DailyDialog...")
    ds = load_dataset("daily_dialog", trust_remote_code=True)

    records = []
    for split_name in ["train", "validation"]:
        for item in ds[split_name]:
            utterances = item["dialog"]
            turns = []
            for i, utt in enumerate(utterances):
                role = "user" if i % 2 == 0 else "assistant"
                text = utt.strip()
                if text:
                    turns.append({"role": role, "content": text})
            if len(turns) >= 2:
                records.append({"source": "daily_dialog", "turns": turns})

    random.shuffle(records)
    split_idx = int(len(records) * 0.95)
    write_jsonl(records[:split_idx], f"{output_dir}/train/daily_dialog.jsonl")
    write_jsonl(records[split_idx:], f"{output_dir}/val/daily_dialog.jsonl")
    return records


def load_custom_data(custom_dir: str, output_dir: str):
    """
    Loads any custom JSONL files you place in data/raw/custom/.
    Format: {"turns": [{"role": "user"|"assistant", "content": "..."}]}
    These take priority and can encode Tranc3-specific behaviour.
    """
    custom_path = Path(custom_dir) / "custom"
    if not custom_path.exists():
        return

    records = []
    for f in custom_path.glob("*.jsonl"):
        print(f"Loading custom data: {f.name}")
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass  # nosec B110 — graceful degradation

    if records:
        random.shuffle(records)
        split_idx = int(len(records) * 0.95)
        write_jsonl(records[:split_idx], f"{output_dir}/train/custom.jsonl")
        write_jsonl(records[split_idx:], f"{output_dir}/val/custom.jsonl")
        print(f"  Custom data: {len(records):,} records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output_dir", default="data/processed")
    parser.add_argument("--raw_dir", default="data/raw")
    parser.add_argument("--skip_download", action="store_true",
                        help="Skip downloading public datasets (use custom data only)")
    args = parser.parse_args()

    print("\n=== TRANC3 Data Preparation ===\n")

    if not args.skip_download:
        download_empathetic_dialogues(args.output_dir)
        download_daily_dialog(args.output_dir)

    load_custom_data(args.raw_dir, args.output_dir)

    print("\nData preparation complete.")
    print(f"Training data: {args.output_dir}/train/")
    print(f"Validation data: {args.output_dir}/val/")
    print("\nNext step: python scripts/train_tokenizer.py")
