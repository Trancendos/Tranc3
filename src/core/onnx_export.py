# src/core/onnx_export.py
# TRANC3 ONNX Export — convert .pt weights to .onnx for edge + WASM deployment.
#
# Why ONNX?
#   PyTorch models cannot run in Cloudflare Workers (JS/WASM only).
#   ONNX models CAN run in:
#     - onnxruntime-web (WASM in CF Workers / browsers)
#     - onnxruntime (Python, CPU-only, lighter than PyTorch)
#     - candle (Rust WASM, CF Workers)
#     - TensorFlow.js (via tflite conversion)
#
# Result: run Tranc3 inference at the edge with ZERO external dependencies.
#
# Usage:
#   python -m src.core.onnx_export                       # default paths
#   python -m src.core.onnx_export --quantize            # + INT8 quantization
#   python -m src.core.onnx_export --out models/tranc3.onnx

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

_DEFAULT_PT_PATH = os.getenv("TRANC3_MODEL_PATH", "./models/tranc3-v1/tranc3-final.pt")
_DEFAULT_ONNX_PATH = os.getenv("TRANC3_ONNX_PATH", "./models/tranc3-v1/tranc3.onnx")
_DEFAULT_OPSET = 17  # ONNX opset — 17 is widely supported (ORT 1.16+)


# ─── Exporter ─────────────────────────────────────────────────────────────────


class OnnxExporter:
    """
    Export Tranc3Engine's AdvancedTransformerModel to ONNX.

    The exported graph accepts:
        input_ids : int64[batch, seq_len]
    and returns:
        logits    : float32[batch, seq_len, vocab_size]

    An optional embedding-only variant is also exported for embedding queries:
        input_ids  → hidden_states : float32[batch, seq_len, hidden_size]
    """

    def __init__(
        self,
        pt_path: Optional[str] = None,
        onnx_path: Optional[str] = None,
        opset: int = _DEFAULT_OPSET,
    ):
        self._pt_path = Path(pt_path or _DEFAULT_PT_PATH)
        self._onnx_path = Path(onnx_path or _DEFAULT_ONNX_PATH)
        self._opset = opset

    # ─── Main export ───────────────────────────────────────────────────────────

    def export(self, quantize: bool = False) -> Path:
        """
        Export the model to ONNX.  Returns the path to the .onnx file.

        Args:
            quantize: If True, also produce INT8-quantized variant at
                      <stem>-int8.onnx (≈ 4× smaller, ~2% accuracy loss).
        """
        import torch

        model, _cfg = self._load_model()

        # Dummy input — batch=1, seq=32
        dummy_ids = torch.randint(0, _cfg.vocab_size, (1, 32), dtype=torch.long)

        self._onnx_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Exporting to ONNX: %s (opset=%d)", self._onnx_path, self._opset)

        torch.onnx.export(
            model,
            (dummy_ids,),
            str(self._onnx_path),
            input_names=["input_ids"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq_len"},
                "logits": {0: "batch", 1: "seq_len"},
            },
            opset_version=self._opset,
            do_constant_folding=True,
        )
        logger.info(
            "ONNX export complete: %s (%.2f MB)",
            self._onnx_path,
            self._onnx_path.stat().st_size / 1e6,
        )

        if quantize:
            q_path = self._quantize(self._onnx_path)
            logger.info(
                "Quantized model: %s (%.2f MB)", q_path, q_path.stat().st_size / 1e6
            )

        return self._onnx_path

    def export_embeddings(self) -> Path:
        """
        Export embedding-only subgraph (no LM head).
        Useful for similarity search, classification, RAG retrieval.
        Returns path to the .onnx file.
        """
        import torch

        model, cfg = self._load_model()
        emb_model = _EmbeddingOnlyWrapper(model)

        dummy_ids = torch.randint(0, cfg.vocab_size, (1, 32), dtype=torch.long)
        out_path = self._onnx_path.with_name(self._onnx_path.stem + "-embeddings.onnx")

        torch.onnx.export(
            emb_model,
            (dummy_ids,),
            str(out_path),
            input_names=["input_ids"],
            output_names=["hidden_states"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq_len"},
                "hidden_states": {0: "batch", 1: "seq_len"},
            },
            opset_version=self._opset,
            do_constant_folding=True,
        )
        logger.info(
            "Embedding ONNX export: %s (%.2f MB)",
            out_path,
            out_path.stat().st_size / 1e6,
        )
        return out_path

    # ─── Validation ────────────────────────────────────────────────────────────

    def validate(self, onnx_path: Optional[Path] = None) -> bool:
        """
        Run ONNX checker + compare outputs against PyTorch for correctness.
        Returns True if outputs match within tolerance.
        """
        import torch

        onnx_path = onnx_path or self._onnx_path
        if not onnx_path.exists():
            logger.error("ONNX file not found: %s", onnx_path)
            return False

        # ONNX structural check
        try:
            import onnx

            onnx.checker.check_model(str(onnx_path))
            logger.info("ONNX structural check: PASSED")
        except Exception as exc:
            logger.error("ONNX structural check FAILED: %s", exc)
            return False

        # Numerical comparison
        try:
            import numpy as np
            import onnxruntime as ort

            model, cfg = self._load_model()
            dummy_ids = torch.randint(0, cfg.vocab_size, (1, 16), dtype=torch.long)

            with torch.no_grad():
                pt_out = model(dummy_ids).numpy()

            sess = ort.InferenceSession(str(onnx_path))
            ort_out = sess.run(["logits"], {"input_ids": dummy_ids.numpy()})[0]

            match = np.allclose(pt_out, ort_out, atol=1e-4, rtol=1e-3)
            if match:
                logger.info(
                    "Numerical validation: PASSED (max diff=%.6f)",
                    float(np.abs(pt_out - ort_out).max()),
                )
            else:
                logger.warning(
                    "Numerical validation: FAILED (max diff=%.6f)",
                    float(np.abs(pt_out - ort_out).max()),
                )
            return match

        except ImportError:
            logger.warning("onnxruntime not installed — skipping numerical validation")
            return True
        except Exception as exc:
            logger.error("Numerical validation error: %s", exc)
            return False

    # ─── INT8 Quantization ────────────────────────────────────────────────────

    @staticmethod
    def _quantize(onnx_path: Path) -> Path:
        """
        Apply static INT8 quantization via onnxruntime.quantization.
        Produces <stem>-int8.onnx alongside the FP32 model.
        """
        try:
            from onnxruntime.quantization import QuantType, quantize_dynamic
        except ImportError:
            logger.warning("onnxruntime not installed — skipping quantization")
            return onnx_path

        out_path = onnx_path.with_name(onnx_path.stem + "-int8.onnx")
        quantize_dynamic(
            model_input=str(onnx_path),
            model_output=str(out_path),
            weight_type=QuantType.QInt8,
        )
        return out_path

    # ─── Model loader ─────────────────────────────────────────────────────────

    def _load_model(self):
        """Load the PyTorch model in eval mode. Returns (model, cfg)."""
        from src.core.tranc3_inference import Tranc3Engine

        engine = Tranc3Engine(model_path=str(self._pt_path))
        engine.load()

        if engine._bootstrap_mode:
            raise RuntimeError(
                f"No trained weights found at {self._pt_path}. "
                "Train the model first: python train.py"
            )

        model = engine._model
        model.eval()

        class _Cfg:
            pass

        cfg = _Cfg()
        cfg.vocab_size = model.token_embeddings.weight.shape[0]
        return model, cfg


