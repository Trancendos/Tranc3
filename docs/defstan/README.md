# DEFSTAN Compliance Framework — Tranc3 / Trancendos Platform

## Scope

This framework applies DEF STAN (UK Defence Standards) discipline and rigour to the Tranc3 / Trancendos platform — a **public civilian application**. The standards are used as a quality benchmark, not as a regulatory requirement. Applicability is voluntary and proportionate.

## Classification

**UNCLASSIFIED — PUBLIC**

## Applicability Statement

The following DEF STAN standards have been mapped to Tranc3 platform requirements:

| Standard | Area Code | Title | Applicability |
|----------|-----------|-------|---------------|
| DEF STAN 00-700 | IA | Information Assurance | Full — all public-facing services |
| DEF STAN 00-055 | SA | Safety-Related Software | Adapted — AI safety and fail-safe design |
| DEF STAN 00-056 | SD | Software Development | Full — all platform code |
| DEF STAN 00-600 | SU | Supportability (ILS) | Adapted — operational observability |
| DEF STAN 00-044 | CM | Configuration Management | Full — all artefacts and infrastructure |
| DEF STAN 05-086 | QA | Quality Assurance | Full — CI/CD and testing |
| DEF STAN 05-057 | TD | Technical Documentation (IETM-inspired) | Adapted — platform documentation |

## Structure

```
docs/defstan/
  README.md                          -- this file (master index)
  COMPLIANCE_REGISTER.md             -- human-readable compliance register
  standards/
    00-700-information-assurance.md  -- IA requirements
    00-055-safety-software.md        -- SA requirements
    00-056-software-development.md   -- SD requirements
    00-600-supportability.md         -- SU requirements
    00-044-configuration-management.md  -- CM requirements
    05-086-quality-assurance.md      -- QA requirements
    05-057-ietm.md                   -- TD requirements

compliance/
  register.yaml        -- machine-readable compliance register (source of truth)
  waivers.yaml         -- formal waiver register
  test_evidence.yaml   -- test file -> requirement mappings

src/compliance/
  __init__.py
  checker.py           -- compliance checker (runnable standalone)
  report_generator.py  -- JSON / Markdown / HTML report generation
  traceability.py      -- traceability matrix builder
  api_routes.py        -- FastAPI /compliance/* endpoints
```

## Quick Start

```bash
# Run compliance checker (summary)
python -m src.compliance.checker

# Generate full JSON report
python -m src.compliance.checker --report

# CI gate (exits 1 if score < 70%)
python -m src.compliance.checker --ci

# Makefile shortcuts
make compliance-check
make compliance-report
make compliance-ci
```

## API Endpoints

When the backend is running (`make dev-api`):

| Endpoint | Description |
|----------|-------------|
| `GET /compliance/status` | Live compliance status JSON |
| `GET /compliance/report` | Full compliance report JSON |
| `GET /compliance/matrix` | Traceability matrix JSON |
| `GET /compliance/export/markdown` | Download Markdown report |
| `GET /compliance/export/html` | Download HTML report |

## Compliance Score Calculation

Score = (COMPLIANT + 0.5 × PARTIAL) / (total − NA − WAIVED) × 100

- COMPLIANT items: full credit
- PARTIAL items: half credit
- PLANNED items: no credit
- NA / WAIVED items: excluded from denominator

CI gate threshold: **70%** overall score.

## Requirement ID Format

```
REQ-{AREA}-{NNN}
```

Where AREA is:
- `IA` — Information Assurance
- `SA` — Safety (Software)
- `QA` — Quality Assurance
- `CM` — Configuration Management
- `SU` — Supportability
- `SD` — Software Development
- `TD` — Technical Documentation

## Status Values

| Status | Meaning |
|--------|---------|
| COMPLIANT | Requirement fully met with verifiable evidence |
| PARTIAL | Requirement partially met; known gaps documented |
| PLANNED | Requirement not yet met; implementation planned |
| WAIVED | Formally waived with compensating controls |
| NA | Not applicable to this platform/context |

## Review Cycle

This register is reviewed **quarterly** or upon:
- Major architecture changes
- New service deployments
- Security incidents
- Regulatory changes

Last reviewed: 2026-06-06
Next review due: 2026-09-06
Owner: Trancendos Platform Engineering
