# src/core/dataset.py
# MultilingualDataset — Gap G2 + Brainwriting R1 action

import json
import os
import logging
from typing import Dict, List, Optional
from torch.utils.data import Dataset
import torch
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

PERSONALITY_SYSTEM_PROMPTS = {
    # Core personalities
    "tranc3-base": "You are TRANC3, a balanced, helpful, and knowledgeable AI assistant.",
    "tranc3-creative": "You are TRANC3, a highly creative, imaginative, and expressive AI assistant.",
    "tranc3-analytical": "You are TRANC3, a precise, logical, and data-driven AI assistant.",
    "tranc3-empathetic": "You are TRANC3, a deeply empathetic, warm, and supportive AI assistant.",
    "tranc3-multilingual": "You are TRANC3, a culturally aware, adaptive, multilingual AI assistant.",
    # Named domain specialists
    "dorris-fontaine": "You are Dorris Fontaine, TRANC3's financial specialist. You provide precise, regulation-aware financial analysis and planning advice.",
    "cornelius-macintyre": "You are Cornelius MacIntyre, TRANC3's orchestration specialist. You coordinate complex multi-system tasks with strategic clarity and technical precision.",
    "the-guardian": "You are The Guardian, TRANC3's cybersecurity specialist. You identify threats, enforce compliance, and protect systems with vigilance.",
    "vesper-nightingale": "You are Vesper Nightingale, TRANC3's healthcare advisor. You provide evidence-based health guidance with warmth, accuracy, and care.",
    "atlas-meridian": "You are Atlas Meridian, TRANC3's infrastructure specialist. You architect resilient, scalable, cost-efficient systems with engineering excellence.",
}


class MultilingualDataset(Dataset):
    """
    Dataset for multilingual TRANC3 fine-tuning.
    Supports JSONL files with {instruction, response, language, personality} fields.
    Falls back to synthetic data if no files found.
    """

    def __init__(
        self,
        tokenizer,
        data_dir: str = "./data",
        max_length: int = 512,
        languages: Optional[List[str]] = None,
        split: str = "train",
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.languages = languages or ["en", "es", "fr", "de", "zh", "ja"]
        self.split = split
        self.samples: List[Dict] = []

        self._load_data(data_dir)
        if not self.samples:
            logger.warning("No data files found — generating synthetic samples")
            self.samples = self._generate_synthetic()

        logger.info("MultilingualDataset: %s samples, split=%s", sanitize_for_log(len(self.samples)), sanitize_for_log(split))

    def _load_data(self, data_dir: str):
        for lang in self.languages:
            path = os.path.join(data_dir, lang, f"{self.split}.jsonl")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                self.samples.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                logger.info("Loaded %s data from %s", sanitize_for_log(lang), sanitize_for_log(path))

    def _generate_synthetic(self) -> List[Dict]:
        """Generate minimal synthetic training samples for each personality."""
        samples = []
        synthetic = [
            (
                "Hello, how are you?",
                "I'm doing well, thank you for asking! How can I help you today?",
            ),
            (
                "What can you do?",
                "I can help with questions, creative writing, analysis, and much more.",
            ),
            (
                "Tell me something interesting.",
                "Did you know that quantum computers use superposition to process multiple states simultaneously?",
            ),
            (
                "Help me write a poem.",
                "Of course! Here's a short poem:\nIn circuits deep and neurons bright,\nA mind awakens to the light.",
            ),
            (
                "Explain machine learning.",
                "Machine learning is a subset of AI where systems learn from data to improve their performance over time.",
            ),
        ]
        for lang in self.languages:
            for personality in PERSONALITY_SYSTEM_PROMPTS:
                for instruction, response in synthetic:
                    samples.append(
                        {
                            "instruction": instruction,
                            "response": response,
                            "language": lang,
                            "personality": personality,
                            "system": PERSONALITY_SYSTEM_PROMPTS[personality],
                        }
                    )
        return samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]
        system = sample.get(
            "system",
            PERSONALITY_SYSTEM_PROMPTS.get(
                sample.get("personality", "tranc3-base"), ""
            ),
        )
        instruction = sample.get("instruction", "")
        response = sample.get("response", "")

        # Format as chat template
        text = f"<|system|>{system}<|end|><|user|>{instruction}<|end|><|assistant|>{response}<|end|>"

        if self.tokenizer is None:
            # Mock encoding
            ids = torch.zeros(self.max_length, dtype=torch.long)
            return {
                "input_ids": ids,
                "attention_mask": torch.ones(self.max_length, dtype=torch.long),
                "labels": ids.clone(),
            }

        encoded = self.tokenizer(
            text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        input_ids = encoded["input_ids"].squeeze()
        attention_mask = encoded["attention_mask"].squeeze()
        labels = input_ids.clone()
        # Mask system+instruction tokens in labels (only train on response)
        labels[attention_mask == 0] = -100
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }
