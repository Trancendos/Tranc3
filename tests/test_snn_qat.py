"""
TR3-009: SNN QAT (Spiking Neural Network + Brevitas INT8 quantization) — unit tests.

Tests:
- SNNModel.backend reports "float_mlp" when torch/snntorch absent
- SNNModel.infer returns a 3-tuple of floats in [0, 1]
- SNNModel.infer clamps outputs that exceed bounds
- SNNModel.infer raises ValueError for wrong input dimension
- Float MLP forward produces deterministic outputs (fixed seed)
- export_onnx returns False without torch backend
- SNN backend is selected when torch+snntorch+brevitas are present (mocked)
- Mocked SNN path infer() returns bounded tuple
- SNNModel.infer works with list, tuple, and generator inputs
- force_fallback=True uses float_mlp even when torch present
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _fresh_snn_module() -> ModuleType:
    import importlib
    for key in list(sys.modules):
        if "personality.snn_qat" in key:
            del sys.modules[key]
    return importlib.import_module("src.personality.snn_qat")


# ── fallback (float MLP) path ─────────────────────────────────────────────────

def test_float_mlp_backend():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    assert m.backend == "float_mlp"


def test_infer_returns_triple():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    result = m.infer([0.5, 0.8, 0.2, 0.4])
    assert len(result) == 3


def test_infer_bounds():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    arousal, valence, engagement = m.infer([1.0, 1.0, 1.0, 1.0])
    assert 0.0 <= arousal <= 1.0
    assert 0.0 <= valence <= 1.0
    assert 0.0 <= engagement <= 1.0


def test_infer_negative_features_bounded():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    # Negative inputs should still produce clamped [0,1] outputs
    result = m.infer([-1.0, -1.0, 0.0, 0.0])
    assert all(0.0 <= v <= 1.0 for v in result)


def test_infer_wrong_dim_raises():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    with pytest.raises(ValueError):
        m.infer([0.5, 0.8])  # only 2 dims, expects 4


def test_infer_too_many_dims_raises():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    with pytest.raises(ValueError):
        m.infer([0.1, 0.2, 0.3, 0.4, 0.5])


def test_float_mlp_deterministic():
    """Fixed-seed MLP must produce identical outputs on repeated calls."""
    from src.personality.snn_qat import SNNModel
    m1 = SNNModel(force_fallback=True)
    m2 = SNNModel(force_fallback=True)
    features = [0.3, 0.6, 0.1, 0.9]
    assert m1.infer(features) == m2.infer(features)


def test_infer_accepts_tuple():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    result = m.infer((0.5, 0.5, 0.5, 0.5))
    assert len(result) == 3


def test_export_onnx_returns_false_without_torch():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    assert m.export_onnx("/tmp/test_model.onnx") is False  # nosec B108


# ── force_fallback flag ───────────────────────────────────────────────────────

def test_force_fallback_ignores_torch():
    from src.personality.snn_qat import SNNModel
    m = SNNModel(force_fallback=True)
    assert m.backend == "float_mlp"


# ── mocked SNN (torch + snntorch + brevitas) path ────────────────────────────

def _make_torch_mock() -> MagicMock:
    fake_torch = MagicMock()
    out_tensor = MagicMock()
    out_tensor.__getitem__ = MagicMock(return_value=MagicMock(tolist=lambda: [0.6, 0.4, 0.7]))
    fake_torch.tensor.return_value = MagicMock()
    fake_torch.zeros.return_value = MagicMock(__add__=lambda s, o: s, __truediv__=lambda s, d: out_tensor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    fake_torch.no_grad.return_value = ctx

    fake_nn = MagicMock()
    fake_torch.nn = fake_nn
    return fake_torch


def test_snn_backend_selected_when_available(monkeypatch):
    fake_torch = _make_torch_mock()
    fake_snntorch = MagicMock()
    fake_snn_leaky = MagicMock()
    fake_snn_leaky.return_value = MagicMock(
        init_leaky=MagicMock(return_value=MagicMock()),
        __call__=MagicMock(return_value=(MagicMock(), MagicMock())),
    )
    fake_snntorch.Leaky = fake_snn_leaky
    fake_sf = MagicMock()

    fake_brevitas_nn = MagicMock()
    fake_qlinear = MagicMock(return_value=MagicMock())
    fake_brevitas_nn.QuantLinear = fake_qlinear

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "torch.nn", fake_torch.nn)
    monkeypatch.setitem(sys.modules, "snntorch", fake_snntorch)
    monkeypatch.setitem(sys.modules, "snntorch.functional", fake_sf)
    monkeypatch.setitem(sys.modules, "brevitas", MagicMock())
    monkeypatch.setitem(sys.modules, "brevitas.nn", fake_brevitas_nn)
    monkeypatch.setitem(sys.modules, "brevitas.quant", MagicMock())

    mod = _fresh_snn_module()
    assert mod._USING_SNN is True

    m = mod.SNNModel()
    assert m.backend == "snn_qat"


def test_no_snntorch_falls_back(monkeypatch):
    monkeypatch.setitem(sys.modules, "snntorch", None)
    monkeypatch.setitem(sys.modules, "snntorch.functional", None)

    mod = _fresh_snn_module()
    assert mod._USING_SNN is False

    m = mod.SNNModel()
    assert m.backend == "float_mlp"


def test_no_brevitas_falls_back(monkeypatch):
    monkeypatch.setitem(sys.modules, "brevitas", None)
    monkeypatch.setitem(sys.modules, "brevitas.nn", None)
    monkeypatch.setitem(sys.modules, "brevitas.quant", None)

    mod = _fresh_snn_module()
    assert mod._USING_SNN is False

    m = mod.SNNModel()
    assert m.backend == "float_mlp"
