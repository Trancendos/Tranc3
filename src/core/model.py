"""
TRANC3 — Transformer Model Architecture
Built from PyTorch primitives. No pre-trained weights, no external model APIs.
This is the architecture you own outright.

Architecture: Decoder-only transformer (GPT-style)
- Multi-head causal self-attention
- Pre-norm (LayerNorm before attention/FFN, more stable training)
- SwiGLU activation in feed-forward (better than ReLU for language tasks)
- Rotary positional embeddings (RoPE) — no learned position table needed
"""

import math
from typing import Optional, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except (ImportError, RuntimeError, OSError):  # pragma: no cover
    # RuntimeError: CUDA init / driver mismatch; OSError: missing shared lib
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
else:
    _TORCH_AVAILABLE = True

from .config import ModelConfig

# ---------------------------------------------------------------------------
# Rotary Positional Embeddings (RoPE)
# ---------------------------------------------------------------------------


class RotaryEmbedding(nn.Module if nn is not None else object):
    """
    Encodes position information directly into the attention query/key vectors.
    More generalizable than learned absolute position embeddings.
    """

    def __init__(self, dim: int, max_seq_len: int = 2048):
        super().__init__()
        inv_freq = 1.0 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)
        self._build_cache(max_seq_len)

    def _build_cache(self, seq_len: int):
        t = torch.arange(seq_len, device=self.inv_freq.device).float()
        freqs = torch.outer(t, self.inv_freq)
        emb = torch.cat([freqs, freqs], dim=-1)
        self.register_buffer("cos_cache", emb.cos()[None, None, :, :])
        self.register_buffer("sin_cache", emb.sin()[None, None, :, :])

    def _rotate_half(self, x: torch.Tensor) -> torch.Tensor:
        half = x.shape[-1] // 2
        x1, x2 = x[..., :half], x[..., half:]
        return torch.cat([-x2, x1], dim=-1)

    def forward(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        seq_len: int,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        cos = self.cos_cache[:, :, :seq_len, :]
        sin = self.sin_cache[:, :, :seq_len, :]
        q_rot = (q * cos) + (self._rotate_half(q) * sin)
        k_rot = (k * cos) + (self._rotate_half(k) * sin)
        return q_rot, k_rot


# ---------------------------------------------------------------------------
# Multi-Head Causal Self-Attention
# ---------------------------------------------------------------------------


class MultiHeadAttention(nn.Module if nn is not None else object):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.n_heads = config.n_heads
        self.d_head = config.d_head
        self.d_model = config.d_model
        self.scale = math.sqrt(self.d_head)

        # Single projection for Q, K, V — more efficient than three separate layers
        self.qkv_proj = nn.Linear(config.d_model, 3 * config.d_model, bias=False)
        self.out_proj = nn.Linear(config.d_model, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

        self.rope = RotaryEmbedding(config.d_head, config.max_seq_len)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, T, C = x.shape

        # Project and split Q, K, V
        qkv = self.qkv_proj(x)
        q, k, v = qkv.split(self.d_model, dim=-1)

        # Reshape to (B, heads, T, d_head)
        def reshape(t):
            return t.view(B, T, self.n_heads, self.d_head).transpose(1, 2)

        q, k, v = reshape(q), reshape(k), reshape(v)

        # Apply rotary embeddings
        q, k = self.rope(q, k, T)

        # Scaled dot-product attention with causal mask
        attn = torch.matmul(q, k.transpose(-2, -1)) / self.scale

        # Build causal mask if not provided
        if mask is None:
            mask = torch.tril(torch.ones(T, T, device=x.device)).bool()
            mask = mask.unsqueeze(0).unsqueeze(0)

        attn = attn.masked_fill(~mask, float("-inf"))
        attn = F.softmax(attn, dim=-1)
        attn = self.dropout(attn)

        # Weighted sum of values
        out = torch.matmul(attn, v)
        out = out.transpose(1, 2).contiguous().view(B, T, C)
        return self.out_proj(out)


# ---------------------------------------------------------------------------
# SwiGLU Feed-Forward Network
# ---------------------------------------------------------------------------


class FeedForward(nn.Module if nn is not None else object):
    """
    SwiGLU activation: better gradient flow and representation capacity
    than standard ReLU/GELU for language modelling.
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        # SwiGLU uses 2/3 of d_ff for the gate — keep parameter count consistent
        hidden = int(2 * config.d_ff / 3)
        hidden = (hidden + 63) // 64 * 64  # round to multiple of 64 for efficiency

        self.gate_proj = nn.Linear(config.d_model, hidden, bias=False)
        self.up_proj = nn.Linear(config.d_model, hidden, bias=False)
        self.down_proj = nn.Linear(hidden, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate = F.silu(self.gate_proj(x))
        up = self.up_proj(x)
        return self.dropout(self.down_proj(gate * up))


# ---------------------------------------------------------------------------
# Transformer Block
# ---------------------------------------------------------------------------


class TransformerBlock(nn.Module if nn is not None else object):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.norm1 = nn.LayerNorm(config.d_model)
        self.attn = MultiHeadAttention(config)
        self.norm2 = nn.LayerNorm(config.d_model)
        self.ffn = FeedForward(config)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        # Pre-norm residual connections
        x = x + self.attn(self.norm1(x), mask)
        x = x + self.ffn(self.norm2(x))
        return x


# ---------------------------------------------------------------------------
# Full Tranc3 Model
# ---------------------------------------------------------------------------


class Tranc3Model(nn.Module if nn is not None else object):
    """
    The core Tranc3 language model.
    Decoder-only transformer with RoPE, SwiGLU, and pre-norm.

    Approximate parameter counts by config:
      d_model=256, n_layers=4  ->  ~10M params  (fast CPU training)
      d_model=512, n_layers=6  ->  ~50M params  (GPU recommended)
      d_model=768, n_layers=12 ->  ~150M params (serious GPU / Slough)
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        self.token_embed = nn.Embedding(config.vocab_size, config.d_model)
        self.embed_dropout = nn.Dropout(config.dropout)

        self.layers = nn.ModuleList([TransformerBlock(config) for _ in range(config.n_layers)])

        self.norm_out = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        # Weight tying: share embedding and output projection weights
        # Reduces parameter count and improves generalisation
        self.lm_head.weight = self.token_embed.weight

        self._init_weights()

    def _init_weights(self):
        """Scaled initialisation for stable training from scratch."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self,
        input_ids: torch.Tensor,
        targets: Optional[torch.Tensor] = None,
        mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        B, T = input_ids.shape
        # nosec B101 — assertion for type/class contract checking
        assert T <= self.config.max_seq_len, (
            f"Sequence length {T} exceeds model max {self.config.max_seq_len}"
        )

        x = self.embed_dropout(self.token_embed(input_ids))

        for layer in self.layers:
            x = layer(x, mask)

        x = self.norm_out(x)
        logits = self.lm_head(x)

        loss = None
        if targets is not None:
            # Flatten for cross-entropy: (B*T, vocab_size) vs (B*T,)
            loss = F.cross_entropy(
                logits.view(-1, self.config.vocab_size),
                targets.view(-1),
                ignore_index=-1,  # padding tokens ignored
            )

        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        input_ids: torch.Tensor,
        max_new_tokens: int = 256,
        temperature: float = 0.8,
        top_k: int = 50,
        top_p: float = 0.92,
        repetition_penalty: float = 1.15,
    ) -> torch.Tensor:
        """
        Autoregressive token generation with top-k/top-p sampling.
        Operates in eval mode — do not call during training.
        """
        self.eval()
        generated = input_ids.clone()

        for _ in range(max_new_tokens):
            # Crop context to max_seq_len
            context = generated[:, -self.config.max_seq_len :]
            logits, _ = self.forward(context)
            logits = logits[:, -1, :]  # last token only

            # Repetition penalty
            if repetition_penalty != 1.0:
                for token_id in set(generated[0].tolist()):
                    if logits[0, token_id] < 0:
                        logits[0, token_id] *= repetition_penalty
                    else:
                        logits[0, token_id] /= repetition_penalty

            # Temperature scaling
            logits = logits / max(temperature, 1e-8)

            # Top-k filtering
            if top_k > 0:
                topk_vals = torch.topk(logits, min(top_k, logits.size(-1))).values
                logits[logits < topk_vals[:, [-1]]] = float("-inf")

            # Top-p (nucleus) filtering
            if top_p < 1.0:
                sorted_logits, sorted_idx = torch.sort(logits, descending=True)
                cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                sorted_logits[cumulative_probs > top_p] = float("-inf")
                logits.scatter_(1, sorted_idx, sorted_logits)

            probs = F.softmax(logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            generated = torch.cat([generated, next_token], dim=1)

        return generated

    def parameter_count(self) -> str:
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        return f"Total: {total:,} | Trainable: {trainable:,}"
