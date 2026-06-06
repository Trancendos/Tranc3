"""
TR3-011: OpenVINO model pipeline.

Provides an OpenVINO-backed inference pipeline for compiled INT8 SNN models.
Loads an ONNX or IR (.xml/.bin) model, compiles it for the target device
(CPU / GPU / NPU), and runs synchronous inference.

Architecture
------------
  1. ModelLoader: loads from ONNX path or OpenVINO IR (.xml)
  2. OpenVINOPipeline: compile → infer() → postprocess
  3. Graceful fallback: when openvino is not installed, a NumPy-based
     mock pipeline runs the same interface with float32 arithmetic.

Supported devices (passed to compile_model):
  "CPU"   — default, works everywhere
  "GPU"   — requires Intel GPU + OpenCL drivers
  "NPU"   — Intel Neural Processing Unit (Meteor Lake+)
  "AUTO"  — OpenVINO auto-device selection

Usage::

    pipeline = OpenVINOPipeline("model.onnx", device="CPU")
    output = pipeline.infer({"features": np.array([0.5, 0.8, 0.2, 0.4])})
    arousal, valence, engagement = output["signals"]
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# ── optional openvino ─────────────────────────────────────────────────────────

try:
    from openvino.runtime import Core  # type: ignore[import]
    _USING_OV = True
    logger.debug("openvino_pipeline: OpenVINO runtime available")
except ImportError:
    _USING_OV = False
    logger.debug("openvino_pipeline: OpenVINO not available — using numpy fallback")

# ── constants ─────────────────────────────────────────────────────────────────

DEFAULT_DEVICE = "CPU"
_SUPPORTED_EXTENSIONS = {".onnx", ".xml"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _validate_model_path(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    if p.suffix not in _SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported model format '{p.suffix}'. Use .onnx or .xml")
    return p


# ── OpenVINO pipeline ─────────────────────────────────────────────────────────

class _OVPipeline:
    """OpenVINO-backed inference pipeline."""

    def __init__(self, model_path: str, device: str = DEFAULT_DEVICE) -> None:
        p = _validate_model_path(model_path)
        ie = Core()
        model = ie.read_model(str(p))
        self._compiled = ie.compile_model(model, device)
        self._infer_request = self._compiled.create_infer_request()
        self._input_names = [t.any_name for t in self._compiled.inputs]
        self._output_names = [t.any_name for t in self._compiled.outputs]
        logger.info("openvino_pipeline: compiled %s on %s", p.name, device)

    def infer(self, inputs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        self._infer_request.infer(inputs)
        return {name: self._infer_request.get_output_tensor(i).data
                for i, name in enumerate(self._output_names)}


# ── NumPy fallback pipeline ───────────────────────────────────────────────────

class _NumpyFallbackPipeline:
    """
    Numpy-based mock pipeline for environments without OpenVINO.

    Implements a simple sigmoid MLP that accepts the same dict-based
    input/output interface. Weights are fixed (seed 42) for determinism.
    """

    def __init__(self, model_path: str, device: str = DEFAULT_DEVICE) -> None:
        rng = np.random.RandomState(42)
        self._w1 = rng.randn(32, 4).astype(np.float32) * 0.1
        self._b1 = np.zeros(32, dtype=np.float32)
        self._w2 = rng.randn(3, 32).astype(np.float32) * 0.1
        self._b2 = np.zeros(3, dtype=np.float32)
        logger.debug("openvino_pipeline: numpy fallback initialised (model=%s)", model_path)

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))

    def infer(self, inputs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        # Accept any key for the first (and only) input
        x = next(iter(inputs.values())).flatten().astype(np.float32)
        h = np.maximum(0, self._w1 @ x + self._b1)   # ReLU
        out = self._sigmoid(self._w2 @ h + self._b2)
        return {"signals": out}


# ── public API ────────────────────────────────────────────────────────────────

class OpenVINOPipeline:
    """
    Unified inference pipeline backed by OpenVINO or NumPy fallback.

    Parameters
    ----------
    model_path : str
        Path to an ONNX (.onnx) or OpenVINO IR (.xml) model file.
    device     : str
        Target device: "CPU" (default), "GPU", "NPU", "AUTO".
    force_fallback : bool
        Force the NumPy fallback even when openvino is installed.

    Attributes
    ----------
    backend : str
        "openvino" | "numpy_fallback"

    Example
    -------
    >>> pipeline = OpenVINOPipeline("snn_model.onnx", device="CPU")
    >>> out = pipeline.infer({"features": np.array([0.5, 0.8, 0.2, 0.4], dtype=np.float32)})
    >>> arousal, valence, engagement = out["signals"]
    """

    def __init__(
        self,
        model_path: str,
        device: str = DEFAULT_DEVICE,
        *,
        force_fallback: bool = False,
    ) -> None:
        _validate_model_path(model_path)
        self._using_ov = _USING_OV and not force_fallback
        if self._using_ov:
            self._pipeline: "_OVPipeline | _NumpyFallbackPipeline" = _OVPipeline(model_path, device)
        else:
            self._pipeline = _NumpyFallbackPipeline(model_path, device)

    @property
    def backend(self) -> str:
        return "openvino" if self._using_ov else "numpy_fallback"

    def infer(self, inputs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Run inference.

        Parameters
        ----------
        inputs : dict[str, np.ndarray]
            Input tensors keyed by layer name.

        Returns
        -------
        dict[str, np.ndarray]
            Output tensors keyed by layer name.
        """
        return self._pipeline.infer(inputs)

    @classmethod
    def from_snn_model(
        cls,
        onnx_path: str,
        device: str = DEFAULT_DEVICE,
        *,
        force_fallback: bool = False,
    ) -> "OpenVINOPipeline":
        """Convenience constructor for SNN QAT ONNX exports."""
        return cls(onnx_path, device, force_fallback=force_fallback)