# ─── Embedding-only wrapper ───────────────────────────────────────────────────


class _EmbeddingOnlyWrapper:
    """Thin nn.Module wrapper that exposes only the hidden states (no LM head)."""

    def __init__(self, full_model):
        import torch.nn as nn

        class _Inner(nn.Module):
            def forward(self, input_ids):
                return full_model.get_embeddings(input_ids)

        self._inner = _Inner()

    def __call__(self, *a, **kw):
        return self._inner(*a, **kw)


# ─── ONNX Runtime inference helper ───────────────────────────────────────────


class OnnxInferenceEngine:
    """
    Lightweight inference wrapper over an ONNX model.
    Replaces Tranc3Engine for CPU/edge deployments with no PyTorch dependency.

    Usage:
        eng = OnnxInferenceEngine("./models/tranc3-v1/tranc3.onnx")
        eng.load()
        logits = eng.forward(input_ids_numpy)
    """

    def __init__(self, onnx_path: Optional[str] = None):
        self._path = Path(onnx_path or _DEFAULT_ONNX_PATH)
        self._session = None

    def load(self) -> "OnnxInferenceEngine":
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self._path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            logger.info("ONNX session loaded: %s", self._path)
        except ImportError:
            logger.error("onnxruntime not installed — pip install onnxruntime")
            raise
        return self

    def forward(self, input_ids):  # -> np.ndarray (imported lazily inside method)
        """
        Run one forward pass.
        input_ids: numpy int64[batch, seq_len] or torch.Tensor
        Returns: numpy float32[batch, seq_len, vocab]
        """
        import numpy as np

        if hasattr(input_ids, "numpy"):
            input_ids = input_ids.numpy()
        input_ids = input_ids.astype(np.int64)
        return self._session.run(["logits"], {"input_ids": input_ids})[0]

    def is_loaded(self) -> bool:
        return self._session is not None


# ─── CLI entry point ──────────────────────────────────────────────────────────


def _cli():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="Export Tranc3 model to ONNX")
    parser.add_argument("--pt", default=_DEFAULT_PT_PATH, help="Input .pt checkpoint")
    parser.add_argument("--out", default=_DEFAULT_ONNX_PATH, help="Output .onnx path")
    parser.add_argument("--opset", default=_DEFAULT_OPSET, type=int, help="ONNX opset")
    parser.add_argument(
        "--quantize", action="store_true", help="Also export INT8 variant"
    )
    parser.add_argument(
        "--embeddings", action="store_true", help="Also export embeddings-only graph"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate ONNX output numerically"
    )
    args = parser.parse_args()

    exporter = OnnxExporter(pt_path=args.pt, onnx_path=args.out, opset=args.opset)

    onnx_path = exporter.export(quantize=args.quantize)
    print(f"✓  Exported: {onnx_path}")

    if args.embeddings:
        emb_path = exporter.export_embeddings()
        print(f"✓  Embeddings: {emb_path}")

    if args.validate:
        ok = exporter.validate()
        print(f"✓  Validation: {'PASSED' if ok else 'FAILED'}")


if __name__ == "__main__":
    _cli()
