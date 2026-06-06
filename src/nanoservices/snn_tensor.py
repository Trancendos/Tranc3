"""
TR3-010: Rust Tensor Nanoservice — INT8 SNN hot paths via tranc3_snn PyO3 extension.

Provides Python-accessible wrappers around the Rust-compiled INT8 SNN kernels.
Falls back to pure-Python implementations when the compiled extension is not
available (development, CI without maturin, non-x86 targets).

Exposed API
-----------
leaky_step_i8(weights, bias, inputs, mem, beta, threshold)
    → (spikes: list[int], new_mem: list[float])

spike_rate_i8(weights_l1, bias_l1, weights_l2, bias_l2,
              inputs, t_steps, beta, threshold)
    → list[float]   # spike rates in [0, 1]

quantize_f32_to_i8(data, scale) → list[int]
dequantize_i8_to_f32(data, scale) → list[float]
matmul_i8(a, a_rows, a_cols, b, b_cols) → list[int]
"""

from __future__ import annotations

import logging
from typing import List, Sequence, Tuple

logger = logging.getLogger(__name__)

# ── attempt to load Rust extension ────────────────────────────────��──────────

try:
    from tranc3_snn import (  # type: ignore[import]
        leaky_step_i8 as _rust_leaky_step_i8,
        spike_rate_i8 as _rust_spike_rate_i8,
        quantize_f32_to_i8 as _rust_quantize,
        dequantize_i8_to_f32 as _rust_dequantize,
        matmul_i8 as _rust_matmul,
    )
    _USING_RUST = True
    logger.debug("snn_tensor: Rust extension loaded — using tranc3_snn kernels")
except ImportError:
    _USING_RUST = False
    logger.debug("snn_tensor: Rust extension not available — using Python fallback")


# ── Python fallback implementations ──────────────────────────────────────────

def _py_leaky_step_i8(
    weights: Sequence[int],
    bias: Sequence[float],
    inputs: Sequence[float],
    mem: Sequence[float],
    beta: float,
    threshold: float,
) -> Tuple[List[int], List[float]]:
    in_dim = len(inputs)
    out_dim = len(bias)
    if len(weights) != out_dim * in_dim:
        raise ValueError(f"weights length {len(weights)} != {out_dim} * {in_dim}")
    if len(mem) != out_dim:
        raise ValueError("mem length must equal out_dim")

    spikes: List[int] = []
    new_mem: List[float] = []
    for j in range(out_dim):
        row = weights[j * in_dim:(j + 1) * in_dim]
        current = sum(int(w) * x for w, x in zip(row, inputs)) + bias[j]
        current = max(0.0, current)   # ReLU
        nm = beta * mem[j] + current
        if nm >= threshold:
            spikes.append(1)
            new_mem.append(nm - threshold)
        else:
            spikes.append(0)
            new_mem.append(nm)
    return spikes, new_mem


def _py_spike_rate_i8(
    weights_l1: Sequence[int],
    bias_l1: Sequence[float],
    weights_l2: Sequence[int],
    bias_l2: Sequence[float],
    inputs: Sequence[float],
    t_steps: int,
    beta: float,
    threshold: float,
) -> List[float]:
    if t_steps <= 0:
        raise ValueError("t_steps must be >= 1")
    hidden_dim = len(bias_l1)
    output_dim = len(bias_l2)
    _input_dim = len(inputs)

    mem1 = [0.0] * hidden_dim
    mem2 = [0.0] * output_dim
    spike_acc = [0.0] * output_dim

    for _ in range(t_steps):
        spk1, mem1 = _py_leaky_step_i8(weights_l1, bias_l1, inputs, mem1, beta, threshold)
        spk1_f = [float(s) for s in spk1]
        spk2, mem2 = _py_leaky_step_i8(weights_l2, bias_l2, spk1_f, mem2, beta, threshold)
        for k in range(output_dim):
            spike_acc[k] += spk2[k]

    return [s / t_steps for s in spike_acc]


def _py_quantize_f32_to_i8(data: Sequence[float], scale: float) -> List[int]:
    if scale == 0.0:
        raise ValueError("scale must not be 0")
    result: List[int] = []
    for x in data:
        q = round(x / scale)
        result.append(max(-127, min(127, q)))
    return result


def _py_dequantize_i8_to_f32(data: Sequence[int], scale: float) -> List[float]:
    return [int(x) * scale for x in data]


def _py_matmul_i8(
    a: Sequence[int],
    a_rows: int,
    a_cols: int,
    b: Sequence[int],
    b_cols: int,
) -> List[int]:
    if len(a) != a_rows * a_cols:
        raise ValueError("a length != a_rows * a_cols")
    if len(b) != a_cols * b_cols:
        raise ValueError("b length != a_cols * b_cols")
    c = [0] * (a_rows * b_cols)
    for i in range(a_rows):
        for k in range(a_cols):
            av = int(a[i * a_cols + k])
            for j in range(b_cols):
                c[i * b_cols + j] += av * int(b[k * b_cols + j])
    return c


# ── public API (dispatch to Rust or Python) ───────────────────────────────────

def leaky_step_i8(
    weights: Sequence[int],
    bias: Sequence[float],
    inputs: Sequence[float],
    mem: Sequence[float],
    beta: float = 0.9,
    threshold: float = 1.0,
) -> Tuple[List[int], List[float]]:
    """One LIF time-step with INT8 weights. Returns (spikes, new_mem)."""
    if _USING_RUST:
        return _rust_leaky_step_i8(
            list(weights), list(bias), list(inputs), list(mem), beta, threshold
        )
    return _py_leaky_step_i8(weights, bias, inputs, mem, beta, threshold)


def spike_rate_i8(
    weights_l1: Sequence[int],
    bias_l1: Sequence[float],
    weights_l2: Sequence[int],
    bias_l2: Sequence[float],
    inputs: Sequence[float],
    t_steps: int = 8,
    beta: float = 0.9,
    threshold: float = 1.0,
) -> List[float]:
    """Two-layer SNN forward pass; returns spike-rate vector."""
    if _USING_RUST:
        return _rust_spike_rate_i8(
            list(weights_l1), list(bias_l1),
            list(weights_l2), list(bias_l2),
            list(inputs), t_steps, beta, threshold,
        )
    return _py_spike_rate_i8(
        weights_l1, bias_l1, weights_l2, bias_l2, inputs, t_steps, beta, threshold
    )


def quantize_f32_to_i8(data: Sequence[float], scale: float) -> List[int]:
    """Symmetric per-tensor INT8 quantization."""
    if _USING_RUST:
        return list(_rust_quantize(list(data), scale))
    return _py_quantize_f32_to_i8(data, scale)


def dequantize_i8_to_f32(data: Sequence[int], scale: float) -> List[float]:
    """Dequantize INT8 → float32."""
    if _USING_RUST:
        return list(_rust_dequantize(list(data), scale))
    return _py_dequantize_i8_to_f32(data, scale)


def matmul_i8(
    a: Sequence[int],
    a_rows: int,
    a_cols: int,
    b: Sequence[int],
    b_cols: int,
) -> List[int]:
    """Flat INT8 matrix multiply → INT32 accumulator."""
    if _USING_RUST:
        return list(_rust_matmul(list(a), a_rows, a_cols, list(b), b_cols))
    return _py_matmul_i8(a, a_rows, a_cols, b, b_cols)
