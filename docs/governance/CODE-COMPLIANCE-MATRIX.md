# Code Compliance Matrix

> **What this is.** Every mechanism below already exists and already runs — this document ties
> them together in one place. Before it, the pieces were split across `CLAUDE.md`'s "Pre-commit
> Hooks" section, its separate "CI/CD" section, `docs/defstan/README.md`, and
> `compliance/register.yaml`, with nothing showing how a local `ruff` failure relates to a DEFSTAN
> requirement or a Magna Carta rule. Nothing here is new enforcement; it's the missing map.

**Owner:** The Workshop (Larry Lowhammer) · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. The four layers, narrowest to broadest

```text
Layer 0: Local pre-commit (.pre-commit-config.yaml)     — runs before a commit exists
Layer 1: CI gates (.github/workflows/, .forgejo/workflows/) — runs on push/PR
Layer 2: DEFSTAN framework (docs/defstan/, compliance/register.yaml) — quality benchmark, 7 mapped standards
Layer 3: Magna Carta (compliance/magna-carta/compliance/magna_carta_register.yaml) — 9 runtime rules, submodule-governed
```

This mirrors `docs/compliance/COMPLIANCE-BLUEPRINT.md`'s own 4-layer model for regulatory
frameworks — this document is the code-quality-specific analogue, not a competing hierarchy.

## 2. Layer 0 — pre-commit (`.pre-commit-config.yaml`)

| Tool | Version | Scope |
|---|---|---|
| ruff (lint + format) | v0.15.8 | `--fix --exit-non-zero-on-fix`, plus `ruff-format` |
| pre-commit-hooks | v5.0.0 | trailing-whitespace, end-of-file-fixer, check-yaml/json/toml, check-merge-conflict, detect-private-key, check-added-large-files (500KB), no-commit-to-branch (`main`), check-ast, debug-statements |
| bandit | 1.9.4 | `-r src` Python SAST, config in `pyproject.toml` |
| black | 25.1.0 | Python formatting |
| isort | 5.13.2 | Import sorting |
| semgrep | v1.63.0 | `--config auto --error`, multi-language SAST |
| gitleaks, detect-secrets, safety, typos | — | secret detection + dependency vulnerability + typo checks (per `CLAUDE.md`'s Pre-commit Hooks list) |

`pyproject.toml`'s `[tool.ruff]`: `line-length = 100`, `target-version = "py311"`, lint selects
`["E", "F", "W", "C", "B", "I"]`, ignores `E501` (formatter's job), `B008` (FastAPI `Depends`
pattern), `C901` (complexity — warned, not blocked). Per-file overrides: `tests/*` allows
`S`/`B`/`C408`/`C416`, `scripts/*` allows `print()` (`T201`), `api.py` allows `E402`/`B904`.

`[tool.mypy]` exists in `pyproject.toml`; `make lint` runs `mypy src/ api.py
--ignore-missing-imports` — type checking is present but not currently a pre-commit hook (only a
`make lint` / presumably-CI step, see §3).

## 3. Layer 1 — CI (two systems, deliberately, see `CLAUDE.md`'s CI/CD section)

- **GitHub Actions** (`.github/workflows/`, 19 files): `ci.yml` (Ruff/lint, Service Topology and
  Pytest-with-coverage — the PR-blocking gate),
  `codeql.yml`, `test.yml`, `trivy.yml`, `python.yml`, `rust.yml`, `go.yml`,
  `publish-wiki.yml`, `publish-matrix-site.yml`, plus `deploy-cloudflare.yml`/`deploy-fly.yml`
  (legacy deploy paths).
- **Forgejo** (`.forgejo/workflows/`, 30 files) — the primary system for deployment and heavier
  pipelines: `production-gate.yml` (the 16-file pytest merge gate, see
  `docs/governance/TRANCENDOS-MODELS-MATRIX.md`'s test-coverage notes), `compliance-gate.yml`,
  `security-scan.yml`, `security-baseline.yml`, `dependency-audit.yml`, `dependency-scanner.yml`,
  `proactive-security.yml`, `proactive-health.yml`, `citadel-preflight.yml`,
  `branch-integration-audit.yml`, `pr-readiness-audit.yml`, `fork-audit.yml`,
  `stale-branch-cleanup.yml`, `renovate.yml`, `nightly.yml`, `e2e-playwright.yml`,
  `frontend-build.yml`, `infrastructure.yml`, `registry-push.yml`,
  `sync-cranbania-submodule.yml`, `adaptive-ci.yml`, `benchmark-eval.yml`,
  `integration-scope-plan.yml`, `phase7-nanoservices.yml`, `phase8-trancex.yml`,
  `audit-key-check.yml`, plus the deploy workflows.

30 Forgejo workflow files is a wide surface this document doesn't re-describe individually — see
each file's own header comment; this section exists so a reader knows the split is deliberate
(GitHub for PR-facing checks GitHub itself needs, Forgejo for everything else) rather than drift.

## 4. Layer 2 — DEFSTAN (`docs/defstan/README.md`)

Applies UK DEF STAN discipline as a **voluntary quality benchmark**, not a regulatory requirement,
to a public civilian platform. Seven standards mapped: 00-700 (Information Assurance, full),
00-055 (Safety-Related Software, adapted for AI safety/fail-safe design), 00-056 (Software
Development, full), 00-600 (Supportability/ILS, adapted for observability), 00-044 (Configuration
Management, full), 05-086 (Quality Assurance, full — this is where Layers 0-1 above are the actual
QA evidence), 05-057 (Technical Documentation, adapted). `compliance/register.yaml`
(`src/compliance/checker.py`'s `REGISTER_PATH`) is this layer's own DEFSTAN register — distinct
from Layer 3's Magna Carta register below. `scripts/run_compliance_mc.py` (see `Makefile`'s
`compliance-mc` target) generates a **merged** report: `load_and_check_merged()` checks the DEFSTAN
register above and, optionally, the Magna Carta register (`mc_register_path`) together — it is not
a DEFSTAN-only report despite the script's name.

## 5. Layer 3 — Magna Carta (`compliance/magna-carta/compliance/magna_carta_register.yaml`, `compliance/magna-carta/` submodule)

9 runtime rules enforced via `src/compliance/middleware.py` — see
`docs/governance/TRANCENDOS-MODELS-MATRIX.md` §10 for how MC-013 specifically gates model
advancement, and `docs/governance/ESTATE-PROTECTION-MATRICES.md` for the license/IP/encryption/
security matrices (MC-012/013/014/015) this repo mirrors from the separate Magna-Carta repository.

## 6. Cross-references

- `docs/compliance/COMPLIANCE-BLUEPRINT.md` — the regulatory-framework analogue to this doc's
  code-quality focus
- `docs/defstan/README.md`, `docs/defstan/COMPLIANCE_REGISTER.md` — Layer 2 in full
- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` — Layer 3's MC-013 gate in the one place it
  actually blocks something (model advancement proposals)
