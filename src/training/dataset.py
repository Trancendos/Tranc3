"""
TRANC3 — Dataset Handler
Loads and prepares conversation data for training.

Supports two data formats:
  1. JSONL conversation files  ({"turns": [{"role": ..., "content": ...}]})
  2. Plain text files          (raw documents, split into chunks)

The empathetic dialogue dataset and daily dialogue dataset both
convert cleanly into format 1 via the provided download script.
"""

import json
import random
from pathlib import Path
from typing import Dict, List

import torch
from torch.utils.data import DataLoader, Dataset

from ..core.tokenizer import Tranc3Tokenizer


class ConversationDataset(Dataset):
    """
    Loads tokenized conversation data for language model training.
    Each sample is a fixed-length chunk of token IDs.
    Input = tokens[:-1], Target = tokens[1:] (next-token prediction).
    """

    def __init__(
        self,
        data_dir: str,
        tokenizer: Tranc3Tokenizer,
        split: str = "train",           # "train" | "val"
        max_seq_len: int = 1024,
        system_prompt: str = "",
    ):
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len
        self.system_prompt = system_prompt

        data_path = Path(data_dir) / split
        if not data_path.exists():
            raise FileNotFoundError(
                f"Data split not found: {data_path}\n"
                f"Run: python scripts/prepare_data.py"
            )

        self.samples = self._load_and_tokenize(data_path)
        print(f"[Dataset] {split}: {len(self.samples):,} samples loaded")

    def _load_and_tokenize(self, data_path: Path) -> List[List[int]]:
        samples = []

        for file_path in sorted(data_path.glob("*.jsonl")):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    turns = record.get("turns", [])
                    if not turns:
                        continue

                    ids = self.tokenizer.format_conversation(
                        system_prompt=self.system_prompt,
                        turns=turns,
                        add_generation_prompt=False,
                    )

                    # Split long conversations into max_seq_len chunks
                    for start in range(0, len(ids), self.max_seq_len):
                        chunk = ids[start: start + self.max_seq_len + 1]
                        if len(chunk) < 8:   # skip tiny fragments
                            continue
                        samples.append(chunk)

        # Also handle plain text files
        for file_path in sorted(data_path.glob("*.txt")):
            text = file_path.read_text(encoding="utf-8")
            ids = self.tokenizer.encode(text, add_bos=True, add_eos=True)
            for start in range(0, len(ids), self.max_seq_len):
                chunk = ids[start: start + self.max_seq_len + 1]
                if len(chunk) < 8:
                    continue
                samples.append(chunk)

        random.shuffle(samples)
        return samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        ids = self.samples[idx]

        # Pad or truncate to max_seq_len + 1
        target_len = self.max_seq_len + 1
        if len(ids) < target_len:
            ids = ids + [0] * (target_len - len(ids))   # 0 = PAD_ID
        else:
            ids = ids[:target_len]

        ids_tensor = torch.tensor(ids, dtype=torch.long)

        return {
            "input_ids": ids_tensor[:-1],   # (max_seq_len,)
            "targets": ids_tensor[1:],       # (max_seq_len,) shifted by 1
        }


def build_dataloader(
    dataset: ConversationDataset,
    batch_size: int,
    shuffle: bool = True,
    num_workers: int = 0,
) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        drop_last=True,
    )
