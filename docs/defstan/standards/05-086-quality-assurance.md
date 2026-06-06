# DEF STAN 05-086 — Quality Assurance

**Standard:** DEF STAN 05-086 (adapted)  
**Area Code:** QA  
**Status Summary:** 6 COMPLIANT, 1 PARTIAL  
**Score:** ~92.9%

## Purpose

Establishes quality assurance requirements for the platform: test coverage, static analysis, CI gates, security testing, test traceability, chaos testing, and performance benchmarking.

## Requirements

### REQ-QA-001 — Automated Test Coverage

80+ test files. Unit, integration, end-to-end. Coverage reports on every CI run.

**Evidence:** `tests/test_smoke.py`, `tests/test_uat.py`, `tests/test_chaos.py`, `pyproject.toml`  
**Status:** COMPLIANT

---

### REQ-QA-002 — Static Code Analysis

Python code passes ruff + mypy + black + isort before merge.

**Evidence:** `.pre-commit-config.yaml`, `pyproject.toml`, `.forgejo/workflows/ci.yml`  
**Status:** COMPLIANT

---

### REQ-QA-003 — Continuous Integration Gate

No code merged to main without passing CI: tests, linting, security scans.

**Evidence:** `.forgejo/workflows/ci.yml`, `.forgejo/workflows/production-gate.yml`  
**Status:** COMPLIANT

---

### REQ-QA-004 — Security Testing in CI

SAST, dependency scanning, secret detection on every PR.

**Evidence:** `.forgejo/workflows/security-scan.yml` (bandit, semgrep, gitleaks), `.forgejo/workflows/dependency-audit.yml`  
**Status:** COMPLIANT

---

### REQ-QA-005 — Test Evidence Traceability

Test results persisted in machine-readable format, linked to requirements.

**Evidence:** `pyproject.toml` (logs/test_results.jsonl), `tests/test_compliance.py`  
**Status:** COMPLIANT

---

### REQ-QA-006 — Chaos and Resilience Testing

Regular fault injection: service unavailability, network partitions, invalid input storms.

**Evidence:** `tests/test_chaos.py` (The Chaos Party — Alice in Wonderland themed), `tests/test_resilience.py`  
**Status:** COMPLIANT

---

### REQ-QA-007 — Performance Benchmarking

Key paths benchmarked to establish baselines. CI regression gate on regressions.

**Evidence:** `src/benchmark/`, `tests/test_tranc3_ml.py`  
**Status:** PARTIAL — Benchmarks exist; CI regression gate not yet automated
