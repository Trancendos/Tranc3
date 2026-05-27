"""
lora.py — Low-Rank Adaptation (LoRA / QLoRA) for Tranc3 models
===============================================================
Implements parameter-efficient fine-tuning via low-rank adapters:

    W_adapted = W_frozen + (B @ A) * scale
      where A ∈ R^(r × in_features)
            B ∈ R^(out_features × r)
            scale = lora_alpha / r

For QLoRA: the base model is loaded in 4-bit precision (requires
``bitsandbytes``) and only the LoRA adapters are trained in bf16.
The module gracefully degrades to standard LoRA when bitsandbytes
is unavailable.

Usage
-----
    from src.training.lora import LoRAConfig, apply_lora, merge_lora, LoRASaveLoad

    # 1. Create config
    cfg = LoRAConfig(rank=8, alpha=16, target_modules=["q_proj", "v_proj"])

    # 2. Apply LoRA to an existing model (freezes base weights)
    apply_lora(model, cfg)

    # 3. Train — only LoRA params have requires_grad=True
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=2e-4
    )

    # 4. Save / load adapters
    LoRASaveLoad.save(model, "checkpoints/lora_adapter.pt")
    LoRASaveLoad.load(model, "checkpoints/lora_adapter.pt")

    # 5. Merge weights permanently (for deployment)
    merge_lora(model)

Zero-cost: no paid external services required.
Optional: bitsandbytes for 4-bit quantisation (QLoRA).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional quantisation import (bitsandbytes)
# ---------------------------------------------------------------------------

try:
    import bitsandbytes as bnb  # type: ignore[import-untyped]
    _BNB_AVAILABLE = True
except ImportError:
    _BNB_AVAILABLE = False
    logger.debug("bitsandbytes not available — QLoRA 4-bit disabled, using standard LoRA")


# ---------------------------------------------------------------------------
# LoRA configuration
# ---------------------------------------------------------------------------

@dataclass
class LoRAConfig:
    """Configuration for LoRA / QLoRA adaptation.

    Attributes
    ----------
    rank:
        The intrinsic rank *r* of the low-rank matrices.  Typical values:
        4 (very lightweight), 8 (balanced), 16-32 (high-fidelity fine-tune).
    alpha:
        Scaling factor.  ``scale = alpha / rank``.  Setting alpha == rank
        gives scale = 1.  Typical: alpha = 2 * rank.
    dropout:
        Dropout probability applied to the LoRA activations during training.
    target_modules:
        Names (or suffixes) of ``nn.Linear`` layers to adapt.  Any module
        whose *name* ends with one of these strings will be wrapped.
        Defaults cover both AdvancedTransformerModel and Tranc3Model.
    quantize_4bit:
        Use bitsandbytes 4-bit base weights (QLoRA).  Requires bitsandbytes.
        Falls back to fp16 with a warning if unavailable.
    use_dora:
        Apply DoRA (Weight-Decomposed Low-Rank Adaptation) on top of LoRA.
        Improves adaptation at higher ranks.  Experimental.
    """
    rank: int = 8
    alpha: float = 16.0
    dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: [
        # AdvancedTransformerModel attention projections
        "q_proj", "k_proj", "v_proj", "out_proj",
        # Tranc3Model combined projection + FFN (selectively)
        "qkv_proj",
        # Feed-forward down projection (often most impactful)
        "down_proj",
    ])
    quantize_4bit: bool = False
    use_dora: bool = False

    @property
    def scale(self) -> float:
        return self.alpha / max(self.rank, 1)


# ---------------------------------------------------------------------------
# LoRA linear layer
# ---------------------------------------------------------------------------

class LoRALinear(nn.Module):
    """A frozen ``nn.Linear`` augmented with trainable low-rank adapters.

    The original weight ``W`` is frozen.  Two small matrices are added:
      - ``lora_A`` (rank × in_features) initialised with kaiming uniform
      - ``lora_B`` (out_features × rank) initialised to zeros → output = 0 at init

    This ensures the adapted model starts identical to the base model.
    """

    def __init__(
        self,
        base_linear: nn.Linear,
        rank: int,
        alpha: float,
        dropout: float = 0.0,
        use_dora: bool = False,
    ) -> None:
        super().__init__()

        self.in_features = base_linear.in_features
        self.out_features = base_linear.out_features
        self.rank = rank
        self.scale = alpha / max(rank, 1)
        self.use_dora = use_dora

        # Frozen base weight
        self.weight = nn.Parameter(base_linear.weight.data.clone(), requires_grad=False)
        if base_linear.bias is not None:
            self.bias = nn.Parameter(base_linear.bias.data.clone(), requires_grad=False)
        else:
            self.bias = None

        # Trainable low-rank matrices
        self.lora_A = nn.Parameter(torch.empty(rank, self.in_features))
        self.lora_B = nn.Parameter(torch.zeros(self.out_features, rank))

        # DoRA: per-output-dimension magnitude vector
        if use_dora:
            weight_norm = self.weight.norm(dim=1, keepdim=True)
            self.dora_m = nn.Parameter(weight_norm.clone())

        self.lora_dropout = nn.Dropout(p=dropout) if dropout > 0.0 else nn.Identity()

        # Initialise A with kaiming uniform (standard practice for LoRA)
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Base output (frozen)
        base_out = F.linear(x, self.weight, self.bias)

        # Low-rank adapter: B @ A @ x * scale
        lora_out = F.linear(
            F.linear(self.lora_dropout(x), self.lora_A),
            self.lora_B,
        ) * self.scale

        if self.use_dora:
            # DoRA: re-normalise base weight direction, scale by learned magnitude
            self.weight.norm(dim=1, keepdim=True).clamp(min=1e-8)
            adapted_w = (self.weight + (self.lora_B @ self.lora_A) * self.scale)
            adapted_norm = adapted_w.norm(dim=1, keepdim=True).clamp(min=1e-8)
            dora_out = F.linear(x, (self.dora_m / adapted_norm) * adapted_w, self.bias)
            return dora_out

        return base_out + lora_out

    def merge(self) -> nn.Linear:
        """Return a plain ``nn.Linear`` with LoRA weights merged into base weights."""
        merged_w = self.weight + (self.lora_B @ self.lora_A) * self.scale
        merged = nn.Linear(self.in_features, self.out_features, bias=self.bias is not None)
        merged.weight = nn.Parameter(merged_w)
        if self.bias is not None:
            merged.bias = nn.Parameter(self.bias.clone())
        return merged

    def extra_repr(self) -> str:
        return (
            f"in={self.in_features}, out={self.out_features}, "
            f"rank={self.rank}, scale={self.scale:.4f}, dora={self.use_dora}"
        )


# ---------------------------------------------------------------------------
# 4-bit quantised LoRA layer (QLoRA)
# ---------------------------------------------------------------------------

class QLoRALinear(nn.Module):
    """LoRA on top of a 4-bit quantised base weight (QLoRA).

    Requires bitsandbytes.  Falls back to LoRALinear with a warning if
    bitsandbytes is unavailable.
    """

    def __new__(cls, base_linear: nn.Linear, rank: int, alpha: float,
                dropout: float = 0.0, **kwargs) -> nn.Module:
        if not _BNB_AVAILABLE:
            logger.warning(
                "bitsandbytes not available — QLoRALinear falling back to LoRALinear"
            )
            return LoRALinear(base_linear, rank, alpha, dropout, **kwargs)
        instance = super().__new__(cls)
        return instance

    def __init__(
        self,
        base_linear: nn.Linear,
        rank: int,
        alpha: float,
        dropout: float = 0.0,
    ) -> None:
        if not _BNB_AVAILABLE:
            return  # __new__ returned a LoRALinear; __init__ won't run
        super().__init__()
        self.rank = rank
        self.scale = alpha / max(rank, 1)
        self.in_features = base_linear.in_features
        self.out_features = base_linear.out_features

        # Quantise base weight to 4-bit NF4
        self.base = bnb.nn.Linear4bit(
            base_linear.in_features,
            base_linear.out_features,
            bias=base_linear.bias is not None,
            quant_type="nf4",
            compute_dtype=torch.bfloat16,
        )
        self.base.weight = bnb.nn.Params4bit(
            base_linear.weight.data,
            requires_grad=False,
            quant_type="nf4",
        )
        if base_linear.bias is not None:
            self.base.bias = nn.Parameter(
                base_linear.bias.data.clone(), requires_grad=False
            )

        # Trainable LoRA adapters in bf16
        self.lora_A = nn.Parameter(
            torch.empty(rank, self.in_features, dtype=torch.bfloat16)
        )
        self.lora_B = nn.Parameter(
            torch.zeros(self.out_features, rank, dtype=torch.bfloat16)
        )
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
        self.lora_dropout = nn.Dropout(p=dropout) if dropout > 0.0 else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base_out = self.base(x)
        lora_out = F.linear(
            F.linear(self.lora_dropout(x.to(torch.bfloat16)), self.lora_A),
            self.lora_B,
        ) * self.scale
        return base_out + lora_out.to(base_out.dtype)


# ---------------------------------------------------------------------------
# Apply / remove / merge helpers
# ---------------------------------------------------------------------------

def _matches_target(name: str, target_modules: List[str]) -> bool:
    """Return True if *name* ends with any of the *target_modules* strings."""
    return any(name == t or name.endswith(f".{t}") for t in target_modules)


def apply_lora(
    model: nn.Module,
    config: LoRAConfig,
    verbose: bool = True,
) -> int:
    """Replace targeted ``nn.Linear`` layers with LoRA-wrapped versions in-place.

    All base model parameters are frozen.  Only LoRA adapter parameters
    (``lora_A``, ``lora_B``, optionally ``dora_m``) remain trainable.

    Returns the number of LoRA layers inserted.
    """
    # Freeze everything first
    for param in model.parameters():
        param.requires_grad_(False)

    layer_cls = QLoRALinear if config.quantize_4bit else LoRALinear
    replaced: List[str] = []

    for name, module in list(model.named_modules()):
        if not isinstance(module, nn.Linear):
            continue
        if not _matches_target(name, config.target_modules):
            continue
        if isinstance(module, (LoRALinear, QLoRALinear)):
            continue  # already wrapped

        # Construct replacement
        lora_layer = layer_cls(
            module,
            rank=config.rank,
            alpha=config.alpha,
            dropout=config.dropout,
            **({"use_dora": config.use_dora} if layer_cls is LoRALinear else {}),
        )

        # Navigate to parent and replace child
        parts = name.split(".")
        parent = model
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], lora_layer)
        replaced.append(name)

    if verbose:
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        pct = 100 * trainable / max(total, 1)
        logger.info(
            "LoRA applied: %d layers wrapped (%s). "
            "Trainable params: %s / %s (%.2f%%)",
            len(replaced),
            ", ".join(replaced[:6]) + ("..." if len(replaced) > 6 else ""),
            f"{trainable:,}",
            f"{total:,}",
            pct,
        )

    return len(replaced)


def remove_lora(model: nn.Module) -> int:
    """Remove all LoRA adapters, restoring original Linear layers.

    Base weights are UN-frozen after removal.  Returns count removed.
    """
    removed = 0
    for name, module in list(model.named_modules()):
        if not isinstance(module, LoRALinear):
            continue
        parts = name.split(".")
        parent = model
        for part in parts[:-1]:
            parent = getattr(parent, part)
        plain = nn.Linear(module.in_features, module.out_features, bias=module.bias is not None)
        plain.weight = nn.Parameter(module.weight.clone())
        if module.bias is not None:
            plain.bias = nn.Parameter(module.bias.clone())
        setattr(parent, parts[-1], plain)
        removed += 1

    # Unfreeze base model
    for param in model.parameters():
        param.requires_grad_(True)

    logger.info("LoRA removed: %d layers restored", removed)
    return removed


def merge_lora(model: nn.Module) -> int:
    """Permanently merge LoRA adapters into base weights.

    After merging the model behaves identically to a fully fine-tuned model
    and has no LoRA overhead at inference time.  Returns count merged.
    """
    merged = 0
    for name, module in list(model.named_modules()):
        if not isinstance(module, LoRALinear):
            continue
        parts = name.split(".")
        parent = model
        for part in parts[:-1]:
            parent = getattr(parent, part)
        setattr(parent, parts[-1], module.merge())
        merged += 1

    # Unfreeze merged model
    for param in model.parameters():
        param.requires_grad_(True)

    logger.info("LoRA merged: %d layers permanently baked in", merged)
    return merged


def lora_state_dict(model: nn.Module) -> Dict[str, torch.Tensor]:
    """Return only the LoRA adapter parameters (not the frozen base weights).

    Use this to save a lightweight adapter checkpoint (~1–5% of full model size).
    """
    sd: Dict[str, torch.Tensor] = {}
    for name, param in model.named_parameters():
        if param.requires_grad:
            sd[name] = param.data.clone()
    return sd


def lora_trainable_params(model: nn.Module) -> Tuple[int, int]:
    """Return (trainable_count, total_count) parameter counts."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return trainable, total


