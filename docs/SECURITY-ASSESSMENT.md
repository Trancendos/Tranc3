# Tranc3 Security Vulnerability Assessment

**Date:** 2026-05-21
**Scope:** Dependency vulnerability analysis and risk assessment
**Author:** Automated Security Remediation Pipeline

---

## Executive Summary

This document provides a detailed risk assessment for all known vulnerabilities in Tranc3 dependencies. Of 12 identified CVEs/PYSECs, 1 has been remediated (sentencepiece CVE-2026-1260) and 11 remain in torch with documented mitigations. All torch vulnerabilities require local access, have high attack complexity, or affect components not used by Tranc3.

---

## Remediated Vulnerabilities

| Package | CVE | Status | Fix |
|---------|-----|--------|-----|
| sentencepiece | CVE-2026-1260 | ✅ Fixed | Updated 0.2.0 → 0.2.1 |

---

## Active Vulnerabilities — PyTorch Risk Assessment

All 10 remaining PYSEC advisories affect `torch==2.12.0`. No upstream fix version is available at this time. Below is a per-advisory risk assessment with Tranc3-specific mitigations.

### PYSEC-2025-210 — Profiler DoS
- **Severity:** Low
- **Vector:** Local
- **Component:** `torch.profiler.profile`
- **Impact:** Application crash/hang if `profiler.stop()` is omitted
- **Tranc3 Exposure:** **NONE** — Tranc3 does not use the PyTorch profiler
- **Mitigation:** Not applicable; profiler not in use

### PYSEC-2025-194 — torch.jit.script Memory Corruption
- **Severity:** Critical (CVSS unspecified)
- **Vector:** Local
- **Component:** `torch.jit.script`
- **Impact:** Memory corruption via crafted script input
- **Tranc3 Exposure:** **NONE** — Tranc3 does not use TorchScript JIT compilation
- **Mitigation:** `torch.jit.script` is never called in the codebase

### PYSEC-2025-196 — torch.jit.jit_module_from_flatbuffer Memory Corruption
- **Severity:** Problematic
- **Vector:** Local
- **Component:** `torch.jit.jit_module_from_flatbuffer`
- **Impact:** Memory corruption from flatbuffer deserialization
- **Tranc3 Exposure:** **NONE** — Tranc3 does not load flatbuffer models
- **Mitigation:** No flatbuffer model loading in codebase

### PYSEC-2025-195 — torch.lstm_cell Memory Corruption
- **Severity:** Critical
- **Vector:** Local
- **Component:** `torch.lstm_cell`
- **Impact:** Memory corruption in LSTM cell computation
- **Tranc3 Exposure:** **LOW** — LSTM cells are used in inference, but attack requires crafted local input
- **Mitigation:** All model inputs are sanitized through the tokenizer pipeline; no raw tensor input accepted

### PYSEC-2025-193 — torch.nn.utils.rnn.unpack_sequence Memory Corruption
- **Severity:** Critical
- **Vector:** Local
- **Component:** `torch.nn.utils.rnn.unpack_sequence`
- **Impact:** Memory corruption in RNN sequence unpacking
- **Tranc3 Exposure:** **LOW** — Same as PYSEC-2025-195; requires local access and crafted input
- **Mitigation:** Input sanitization through tokenizer; no direct tensor manipulation

### PYSEC-2025-192 — torch.nn.utils.rnn.pad_packed_sequence Memory Corruption
- **Severity:** Critical
- **Vector:** Local
- **Component:** `torch.nn.utils.rnn.pad_packed_sequence`
- **Impact:** Memory corruption in RNN padding
- **Tranc3 Exposure:** **LOW** — Same vector as above
- **Mitigation:** Input sanitization; no direct packed sequence manipulation

### PYSEC-2026-139 — pt2 Loading Handler Deserialization
- **Severity:** Unspecified
- **Vector:** Local
- **Component:** pt2 Loading Handler
- **Impact:** Deserialization attack via malicious .pt2 files
- **Tranc3 Exposure:** **NONE** — All `torch.load()` calls use `weights_only=True`
- **Mitigation:** `weights_only=True` prevents arbitrary code execution during deserialization

### PYSEC-2025-191 — torch.mkldnn_max_pool2d DoS
- **Severity:** Problematic
- **Vector:** Local
- **Component:** `torch.mkldnn_max_pool2d`
- **Impact:** Denial of service via MKL-DNN pooling
- **Tranc3 Exposure:** **NONE** — Disputed vulnerability; Tranc3 does not use mkldnn pooling directly
- **Mitigation:** Not applicable

### PYSEC-2025-197 — CUDA Caching Allocator Memory Corruption
- **Severity:** Problematic
- **Vector:** Local
- **Component:** `c10/cuda/CUDACachingAllocator.cpp`
- **Impact:** Memory corruption in CUDA allocator
- **Tranc3 Exposure:** **LOW** — CUDA allocator is internal to PyTorch; requires direct manipulation
- **Mitigation:** No direct CUDA allocator interaction in Tranc3 codebase

### PYSEC-2025-189 — Tuple Handler Memory Corruption (Remote-capable)
- **Severity:** Critical
- **Vector:** Remote (high complexity)
- **Component:** `torch.ops.profiler._call_end_callbacks_on_jit_fut`
- **Impact:** Memory corruption via profiler callback manipulation
- **Tranc3 Exposure:** **NONE** — Tranc3 does not use profiler callbacks; attack complexity is high
- **Mitigation:** Profiler not in use; remote exploitation considered infeasible

### PYSEC-2025-190 — Quantized Sigmoid Improper Initialization
- **Severity:** Problematic
- **Vector:** Local
- **Component:** `nnq_Sigmoid` (Quantized Sigmoid Module)
- **Impact:** Improper initialization via scale/zero_point manipulation
- **Tranc3 Exposure:** **NONE** — Tranc3 does not use quantized sigmoid modules
- **Mitigation:** Not applicable

---

## Compensating Controls

The following controls reduce the effective risk of all torch vulnerabilities:

1. **`weights_only=True`** on all `torch.load()` calls — prevents deserialization attacks
2. **No JIT compilation** — `torch.jit.script` and `torch.jit.trace` are never called
3. **No profiler usage** — `torch.profiler` is not used in production or testing
4. **Input sanitization** — all user input passes through the tokenizer pipeline before tensor conversion
5. **No untrusted model loading** — models are loaded only from configured, trusted sources
6. **Container security** — non-root execution, read-only filesystems, resource limits
7. **Network isolation** — inference workers run in isolated network segments

---

## Recommendation

**Accept residual risk** for torch vulnerabilities. All are either:
- Not applicable to Tranc3's usage pattern (profiler, JIT, quantization)
- Local-attack-vector only (requires server access, which is already controlled)
- High complexity / disputed (PYSEC-2025-191, PYSEC-2025-191)
- Already mitigated by `weights_only=True` (deserialization)

**Monitor** for upstream PyTorch releases that address these CVEs and upgrade when available.

---

## Code Scanning Results

### Bandit (Python SAST)
- **Before remediation:** 75 issues (6 MEDIUM, 69 LOW)
- **After remediation:** 0 issues
- **Fixes applied:** B110 (41), B105 (15), B311 (9), B101 (3), B614 (3), B104 (1), B108 (1), B106 (1), B615 (1)

### pip-audit
- **Before remediation:** 12 vulnerabilities (2 packages)
- **After remediation:** 11 vulnerabilities (1 package — torch, documented above)
- **Fixed:** CVE-2026-1260 (sentencepiece 0.2.0 → 0.2.1)

---

*This assessment should be reviewed quarterly or when new PyTorch versions are released.*
