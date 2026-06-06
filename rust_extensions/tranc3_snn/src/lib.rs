/*!
 * tranc3_snn — INT8 SNN tensor hot paths via PyO3
 *
 * Provides accelerated implementations of the inner loops from
 * src/personality/snn_qat.py that are performance-critical:
 *
 *   1. `leaky_step_i8(weights, bias, inputs, mem, beta, threshold)`
 *      → (spikes: Vec<i8>, mem: Vec<f32>)
 *      One time-step of a Leaky Integrate-and-Fire layer with INT8 weights.
 *
 *   2. `spike_rate_i8(weights_l1, bias_l1, weights_l2, bias_l2,
 *                     inputs, t_steps, beta, threshold)`
 *      → Vec<f32>
 *      Full two-layer forward pass over t_steps; returns spike-rate vector.
 *
 *   3. `quantize_f32_to_i8(data, scale)` → Vec<i8>
 *      Symmetric per-tensor INT8 quantization: round(x / scale) clipped to [-127, 127].
 *
 *   4. `dequantize_i8_to_f32(data, scale)` → Vec<f32>
 *      Inverse: data[i] * scale.
 *
 *   5. `matmul_i8(a, a_rows, a_cols, b, b_cols)` → Vec<i32>
 *      Flat INT8 matrix multiply → INT32 accumulator (no overflow guard needed
 *      for our small matrices, but we use i32 accumulators throughout).
 */

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

// ──────────────────────────────────────────────────────────��──────────────────
// Internal helpers
// ─────────────────────────────────────────────────────────────────────────────

#[inline]
fn relu(x: f32) -> f32 {
    if x > 0.0 { x } else { 0.0 }
}

