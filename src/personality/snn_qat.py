"""
TR3-009: Spiking Neural Network with Quantization-Aware Training (SNN QAT).

Implements a two-layer SNN inference path using snnTorch Leaky neurons with
Brevitas INT8 weight quantization.  Designed for on-device / edge inference
where 8-bit fixed-point arithmetic is required.

Architecture
------------
  Layer 1: QuantLinear(input_dim → hidden_dim, INT8 weights, INT8 activations)
            + Leaky (β=0.9, threshold=1.0) spiking neuron
  Layer 2: QuantLinear(hidden_dim → output_dim, INT8 weights, INT8 activations)
            + Leaky output neuron

  Inputs are presented as a time-series of T=8 steps (temporal unrolling).
  Spike rates over the window are averaged to produce a float output vector.

Use case: Fast personality-signal classification at edge latency budgets.
  input : 4-dim feature vector (same encoding as PersonalityLNN)
  output: 3-dim signal [arousal, valence, engagement] in [0, 1]

Fallback (no snntorch / brevitas / torch)
-----------------------------------------
Simple ReLU MLP with floating-point arithmetic provides the same interface.

Quantization export
-------------------
`SNNModel.export_onnx(path)` serialises the quantized model to ONNX (INT8).
Falls back to a no-op stub when brevitas/torch are unavailable.
"""

from __future__ import annotations

import logging
import math
from typing import List, Sequence

logger = logging.getLogger(__name__)

# ── optional torch / snntorch / brevitas ──────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import snntorch as snn  # type: ignore[import]
    from snntorch import functional as SF  # type: ignore[import]  # noqa: F401
    import brevitas.nn as qnn  # type: ignore[import]
    from brevitas.quant import Int8WeightPerTensorFloat  # type: ignore[import]
    from brevitas.quant import Int8ActPerTensorFloat  # type: ignore[import]
    _USING_SNN = True
    logger.debug("personality.snn_qat: snntorch+brevitas available — using SNN QAT")
except ImportError:
    _USING_SNN = False
    logger.debug("personality.snn_qat: snntorch/brevitas unavailable — using float MLP")

# ── constants ─────────────────────────────────────────────────────────────────

INPUT_DIM = 4
HIDDEN_DIM = 32
OUTPUT_DIM = 3
T_STEPS = 8        # temporal unrolling window
BETA = 0.9         # Leaky membrane decay constant
THRESHOLD = 1.0    # spike threshold


# ── SNN QAT model (snntorch + brevitas path) ──────────────────────────────────

