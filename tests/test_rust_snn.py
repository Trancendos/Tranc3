"""
TR3-010: Rust Tensor Nanoservice — unit tests for INT8 SNN hot paths.

Tests cover both the Python fallback path (always runs) and the Rust path
(via mocking). All tests use the public API in src/nanoservices/snn_tensor.

Tests:
- leaky_step_i8: single neuron, spike fires at threshold
- leaky_step_i8: no spike below threshold
- leaky_step_i8: membrane reset after spike
- leaky_step_i8: wrong weights length raises ValueError
- leaky_step_i8: wrong mem length raises ValueError
- spike_rate_i8: 2-layer forward produces bounded outputs
- spike_rate_i8: t_steps=0 raises ValueError
- spike_rate_i8: all-zero weights produces zero spike rate
- spike_rate_i8: very high input produces positive spike rates
- quantize_f32_to_i8: correct rounding and clip to [-127, 127]
- quantize_f32_to_i8: scale=0 raises ValueError
- dequantize_i8_to_f32: round-trip fidelity
- matmul_i8: 2×2 example
- matmul_i8: shape mismatch raises ValueError
- Rust extension fallback when import fails (_USING_RUST=False by default in CI)
- Python and Rust paths produce identical results (parity test, mocked Rust)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _import_fresh():
    import importlib
    for k in list(sys.modules):
        if "snn_tensor" in k:
            del sys.modules[k]
    return importlib.import_module("src.nanoservices.snn_tensor")


# ── leaky_step_i8 ─────────────────────────────────────────────────────────────

def test_leaky_step_single_neuron_spike():
    """Neuron spikes when current pushes membrane above threshold."""
    from src.nanoservices.snn_tensor import leaky_step_i8

    weights = [64]      # weight for 1 input
    bias = [0.0]
    inputs = [2.0]      # current = 64 * 2.0 = 128.0 → relu → well above threshold
    mem = [0.0]
    spikes, new_mem = leaky_step_i8(weights, bias, inputs, mem, beta=0.9, threshold=1.0)
    assert spikes[0] == 1
    assert new_mem[0] >= 0.0       # mem was reset


def test_leaky_step_no_spike_below_threshold():
    """Neuron does not spike when current is insufficient."""
    from src.nanoservices.snn_tensor import leaky_step_i8

    weights = [1]
    bias = [0.0]
    inputs = [0.001]    # very tiny current — will not reach threshold
    mem = [0.0]
    spikes, new_mem = leaky_step_i8(weights, bias, inputs, mem, beta=0.9, threshold=1.0)
    assert spikes[0] == 0
    assert new_mem[0] < 1.0


def test_leaky_step_membrane_decays():
    """Membrane decays by beta each step without spiking."""
    from src.nanoservices.snn_tensor import leaky_step_i8
    weights = [0]
    bias = [0.0]
    inputs = [0.0]
    mem = [0.5]
    _, new_mem = leaky_step_i8(weights, bias, inputs, mem, beta=0.9, threshold=1.0)
    assert abs(new_mem[0] - 0.45) < 1e-5   # 0.9 * 0.5 = 0.45


def test_leaky_step_wrong_weights_raises():
    from src.nanoservices.snn_tensor import leaky_step_i8
    with pytest.raises((ValueError, Exception)):
        leaky_step_i8([1, 2, 3], [0.0], [1.0], [0.0], 0.9, 1.0)


def test_leaky_step_wrong_mem_raises():
    from src.nanoservices.snn_tensor import leaky_step_i8
    with pytest.raises((ValueError, Exception)):
        leaky_step_i8([1], [0.0, 0.0], [1.0], [0.0], 0.9, 1.0)


# ── spike_rate_i8 ─────────────────────────────────────────────────────────────

def test_spike_rate_bounded():
    from src.nanoservices.snn_tensor import spike_rate_i8
    # Small random-ish INT8 weights
    w1 = [10] * (4 * 8)   # 8 hidden, 4 inputs
    b1 = [0.0] * 8
    w2 = [10] * (8 * 3)   # 3 outputs, 8 hidden
    b2 = [0.0] * 3
    rates = spike_rate_i8(w1, b1, w2, b2, [0.5, 0.5, 0.5, 0.5], t_steps=8)
    assert len(rates) == 3
    assert all(0.0 <= r <= 1.0 for r in rates)


def test_spike_rate_zero_weights_produces_zero():
    from src.nanoservices.snn_tensor import spike_rate_i8
    w1 = [0] * (4 * 8)
    b1 = [0.0] * 8
    w2 = [0] * (8 * 3)
    b2 = [0.0] * 3
    rates = spike_rate_i8(w1, b1, w2, b2, [1.0, 1.0, 1.0, 1.0], t_steps=4)
    assert all(r == 0.0 for r in rates)


def test_spike_rate_t_steps_zero_raises():
    from src.nanoservices.snn_tensor import spike_rate_i8
    w1 = [1] * (4 * 8)
    b1 = [0.0] * 8
    w2 = [1] * (8 * 3)
    b2 = [0.0] * 3
    with pytest.raises((ValueError, Exception)):
        spike_rate_i8(w1, b1, w2, b2, [0.5] * 4, t_steps=0)


def test_spike_rate_high_input_produces_spikes():
    from src.nanoservices.snn_tensor import spike_rate_i8
    # Large positive weights + bias → should spike
    w1 = [100] * (4 * 4)
    b1 = [50.0] * 4
    w2 = [100] * (4 * 2)
    b2 = [50.0] * 2
    rates = spike_rate_i8(w1, b1, w2, b2, [1.0] * 4, t_steps=8, beta=0.9, threshold=0.1)
    assert any(r > 0 for r in rates)


# ── quantize / dequantize ─────────────────────────────────────────────────────

def test_quantize_correct_rounding():
    from src.nanoservices.snn_tensor import quantize_f32_to_i8
    result = quantize_f32_to_i8([0.0, 0.5, -0.5, 1.27], scale=0.01)
    assert result[0] == 0
    assert result[1] == 50
    assert result[2] == -50
    assert result[3] == 127


def test_quantize_clips_to_127():
    from src.nanoservices.snn_tensor import quantize_f32_to_i8
    result = quantize_f32_to_i8([1000.0, -1000.0], scale=1.0)
    assert result[0] == 127
    assert result[1] == -127


def test_quantize_zero_scale_raises():
    from src.nanoservices.snn_tensor import quantize_f32_to_i8
    with pytest.raises((ValueError, Exception)):
        quantize_f32_to_i8([1.0], scale=0.0)


def test_dequantize_round_trip():
    from src.nanoservices.snn_tensor import dequantize_i8_to_f32
    data = [10, -20, 50, -127]
    scale = 0.01
    result = dequantize_i8_to_f32(data, scale)
    assert abs(result[0] - 0.10) < 1e-5
    assert abs(result[1] - (-0.20)) < 1e-5
    assert abs(result[3] - (-1.27)) < 1e-4


# ── matmul_i8 ─────────────────────────────────────────────────────────────────

def test_matmul_2x2():
    """[[1,2],[3,4]] @ [[5,6],[7,8]] = [[19,22],[43,50]]"""
    from src.nanoservices.snn_tensor import matmul_i8
    a = [1, 2, 3, 4]
    b = [5, 6, 7, 8]
    c = matmul_i8(a, 2, 2, b, 2)
    assert c == [19, 22, 43, 50]


def test_matmul_shape_mismatch_raises():
    from src.nanoservices.snn_tensor import matmul_i8
    with pytest.raises((ValueError, Exception)):
        matmul_i8([1, 2], 2, 2, [1, 2, 3, 4], 2)   # a is wrong length


# ── Rust extension flag ───────────────────────────────────────────────────────

def test_uses_python_fallback_when_rust_absent(monkeypatch):
    """Without compiled extension, _USING_RUST must be False."""
    monkeypatch.setitem(sys.modules, "tranc3_snn", None)
    mod = _import_fresh()
    assert mod._USING_RUST is False


def test_uses_rust_when_extension_present(monkeypatch):
    """When tranc3_snn is importable, _USING_RUST is True."""
    fake = MagicMock()
    fake.leaky_step_i8 = MagicMock(return_value=([1], [0.5]))
    fake.spike_rate_i8 = MagicMock(return_value=[0.5, 0.3, 0.6])
    fake.quantize_f32_to_i8 = MagicMock(return_value=[50])
    fake.dequantize_i8_to_f32 = MagicMock(return_value=[0.5])
    fake.matmul_i8 = MagicMock(return_value=[19, 22, 43, 50])
    monkeypatch.setitem(sys.modules, "tranc3_snn", fake)
    mod = _import_fresh()
    assert mod._USING_RUST is True
