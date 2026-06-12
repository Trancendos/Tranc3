# Tranc3 — Master Framework Blueprint

**Version:** 1.0.0 | **Date:** 2026-06-12
**Classification:** UNCLASSIFIED — PUBLIC

## Overview

Tranc3 is the technology backbone of the Trancendos Universe — a zero-cost, fully self-hosted AI platform governed by the Magna Carta compliance framework and DEFSTAN requirements. This document is the master framework blueprint.

## Framework Stack

```
┌─────────────────────────────────────────────────────────────┐
│                   EXTERNAL FRAMEWORKS                        │
│  ISO 27001:2022 · GDPR · HIPAA (opt-in) · FCA · EU AI Act  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                MAGNA CARTA FRAMEWORK                         │
│    9 runtime rules · 11 register requirements               │
│    compliance/magna-carta/  (git submodule)                 │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   DEFSTAN REGISTER                           │
│    7 control areas · 40+ requirements                       │
│    compliance/register.yaml                                 │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│               RUNTIME ENFORCEMENT                            │
│    ZeroTrust → MagnaCarta → CABMiddleware                   │
│    api.py middleware stack                                  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│               EVIDENCE REPOSITORY                            │
│    docs/ · compliance/ · src/ (this repository)            │
└─────────────────────────────────────────────────────────────┘
```

## Core Principles

1. **Zero-Cost Sovereignty** — No mandatory paid APIs. See `docs/01-MAGNACARTA-FOUNDATION.md`
2. **Compliance as Code** — Registers are machine-readable YAML; checker runs in CI
3. **Defence in Depth** — Middleware stack enforces multiple layers
4. **Evidence-Driven** — Every compliance claim backed by a file in this repo
5. **Continuous Improvement** — PDCA cycle documented in `docs/governance/CONTINUOUS-IMPROVEMENT-PROGRAMME.md`

## Framework Documents

| Document | Purpose |
|---|---|
| `compliance/register.yaml` | DEFSTAN compliance register |
| `compliance/magna-carta/compliance/magna_carta_register.yaml` | Magna Carta register |
| `compliance/tranc3_register_bridge.yaml` | MC ↔ DEFSTAN bridge |
| `config/magna_carta_config.json` | Runtime rule configuration |
| `docs/architecture/AS-BUILT-ARCHITECTURE.md` | Canonical architecture |
| `docs/architecture/CONTROL-TO-COMPONENT-MAP.md` | Control traceability |
| `ARCHITECTURE_THREAT_MODEL.md` | STRIDE threat analysis |
| `docs/compliance/COMPLIANCE-BLUEPRINT.md` | Compliance operating model |

## Platform Entities

43 named platform entities. Full register: `PLATFORM_ENTITIES.md` and `src/entities/platform.py`.

## Contact

Platform Engineering: Trancendos | via The Town Hall governance board
