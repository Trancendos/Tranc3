# src/deepmind/gemini_multimodal.py
# Multi-modal processing pipeline — text, vision, structured data fusion
# Gemini-inspired architecture for cross-modal reasoning

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


# ─── Multi-Modal Input ─────────────────────────────────────────────────────────


@dataclass
class ModalInput:
    modality: str  # "text", "image", "audio", "structured"
    data: Any  # raw data (str, bytes, np.ndarray, dict)
    encoding: Optional[str] = None  # "base64", "utf-8", etc.
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusedRepresentation:
    embedding: torch.Tensor  # fused cross-modal embedding
    modalities: List[str]  # which modalities contributed
    confidence: float  # fusion confidence
    attention_weights: Dict[str, float]  # per-modality attention weight
    latent_code: torch.Tensor  # compressed latent representation


# ─── Modality Encoders ─────────────────────────────────────────────────────────


class TextEncoder(nn.Module):
    """Transformer-based text encoder."""

    def __init__(
        self,
        vocab_size: int = 32000,
        d_model: int = 512,
        nhead: int = 8,
        num_layers: int = 4,
    ):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model, nhead, d_model * 4, dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.proj = nn.Linear(d_model, 256)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        x = self.embedding(tokens)
        x = self.transformer(x)
        x = self.pool(x.transpose(1, 2)).squeeze(-1)
        return self.proj(x)

    def encode_string(self, text: str) -> torch.Tensor:
        """Encode raw text string to embedding."""
        tokens = torch.tensor([[ord(c) % 32000 for c in text[:512]]], dtype=torch.long)
        with torch.no_grad():
            return self.forward(tokens)


class VisionEncoder(nn.Module):
    """Lightweight CNN vision encoder (ResNet-inspired)."""

    def __init__(self, out_dim: int = 256):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(64, 128, 3, stride=2, padding=1),
            nn.GELU(),
            nn.Conv2d(128, 256, 3, stride=2, padding=1),
            nn.GELU(),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(256, out_dim)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        x = self.features(images)
        x = self.pool(x).flatten(1)
        return self.proj(x)

    def encode_array(self, array: np.ndarray) -> torch.Tensor:
        """Encode (H, W, 3) numpy array to embedding."""
        if array.ndim == 2:
            array = np.stack([array] * 3, axis=-1)
        img = torch.from_numpy(array.transpose(2, 0, 1)).float().unsqueeze(0) / 255.0
        if img.shape[2] != 224 or img.shape[3] != 224:
            img = F.interpolate(
                img, size=(224, 224), mode="bilinear", align_corners=False
            )
        with torch.no_grad():
            return self.forward(img)


