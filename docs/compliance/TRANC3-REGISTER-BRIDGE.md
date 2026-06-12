# Tranc3 Register Bridge — Magna Carta ↔ DEFSTAN Mapping

**Version:** 1.0.0 | **Date:** 2026-06-12
**Machine-readable version:** `compliance/tranc3_register_bridge.yaml`

## Purpose

This document maps Magna Carta register items (MC-###) to their corresponding Tranc3 DEFSTAN register entries (REQ-###) and runtime implementations. It serves as the human-readable companion to `compliance/tranc3_register_bridge.yaml`.

## MC ↔ REQ Mapping Table

| MC ID | MC Title | DEFSTAN REQ | Runtime Rule | Implementation |
|---|---|---|---|---|
| MC-001 | Digital Rights Transparency | REQ-IA-006 | MC-RULE-008 | `src/compliance/magna_carta.py` |
| MC-002 | Zero-Cost Sovereignty | REQ-IA-002, REQ-AI-002 | MC-RULE-005 | `src/ai_gateway/`, `workers/rate-limit-service/` |
| MC-003 | Town Hall Governance Gate | REQ-SW-003 | MC-RULE-007 | `src/compliance/cab_gate.py` |
| MC-004 | Magna Carta Runtime Rules | REQ-IA-001, REQ-IA-004 | MC-RULE-001–009 | `src/compliance/magna_carta.py` |
| MC-005 | AI Ethics and Human Agency | REQ-AI-001 | MC-RULE-004 | `src/compliance/ai_governance.py` |
| MC-006 | Policy and Procedure Library | (all areas) | — | `docs/policies/`, `docs/procedures/` |
| MC-007 | Architecture Evidence Pack | REQ-SA-001 | — | `docs/architecture/`, `ARCHITECTURE_THREAT_MODEL.md` |
| MC-008 | HIPAA Alignment Programme | — | MC-RULE-009 | `docs/compliance/HIPAA-ALIGNMENT.md` |
| MC-009 | FCA Alignment Programme | — | — | `docs/compliance/FCA-ALIGNMENT.md` |
| MC-010 | Evidence & Assurance Programme | (all areas) | — | `docs/compliance/`, `docs/governance/`, `docs/evidence/` |
| MC-011 | Infinity App Bridge | REQ-IA-001, REQ-AI-001 | — | `compliance/tranc3_register_bridge.yaml` |

## Checker Integration

```python
# Load merged register (DEFSTAN + Magna Carta)
from src.compliance.checker import load_and_check_merged, REGISTER_PATH
from pathlib import Path

mc_register = Path("compliance/magna-carta/compliance/magna_carta_register.yaml")
report = load_and_check_merged(REGISTER_PATH, mc_register)

# Get Magna Carta area score
for area in report.areas:
    if area.code == "MC":
        print(f"Magna Carta score: {area.score:.1f}%")
```

## Staging Enablement Guide

### Step 1: Development/Staging
```bash
MAGNA_CARTA_ENABLED=true  # in .env
CAB_GATE_ENABLED=false     # keep disabled in dev
```

### Step 2: Pre-production Testing
```bash
MAGNA_CARTA_ENABLED=true
CAB_GATE_ENABLED=true      # enable CAB gate
CAB_PROTECTED_PATHS=/admin/,/config/,/deploy/
```

### Step 3: Production
```bash
MAGNA_CARTA_ENABLED=true
CAB_GATE_ENABLED=true
# All X-Change-ID headers enforced on mutating requests to protected paths
```

### Checker Invocation

```bash
# Check DEFSTAN only
make compliance-check

# Check Magna Carta only  
make compliance-mc

# Full merged check (recommended)
make compliance-merged
```

## Status Definitions for MC Register

| Status | Score Weight | Meaning |
|---|---|---|
| PROGRAMME_ARTEFACT | 0 (≈ PLANNED) | Documentation exists in MC programme; operational validation pending |
| COMPLIANT | 1.0 | Fully implemented and evidence verified |
| PARTIAL | 0.5 | Partially implemented |
| WAIVED | Excluded | Formally waived with justification |
| NA | Excluded | Not applicable to this platform |

## Evidence Path Resolution

All evidence paths in the MC register are resolved relative to the Tranc3 repo root (`/home/user/Tranc3/`). Paths must exist as files or directories to count toward evidence verification.

## Review History

| Date | Reviewer | Action |
|---|---|---|
| 2026-06-12 | Trancendos | Initial register bridge document |
