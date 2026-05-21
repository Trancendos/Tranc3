"""
TRANC3 — Core Configuration
All model, training, and inference parameters in one place.
Swap values here; nothing else in the codebase needs to change.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    # Vocabulary & sequence
    vocab_size: int = 32_000
    max_seq_len: int = 1024

    # Architecture
    n_layers: int = 6
    n_heads: int = 8
    d_model: int = 512          # embedding dimension
    d_ff: int = 2048            # feed-forward inner dimension
    dropout: float = 0.1

    # Derived (do not set manually)
    d_head: int = field(init=False)

    def __post_init__(self):
        assert self.d_model % self.n_heads == 0, \
            f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})"
        self.d_head = self.d_model // self.n_heads


@dataclass
class TrainingConfig:
    # Data
    data_dir: str = "data/processed"
    checkpoint_dir: str = "models"

    # Training loop
    batch_size: int = 16
    grad_accum_steps: int = 4       # effective batch = batch_size * grad_accum_steps
    max_steps: int = 50_000
    warmup_steps: int = 2_000
    eval_every: int = 500
    save_every: int = 1_000

    # Optimiser
    learning_rate: float = 3e-4
    weight_decay: float = 0.1
    grad_clip: float = 1.0
    beta1: float = 0.9
    beta2: float = 0.95

    # Hardware
    device: str = "auto"            # "auto" | "cuda" | "cpu"
    mixed_precision: bool = True    # fp16 on GPU, ignored on CPU

    # Logging
    log_interval: int = 50
    run_name: str = "tranc3-v1"


@dataclass
class InferenceConfig:
    max_new_tokens: int = 512
    temperature: float = 0.8
    top_k: int = 50
    top_p: float = 0.92
    repetition_penalty: float = 1.15
    device: str = "auto"