def _build_snn_model() -> "nn.Module":
    """Build a two-layer quantized SNN (returns nn.Module)."""

    class _SNNQAT(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.fc1 = qnn.QuantLinear(
                INPUT_DIM, HIDDEN_DIM,
                bias=True,
                weight_quant=Int8WeightPerTensorFloat,
                input_quant=Int8ActPerTensorFloat,
                output_quant=Int8ActPerTensorFloat,
            )
            self.lif1 = snn.Leaky(beta=BETA, threshold=THRESHOLD, learn_beta=False)
            self.fc2 = qnn.QuantLinear(
                HIDDEN_DIM, OUTPUT_DIM,
                bias=True,
                weight_quant=Int8WeightPerTensorFloat,
                input_quant=Int8ActPerTensorFloat,
                output_quant=Int8ActPerTensorFloat,
            )
            self.lif2 = snn.Leaky(beta=BETA, threshold=THRESHOLD, learn_beta=False)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            """
            x: (batch, T, input_dim)
            returns: (batch, output_dim) — spike-rate average over T steps
            """
            batch = x.shape[0]
            mem1 = self.lif1.init_leaky()
            mem2 = self.lif2.init_leaky()
            spike_acc = torch.zeros(batch, OUTPUT_DIM)

            for t in range(T_STEPS):
                xt = x[:, t, :]            # (batch, input_dim)
                cur1 = self.fc1(xt)
                spk1, mem1 = self.lif1(cur1, mem1)
                cur2 = self.fc2(spk1)
                spk2, mem2 = self.lif2(cur2, mem2)
                spike_acc = spike_acc + spk2

            return spike_acc / T_STEPS   # spike rate in [0, ~1]

    return _SNNQAT()


# ── Float MLP fallback ────────────────────────────────────────────────────────

class _FloatMLP:
    """Simple ReLU MLP fallback — no torch, no quantization."""

    def __init__(self) -> None:
        import random
        rng = random.Random(42)  # fixed seed for determinism

        def _rand_weights(rows: int, cols: int) -> List[List[float]]:
            scale = math.sqrt(2.0 / cols)
            return [[rng.gauss(0, scale) for _ in range(cols)] for _ in range(rows)]

        self._w1 = _rand_weights(HIDDEN_DIM, INPUT_DIM)
        self._b1 = [0.0] * HIDDEN_DIM
        self._w2 = _rand_weights(OUTPUT_DIM, HIDDEN_DIM)
        self._b2 = [0.0] * OUTPUT_DIM

    def _relu(self, x: float) -> float:
        return max(0.0, x)

    def _sigmoid(self, x: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-x))
        except OverflowError:
            return 0.0 if x < 0 else 1.0

    def forward(self, x: Sequence[float]) -> List[float]:
        h = [
            self._relu(sum(self._w1[j][i] * x[i] for i in range(INPUT_DIM)) + self._b1[j])
            for j in range(HIDDEN_DIM)
        ]
        return [
            self._sigmoid(sum(self._w2[k][j] * h[j] for j in range(HIDDEN_DIM)) + self._b2[k])
            for k in range(OUTPUT_DIM)
        ]


# ── public API ────────────────────────────────────────────────────────────────

class SNNModel:
    """
    INT8-quantized SNN classifier for personality signal extraction.

    Accepts a 4-dim feature vector and returns [arousal, valence, engagement]
    all in [0, 1].

    Usage::

        snn_model = SNNModel()
        features = [0.5, 0.8, 0.2, 0.4]   # [sentiment, domain, depth, length]
        arousal, valence, engagement = snn_model.infer(features)

    Attributes:
        backend: "snn_qat" | "float_mlp"
    """

    def __init__(self, *, force_fallback: bool = False) -> None:
        self._using_snn = _USING_SNN and not force_fallback
        if self._using_snn:
            self._model = _build_snn_model()
            self._model.eval()  # type: ignore[attr-defined]
        else:
            self._mlp = _FloatMLP()

    @property
    def backend(self) -> str:
        return "snn_qat" if self._using_snn else "float_mlp"

    def infer(self, features: Sequence[float]) -> tuple[float, float, float]:
        """
        Run inference on a single 4-dim feature vector.

        Returns (arousal, valence, engagement) each in [0, 1].
        """
        if len(features) != INPUT_DIM:
            raise ValueError(f"Expected {INPUT_DIM} features, got {len(features)}")

        if self._using_snn:
            x = torch.tensor([[list(features)] * T_STEPS], dtype=torch.float32)
            with torch.no_grad():
                out = self._model(x)[0].tolist()
        else:
            out = self._mlp.forward(list(features))

        # Clamp to [0, 1]
        arousal, valence, engagement = (max(0.0, min(1.0, v)) for v in out[:3])
        return arousal, valence, engagement

    def export_onnx(self, path: str) -> bool:
        """
        Export model to ONNX (INT8 via Brevitas).

        Returns True on success, False if torch/brevitas unavailable.
        """
        if not self._using_snn:
            logger.warning("snn_qat: ONNX export skipped — SNN backend not available")
            return False

        try:
            import torch
            dummy = torch.zeros(1, T_STEPS, INPUT_DIM)
            torch.onnx.export(
                self._model,
                dummy,
                path,
                opset_version=13,
                input_names=["features"],
                output_names=["signals"],
                dynamic_axes={"features": {0: "batch"}},
            )
            logger.info("snn_qat: ONNX exported to %s", path)
            return True
        except Exception as exc:
            logger.error("snn_qat: ONNX export failed: %s", exc)
            return False
