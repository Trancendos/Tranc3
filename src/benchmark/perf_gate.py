"""
REQ-QA-007: Performance Regression Gate — CI enforcer.

Runs a lightweight, dependency-free benchmark suite against the local
Tranc3 module layer (no HTTP server required) and compares results
against a committed baseline file.

Exit codes:
  0  — All benchmarks pass; no regressions.
  1  — One or more regressions detected; CI gate fails.
  2  — Baseline file missing; writes a new baseline and exits 0
       (first-run seeding mode).

Usage::

    python -m src.benchmark.perf_gate                 # gate check
    python -m src.benchmark.perf_gate --update        # refresh baseline
    python -m src.benchmark.perf_gate --report        # JSON report to stdout
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

BASELINE_PATH = Path(__file__).parent / "baseline.json"

# Regression thresholds
RPS_REGRESSION_RATIO = 0.85  # measured RPS < baseline * this → regression
P99_REGRESSION_RATIO = 1.20  # measured P99 > baseline * this → regression


# ---------------------------------------------------------------------------
# Micro-benchmark helpers
# ---------------------------------------------------------------------------


class BenchResult(NamedTuple):
    name: str
    rps: float
    p50_ms: float
    p99_ms: float
    error_rate: float


def _run_micro(name: str, fn, n: int = 200, warmup: int = 20) -> BenchResult:
    """Call fn() n times and return latency/throughput stats."""
    for _ in range(warmup):
        try:
            fn()
        except Exception:
            pass

    latencies: List[float] = []
    errors = 0
    t0 = time.perf_counter()
    for _ in range(n):
        t = time.perf_counter()
        try:
            fn()
        except Exception:
            errors += 1
        latencies.append((time.perf_counter() - t) * 1000)
    elapsed = time.perf_counter() - t0

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p99 = latencies[int(len(latencies) * 0.99)]
    rps = n / elapsed if elapsed > 0 else 0.0
    return BenchResult(name, rps, p50, p99, errors / n)


# ---------------------------------------------------------------------------
# Benchmark suite (pure-Python, no server needed)
# ---------------------------------------------------------------------------


def _build_suite() -> List[BenchResult]:
    results: List[BenchResult] = []

    # 1. Encrypted-SQLite field round-trip (REQ-IA-010)
    try:
        from src.database.encrypted_sqlite import decrypt_field, encrypt_field

        payload = b"sensitive_value_" * 4
        key = b"\x00" * 32
        results.append(
            _run_micro(
                "encrypted_sqlite_roundtrip",
                lambda: decrypt_field(encrypt_field(payload, key), key),
            )
        )
    except Exception:
        results.append(BenchResult("encrypted_sqlite_roundtrip", 0.0, 0.0, 0.0, 1.0))

    # 2. Output safety filter (REQ-SA-003)
    try:
        from src.core.output_safety import OutputSafetyFilter

        f = OutputSafetyFilter()
        results.append(
            _run_micro(
                "output_safety_filter",
                lambda: f.check("Hello, the answer is 42. Here is some helpful output."),
            )
        )
    except Exception:
        results.append(BenchResult("output_safety_filter", 0.0, 0.0, 0.0, 1.0))

    # 3. Resource limits lookup (REQ-SA-005)
    try:
        from src.core.resource_limits import ResourceLimits

        rl = ResourceLimits()
        results.append(
            _run_micro(
                "resource_limits_lookup",
                lambda: rl.http_timeout,
                n=500,
            )
        )
    except Exception:
        results.append(BenchResult("resource_limits_lookup", 0.0, 0.0, 0.0, 1.0))

    # 4. SNN tensor quantize (TR3-010)
    try:
        from src.nanoservices.snn_tensor import quantize_f32_to_i8

        data = [float(i) / 100 for i in range(128)]
        results.append(
            _run_micro(
                "snn_quantize_128",
                lambda: quantize_f32_to_i8(data, 0.01),
                n=500,
            )
        )
    except Exception:
        results.append(BenchResult("snn_quantize_128", 0.0, 0.0, 0.0, 1.0))

    # 5. Ice Box threat scan (REQ-SA-006)
    try:
        from src.security.ice_box.analyser import ThreatAnalyser

        analyser = ThreatAnalyser()
        sample = "SELECT * FROM users WHERE id=1; DROP TABLE users;--"
        results.append(
            _run_micro(
                "ice_box_scan",
                lambda: analyser.analyse(sample),
            )
        )
    except Exception:
        results.append(BenchResult("ice_box_scan", 0.0, 0.0, 0.0, 1.0))

    return results


# ---------------------------------------------------------------------------
# Baseline management
# ---------------------------------------------------------------------------


def load_baseline() -> Optional[Dict[str, dict]]:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text())


def save_baseline(results: List[BenchResult]) -> None:
    data = {r.name: {"rps": r.rps, "p99_ms": r.p99_ms} for r in results}
    BASELINE_PATH.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------


def run_gate(update: bool = False, report: bool = False) -> int:
    results = _build_suite()

    if report:
        print(json.dumps([r._asdict() for r in results], indent=2))

    baseline = load_baseline()

    if baseline is None or update:
        save_baseline(results)
        if not update:
            print("[perf-gate] No baseline found — seeding baseline.json (first run).")
            print("[perf-gate] Re-run to gate against this baseline.")
        else:
            print("[perf-gate] Baseline updated.")
        return 0

    regressions: List[str] = []
    rows = []
    for r in results:
        b = baseline.get(r.name)
        if b is None:
            rows.append(f"  {r.name:<40} NEW   rps={r.rps:.0f}  p99={r.p99_ms:.1f}ms")
            continue

        rps_ok = r.rps >= b["rps"] * RPS_REGRESSION_RATIO
        p99_ok = r.p99_ms <= b["p99_ms"] * P99_REGRESSION_RATIO
        status = "PASS" if (rps_ok and p99_ok) else "FAIL"
        if status == "FAIL":
            regressions.append(r.name)
        rows.append(
            f"  {r.name:<40} {status}  "
            f"rps={r.rps:.0f} (base={b['rps']:.0f})  "
            f"p99={r.p99_ms:.1f}ms (base={b['p99_ms']:.1f}ms)"
        )

    print("[perf-gate] Performance regression gate results:")
    for row in rows:
        print(row)

    if regressions:
        print(f"\n[perf-gate] FAILED — {len(regressions)} regression(s): {', '.join(regressions)}")
        return 1

    print(f"\n[perf-gate] PASSED — {len(results)} benchmarks, 0 regressions.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tranc3 performance regression gate")
    parser.add_argument("--update", action="store_true", help="Refresh baseline")
    parser.add_argument("--report", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()
    sys.exit(run_gate(update=args.update, report=args.report))