# ---------------------------------------------------------------------------
# Save / load helpers
# ---------------------------------------------------------------------------

class LoRASaveLoad:
    """Lightweight checkpoint utilities for LoRA adapters.

    Only the adapter parameters are saved — the base weights stay frozen
    and are loaded separately.  Checkpoint size is typically 1–5% of a
    full model checkpoint.
    """

    @staticmethod
    def save(
        model: nn.Module,
        path: str,
        config: Optional[LoRAConfig] = None,
        step: int = 0,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Save LoRA adapter weights and config to *path*."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict = {
            "lora_state": lora_state_dict(model),
            "step": step,
        }
        if config is not None:
            payload["lora_config"] = {
                "rank": config.rank,
                "alpha": config.alpha,
                "dropout": config.dropout,
                "target_modules": config.target_modules,
                "quantize_4bit": config.quantize_4bit,
                "use_dora": config.use_dora,
            }
        if metadata:
            payload["metadata"] = metadata
        torch.save(payload, out)
        adapter_mb = out.stat().st_size / 1024 / 1024
        logger.info("LoRA adapter saved → %s (%.2f MB)", out, adapter_mb)

    @staticmethod
    def load(model: nn.Module, path: str, strict: bool = True) -> Dict:
        """Load LoRA adapter weights into an already-patched model.

        The model must have ``apply_lora()`` called first so the LoRA
        layers exist.  Returns the full checkpoint dict.
        """
        payload = torch.load(path, map_location="cpu", weights_only=True)
        missing, unexpected = [], []
        state = payload.get("lora_state", payload)
        {n for n, _ in model.named_parameters() if "lora_" in n}
        for k, v in state.items():
            if "lora_" not in k and "dora_m" not in k:
                continue
            try:
                parts = k.split(".")
                obj = model
                for p in parts[:-1]:
                    obj = getattr(obj, p)
                getattr(obj, parts[-1]).data.copy_(v)
            except (AttributeError, RuntimeError):
                if strict:
                    raise
                missing.append(k)
        logger.info(
            "LoRA adapter loaded from %s (missing=%d, unexpected=%d)",
            path, len(missing), len(unexpected),
        )
        return payload


# ---------------------------------------------------------------------------
# Gradient checkpointing utility
# ---------------------------------------------------------------------------

def enable_gradient_checkpointing(model: nn.Module) -> None:
    """Enable gradient checkpointing on transformer blocks to reduce VRAM.

    Trades compute for memory: activations are recomputed during backward
    instead of stored.  Compatible with LoRA — only LoRA adapters need
    their gradients retained.
    """
    for module in model.modules():
        # Support both Tranc3Model TransformerBlock and AdvancedTransformerModel layers
        cls_name = type(module).__name__
        if "Block" in cls_name or "Layer" in cls_name:
            if hasattr(module, "gradient_checkpointing"):
                module.gradient_checkpointing = True
            elif hasattr(module, "_gradient_checkpointing_func"):
                pass  # already set up by HF-style API
    logger.info("Gradient checkpointing enabled (VRAM optimisation active)")