class StructuredEncoder(nn.Module):
    """Encodes structured data (dicts, tables) to dense embeddings."""

    def __init__(self, input_dim: int = 128, out_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Linear(256, 256),
            nn.GELU(),
            nn.Linear(256, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    def encode_dict(self, data: Dict) -> torch.Tensor:
        """Hash dict values into a fixed-size feature vector."""
        features = []
        for v in list(data.values())[:128]:
            if isinstance(v, (int, float)):
                features.append(float(v))
            elif isinstance(v, str):
                features.append(sum(ord(c) for c in v[:50]) / 50.0)
            else:
                features.append(0.0)
        features = features[:128]
        features += [0.0] * (128 - len(features))
        t = torch.tensor(features, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            return self.forward(t)


# ─── Cross-Modal Attention Fusion ──────────────────────────────────────────────


class CrossModalAttention(nn.Module):
    """
    Attend over multiple modality embeddings to produce a fused representation.
    Each modality is a "token" in the attention sequence.
    """

    def __init__(self, embed_dim: int = 256, num_heads: int = 4):
        super().__init__()
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm = nn.LayerNorm(embed_dim)
        self.proj = nn.Sequential(
            nn.Linear(embed_dim, embed_dim * 2),
            nn.GELU(),
            nn.Linear(embed_dim * 2, embed_dim),
        )

    def forward(self, embeddings: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        embeddings: (1, num_modalities, embed_dim)
        Returns: (fused, attn_weights)
        """
        query = embeddings.mean(dim=1, keepdim=True)  # (1, 1, D) — mean as query
        out, weights = self.attn(query, embeddings, embeddings)
        out = self.norm(out.squeeze(1) + query.squeeze(1))
        out = self.proj(out)
        return out, weights.squeeze(0)  # (D,), (1, num_modalities)


# ─── Gemini-Inspired Multi-Modal Model ────────────────────────────────────────


class GeminiMultiModalModel(nn.Module):
    """
    Gemini-inspired multi-modal model.
    Encodes text, images, and structured data; fuses via cross-modal attention;
    produces a unified representation for downstream tasks.
    """

    EMBED_DIM = 256

    def __init__(self):
        super().__init__()
        self.text_encoder = TextEncoder(d_model=512)
        self.vision_encoder = VisionEncoder(out_dim=self.EMBED_DIM)
        self.structured_encoder = StructuredEncoder(out_dim=self.EMBED_DIM)
        self.cross_attn = CrossModalAttention(self.EMBED_DIM)
        self.latent = nn.Sequential(
            nn.Linear(self.EMBED_DIM, 128), nn.GELU(), nn.Linear(128, 64)
        )

    def forward(self, modal_embeddings: Dict[str, torch.Tensor]) -> FusedRepresentation:
        if not modal_embeddings:
            dummy = torch.zeros(1, self.EMBED_DIM)
            return FusedRepresentation(
                embedding=dummy,
                modalities=[],
                confidence=0.0,
                attention_weights={},
                latent_code=self.latent(dummy),
            )

        modalities = list(modal_embeddings.keys())
        stack = torch.stack(
            [modal_embeddings[m] for m in modalities], dim=1
        )  # (1, M, D)

        fused, attn_w = self.cross_attn(stack)  # (D,), (1, M)
        latent = self.latent(fused)

        # Normalize attention weights for interpretability
        weights_np = attn_w[0].detach().numpy()
        attn_dict = {m: float(w) for m, w in zip(modalities, weights_np, strict=False)}

        confidence = float(torch.max(attn_w).item())

        return FusedRepresentation(
            embedding=fused,
            modalities=modalities,
            confidence=confidence,
            attention_weights=attn_dict,
            latent_code=latent,
        )


# ─── Multi-Modal Pipeline ─────────────────────────────────────────────────────


class MultiModalPipeline:
    """
    High-level pipeline: accept ModalInput objects → encode → fuse → output.
    """

    def __init__(self):
        self.model = GeminiMultiModalModel()
        self.model.eval()
        logger.info("MultiModalPipeline initialized (text + vision + structured)")

    async def process(self, inputs: List[ModalInput]) -> FusedRepresentation:
        """Async wrapper around the synchronous encode+fuse pipeline."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._process_sync, inputs)

    def _process_sync(self, inputs: List[ModalInput]) -> FusedRepresentation:
        modal_embeddings: Dict[str, torch.Tensor] = {}

        for inp in inputs:
            try:
                emb = self._encode_modality(inp)
                if emb is not None:
                    modal_embeddings[inp.modality] = emb
            except Exception as e:
                logger.warning("Failed to encode modality '%s': %s", inp.modality, e)

        with torch.no_grad():
            return self.model(modal_embeddings)

    def _encode_modality(self, inp: ModalInput) -> Optional[torch.Tensor]:
        if inp.modality == "text":
            text = inp.data if isinstance(inp.data, str) else str(inp.data)
            return self.model.text_encoder.encode_string(text)

        elif inp.modality == "image":
            if isinstance(inp.data, np.ndarray):
                return self.model.vision_encoder.encode_array(inp.data)
            elif isinstance(inp.data, str) and inp.encoding == "base64":
                img_bytes = base64.b64decode(inp.data)
                arr = np.frombuffer(img_bytes, dtype=np.uint8).reshape(64, 64, 3)
                return self.model.vision_encoder.encode_array(arr)
            else:
                arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
                return self.model.vision_encoder.encode_array(arr)

        elif inp.modality == "structured":
            data = inp.data if isinstance(inp.data, dict) else {"value": inp.data}
            return self.model.structured_encoder.encode_dict(data)

        logger.warning("Unknown modality: %s", inp.modality)
        return None

    async def cross_modal_similarity(
        self, input_a: ModalInput, input_b: ModalInput
    ) -> float:
        """Compute cosine similarity between two different modal inputs."""
        rep_a = await self.process([input_a])
        rep_b = await self.process([input_b])
        a = F.normalize(rep_a.embedding, dim=-1)
        b = F.normalize(rep_b.embedding, dim=-1)
        return float(torch.dot(a.squeeze(), b.squeeze()).item())


# Singleton
multimodal_pipeline = MultiModalPipeline()