/// Leaky Integrate-and-Fire membrane update for a single neuron.
/// Returns (spike, new_mem).
#[inline]
fn lif_update(current: f32, mem: f32, beta: f32, threshold: f32) -> (i8, f32) {
    let new_mem = beta * mem + current;
    if new_mem >= threshold {
        (1i8, new_mem - threshold)   // spike + reset
    } else {
        (0i8, new_mem)
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. leaky_step_i8
// ─────────────────────────────────────────────────────────────────────────────

/// One time-step of a Leaky-IF layer with INT8 weights.
///
/// Parameters
/// ----------
/// weights  : flat row-major INT8 weight matrix, shape (out_dim, in_dim)
/// bias     : float32 bias vector, length out_dim
/// inputs   : float32 input activations, length in_dim
/// mem      : float32 membrane potential, length out_dim (updated in place)
/// beta     : membrane decay factor [0, 1)
/// threshold: spike threshold
///
/// Returns
/// -------
/// (spikes: list[int], new_mem: list[float])
#[pyfunction]
fn leaky_step_i8(
    weights: Vec<i8>,
    bias: Vec<f32>,
    inputs: Vec<f32>,
    mem: Vec<f32>,
    beta: f32,
    threshold: f32,
) -> PyResult<(Vec<i8>, Vec<f32>)> {
    let in_dim = inputs.len();
    let out_dim = bias.len();

    if weights.len() != out_dim * in_dim {
        return Err(PyValueError::new_err(format!(
            "weights length {} != out_dim({}) * in_dim({})",
            weights.len(), out_dim, in_dim
        )));
    }
    if mem.len() != out_dim {
        return Err(PyValueError::new_err("mem length must equal out_dim"));
    }

    let mut spikes = Vec::with_capacity(out_dim);
    let mut new_mem = Vec::with_capacity(out_dim);

    for j in 0..out_dim {
        let row = &weights[j * in_dim..(j + 1) * in_dim];
        let current: f32 = row.iter()
            .zip(inputs.iter())
            .map(|(&w, &x)| (w as f32) * x)
            .sum::<f32>()
            + bias[j];
        let (spk, nm) = lif_update(relu(current), mem[j], beta, threshold);
        spikes.push(spk);
        new_mem.push(nm);
    }

    Ok((spikes, new_mem))
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. spike_rate_i8
// ─────────────────────────────────────────────────────────────────────────────

/// Full two-layer SNN forward pass, returning spike rates.
///
/// Parameters
/// ----------
/// weights_l1 : flat INT8 (hidden_dim × input_dim)
/// bias_l1    : f32 (hidden_dim,)
/// weights_l2 : flat INT8 (output_dim × hidden_dim)
/// bias_l2    : f32 (output_dim,)
/// inputs     : f32 (input_dim,) — same input is presented for all t_steps
/// t_steps    : number of temporal unrolling steps
/// beta       : membrane decay factor
/// threshold  : spike threshold
///
/// Returns
/// -------
/// spike rates: Vec<f32> (output_dim,), each in [0.0, 1.0]
#[pyfunction]
fn spike_rate_i8(
    weights_l1: Vec<i8>,
    bias_l1: Vec<f32>,
    weights_l2: Vec<i8>,
    bias_l2: Vec<f32>,
    inputs: Vec<f32>,
    t_steps: usize,
    beta: f32,
    threshold: f32,
) -> PyResult<Vec<f32>> {
    let hidden_dim = bias_l1.len();
    let output_dim = bias_l2.len();
    let input_dim = inputs.len();

    if weights_l1.len() != hidden_dim * input_dim {
        return Err(PyValueError::new_err("weights_l1 shape mismatch"));
    }
    if weights_l2.len() != output_dim * hidden_dim {
        return Err(PyValueError::new_err("weights_l2 shape mismatch"));
    }
    if t_steps == 0 {
        return Err(PyValueError::new_err("t_steps must be >= 1"));
    }

    let mut mem1 = vec![0.0f32; hidden_dim];
    let mut mem2 = vec![0.0f32; output_dim];
    let mut spike_acc = vec![0.0f32; output_dim];

    for _ in 0..t_steps {
        // Layer 1
        let mut spk1 = Vec::with_capacity(hidden_dim);
        let mut new_mem1 = Vec::with_capacity(hidden_dim);
        for j in 0..hidden_dim {
            let row = &weights_l1[j * input_dim..(j + 1) * input_dim];
            let current: f32 = row.iter()
                .zip(inputs.iter())
                .map(|(&w, &x)| (w as f32) * x)
                .sum::<f32>()
                + bias_l1[j];
            let (spk, nm) = lif_update(relu(current), mem1[j], beta, threshold);
            spk1.push(spk as f32);
            new_mem1.push(nm);
        }
        mem1 = new_mem1;

        // Layer 2
        let mut new_mem2 = Vec::with_capacity(output_dim);
        for k in 0..output_dim {
            let row = &weights_l2[k * hidden_dim..(k + 1) * hidden_dim];
            let current: f32 = row.iter()
                .zip(spk1.iter())
                .map(|(&w, &s)| (w as f32) * s)
                .sum::<f32>()
                + bias_l2[k];
            let (spk, nm) = lif_update(relu(current), mem2[k], beta, threshold);
            spike_acc[k] += spk as f32;
            new_mem2.push(nm);
        }
        mem2 = new_mem2;
    }

    // Return spike rates (divide by t_steps)
    let rates: Vec<f32> = spike_acc.iter().map(|&s| s / t_steps as f32).collect();
    Ok(rates)
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. quantize_f32_to_i8
// ─────────────────────────────────────────────────────────────────────────────

/// Symmetric per-tensor INT8 quantization.
/// result[i] = round(data[i] / scale), clipped to [-127, 127].
#[pyfunction]
fn quantize_f32_to_i8(data: Vec<f32>, scale: f32) -> PyResult<Vec<i8>> {
    if scale == 0.0 {
        return Err(PyValueError::new_err("scale must not be 0"));
    }
    Ok(data.iter()
        .map(|&x| {
            let q = (x / scale).round();
            q.max(-127.0).min(127.0) as i8
        })
        .collect())
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. dequantize_i8_to_f32
// ─────────────────────────────────────────────────────────────────────────────

/// Dequantize INT8 values back to float32: result[i] = data[i] * scale.
#[pyfunction]
fn dequantize_i8_to_f32(data: Vec<i8>, scale: f32) -> Vec<f32> {
    data.iter().map(|&x| (x as f32) * scale).collect()
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. matmul_i8
// ─────────────────────────────────────────────────────────────────────────────

/// Flat INT8 matrix multiply: C = A @ B (INT32 accumulator).
///
/// a       : flat row-major INT8, shape (a_rows, a_cols)
/// a_rows  : rows of A
/// a_cols  : cols of A = rows of B
/// b       : flat row-major INT8, shape (a_cols, b_cols)
/// b_cols  : cols of B
///
/// Returns flat row-major INT32, shape (a_rows, b_cols).
#[pyfunction]
fn matmul_i8(
    a: Vec<i8>,
    a_rows: usize,
    a_cols: usize,
    b: Vec<i8>,
    b_cols: usize,
) -> PyResult<Vec<i32>> {
    if a.len() != a_rows * a_cols {
        return Err(PyValueError::new_err("a length != a_rows * a_cols"));
    }
    if b.len() != a_cols * b_cols {
        return Err(PyValueError::new_err("b length != a_cols * b_cols"));
    }

    let mut c = vec![0i32; a_rows * b_cols];
    for i in 0..a_rows {
        for k in 0..a_cols {
            let av = a[i * a_cols + k] as i32;
            for j in 0..b_cols {
                c[i * b_cols + j] += av * (b[k * b_cols + j] as i32);
            }
        }
    }
    Ok(c)
}

// ─────────────────────────────────────────────────────────────────────────────
// Module registration
// ─────────────────────────────────────────────────────────────────────────────

#[pymodule]
fn tranc3_snn(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(leaky_step_i8, m)?)?;
    m.add_function(wrap_pyfunction!(spike_rate_i8, m)?)?;
    m.add_function(wrap_pyfunction!(quantize_f32_to_i8, m)?)?;
    m.add_function(wrap_pyfunction!(dequantize_i8_to_f32, m)?)?;
    m.add_function(wrap_pyfunction!(matmul_i8, m)?)?;
    Ok(())
}
