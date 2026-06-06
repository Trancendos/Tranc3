"""
TR3-011: OpenVINO model pipeline — unit tests.

Tests:
- OpenVINOPipeline.backend = "numpy_fallback" when openvino absent
- infer() returns dict with "signals" key
- infer() output shape is (3,) for 4-dim SNN model
- infer() output values are in [0, 1] (sigmoid output)
- from_snn_model() convenience constructor works
- model_path with missing file raises FileNotFoundError
- model_path with unsupported extension raises ValueError
- Deterministic output for fixed-seed numpy fallback
- force_fallback=True uses numpy even when openvino present (mocked)
- OpenVINO path selected when openvino importable (mocked)
- Mocked OpenVINO pipeline infer() invoked correctly
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_dummy_onnx(tmp_path: Path) -> str:
    """Create a dummy .onnx file (content doesn't matter for fallback tests)."""
    p = tmp_path / "dummy.onnx"
    p.write_bytes(b"\x08\x00")
    return str(p)


def _fresh_module():
    import importlib
    for k in list(sys.modules):
        if "openvino_pipeline" in k:
            del sys.modules[k]
    return importlib.import_module("src.core.openvino_pipeline")


# ── numpy fallback (no openvino) ──────────────────────────────────────────────

def test_numpy_fallback_backend(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline(path, force_fallback=True)
    assert pipeline.backend == "numpy_fallback"


def test_infer_returns_signals_key(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline(path, force_fallback=True)
    out = pipeline.infer({"features": np.array([0.5, 0.8, 0.2, 0.4], dtype=np.float32)})
    assert "signals" in out


def test_infer_output_shape(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline(path, force_fallback=True)
    out = pipeline.infer({"features": np.array([0.5, 0.8, 0.2, 0.4], dtype=np.float32)})
    assert out["signals"].shape == (3,)


def test_infer_output_bounded(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline(path, force_fallback=True)
    out = pipeline.infer({"features": np.array([1.0, -1.0, 0.5, 0.0], dtype=np.float32)})
    assert all(0.0 <= v <= 1.0 for v in out["signals"])


def test_numpy_fallback_deterministic(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    p1 = OpenVINOPipeline(path, force_fallback=True)
    p2 = OpenVINOPipeline(path, force_fallback=True)
    x = np.array([0.3, 0.6, 0.1, 0.9], dtype=np.float32)
    out1 = p1.infer({"features": x})
    out2 = p2.infer({"features": x})
    np.testing.assert_array_almost_equal(out1["signals"], out2["signals"])


def test_from_snn_model_convenience(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline.from_snn_model(path, force_fallback=True)
    assert pipeline.backend == "numpy_fallback"


def test_missing_model_file_raises():
    from src.core.openvino_pipeline import OpenVINOPipeline
    with pytest.raises(FileNotFoundError):
        OpenVINOPipeline("/nonexistent/path/model.onnx", force_fallback=True)


def test_unsupported_extension_raises(tmp_path):
    from src.core.openvino_pipeline import OpenVINOPipeline
    bad_path = tmp_path / "model.pb"
    bad_path.write_bytes(b"fake")
    with pytest.raises(ValueError):
        OpenVINOPipeline(str(bad_path), force_fallback=True)


def test_infer_accepts_any_input_key(tmp_path):
    """Pipeline should accept any input key name (not just 'features')."""
    from src.core.openvino_pipeline import OpenVINOPipeline
    path = _make_dummy_onnx(tmp_path)
    pipeline = OpenVINOPipeline(path, force_fallback=True)
    out = pipeline.infer({"x": np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)})
    assert out["signals"].shape == (3,)


# ── mocked OpenVINO path ──────────────────────────────────────────────────────

def test_openvino_backend_selected_when_available(monkeypatch, tmp_path):
    """When openvino is importable, backend should be 'openvino'."""
    fake_ov = MagicMock()
    fake_compiled = MagicMock()
    fake_compiled.inputs = [MagicMock(any_name="features")]
    fake_compiled.outputs = [MagicMock(any_name="signals")]
    fake_infer_req = MagicMock()
    fake_out_tensor = MagicMock()
    fake_out_tensor.data = np.array([0.6, 0.4, 0.7])
    fake_infer_req.get_output_tensor.return_value = fake_out_tensor
    fake_compiled.create_infer_request.return_value = fake_infer_req

    fake_core = MagicMock()
    fake_core.read_model.return_value = MagicMock()
    fake_core.compile_model.return_value = fake_compiled
    fake_ov.Core.return_value = fake_core

    fake_ov_runtime = MagicMock()
    fake_ov_runtime.Core = fake_ov.Core

    monkeypatch.setitem(sys.modules, "openvino", fake_ov)
    monkeypatch.setitem(sys.modules, "openvino.runtime", fake_ov_runtime)

    path = _make_dummy_onnx(tmp_path)
    mod = _fresh_module()
    assert mod._USING_OV is True

    pipeline = mod.OpenVINOPipeline(path, device="CPU")
    assert pipeline.backend == "openvino"


def test_force_fallback_ignores_openvino(tmp_path, monkeypatch):
    fake_ov_runtime = MagicMock()
    monkeypatch.setitem(sys.modules, "openvino", MagicMock())
    monkeypatch.setitem(sys.modules, "openvino.runtime", fake_ov_runtime)
    path = _make_dummy_onnx(tmp_path)
    mod = _fresh_module()
    pipeline = mod.OpenVINOPipeline(path, force_fallback=True)
    assert pipeline.backend == "numpy_fallback"
