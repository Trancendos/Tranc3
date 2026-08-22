---
title: "BOM Matrix — Bills of Materials Across the Platform"
category: Reference
last-reviewed: 2026-08-19
status: needs-update
---

# BOM Matrix — Bills of Materials Across the Platform

> **What this is.** A follow-up brainstorm asked whether the "BOM-ification" trend (SBOM, CBOM,
> AI-BOM, HBOM, SaaSBOM, and ~15 other acronyms circulating in supply-chain-security discourse)
> maps onto anything real in this platform, and whether a Cosign/Conftest/Dependency-Track-style
> pipeline overhaul is worth building. This doc triages that request the same way
> [MATRIX-INDEX.md](MATRIX-INDEX.md) triaged the ~35-item matrix brainstorm: check each concept
> against real code and real infrastructure, build only where there's genuine signal, and record
> the rest as an honest "not applicable here" rather than padding for its own sake.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-31

---

## 1. What already exists, and is good

`.forgejo/workflows/security-scan.yml`'s `sbom-generation` job already runs a real SBOM pipeline,
already described in [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §3:

- **syft** generates both CycloneDX JSON and SPDX JSON from the repo tree (`sbom-cyclonedx.json`,
  `sbom-spdx.json`) — dual-format, matching the two standards the wider BOM ecosystem actually
  converges on.
- **grype** matches the CycloneDX SBOM against a vulnerability database.
- **Dependency-Track** upload is wired in (conditional on `DTRACK_API_KEY`/`DTRACK_URL` being set),
  auto-creating a project keyed by `git describe`.
- `cyclonedx-py` separately generates a Python-specific SBOM in the `python-security` job.

This is already equivalent to (and in the dual-format sense, slightly ahead of) the
Syft+Grype+Dependency-Track pipeline researched in this brainstorm. No pipeline rebuild is needed
for core SBOM.

## 2. The Grype gate now actually gates (fixed)

`security-scan.yml`'s `Run grype against SBOM` step passes `--fail-on high` — which should make the
job fail when Grype finds a HIGH or CRITICAL vulnerability — but the step used to wrap that command
in:

```bash
grype sbom:logs/sbom-cyclonedx.json ... --fail-on high 2>&1 | tee logs/grype-console.txt || {
  echo "::warning::Grype found HIGH/CRITICAL vulnerabilities — review logs/grype-results.json"
  exit 0
}
```

The `|| { ...; exit 0; }` caught Grype's non-zero exit (which `--fail-on high` is supposed to
produce) and explicitly replaced it with success, and the step also carried `continue-on-error:
true` on top of that. The net effect: **Grype's findings were recorded in the uploaded artifact,
but could never fail the pipeline, regardless of severity.** This was the same class of bug as the
`|| true` CI bypass fixed earlier in this platform's history (5 Whys #4) — a real gate that reads
as enforcing but silently doesn't.

**Backlog triaged, then the gate flipped for real.** Rather than flip the swallow blind, a real
`pip-audit` + a from-source `grype dir:.` scan were run against this repo to find out what was
actually in the backlog before touching the gate:

- **react-router-dom** 7.17.0 → 7.18.2 (fixed a real DoS CVE) — also fixed the `web/package-lock.json`
  drift that meant this dependency tree wasn't even the one real CI's `npm ci` installed.
- **brace-expansion**, **postcss**, **dompurify**, **valibot** — bumped to patched versions via
  `overrides` in both `web/package.json` (npm, the tree CI's `frontend-build.yml` actually installs)
  and the `pnpm` block (local dev).
- Root `package.json`'s `overrides` block gained a `postcss` pin for the same HIGH finding in the
  separate root Node project.
- Three findings remain and are **suppressed via `.grype.yaml`**, each with an inline justification
  (not just silenced — a per-finding VEX-style record, matching the ask in §3's VEX row below):
  - `GHSA-qwww-vcr4-c8h2` (react-router RSC-mode CSRF bypass) — fix needs a major-version bump to
    8.3.0; not exploitable here since `web/` has zero React Server Components usage.
  - `CVE-2024-23342` (ecdsa Minerva timing attack) — no upstream fix exists; not exploitable here
    since JWT signing is hardcoded to HS256 (`src/auth/facade.py`), never touching ecdsa's ECDSA path.
  - `GHSA-w8v5-vhqr-4h9v` (diskcache unsafe pickle deserialization) — no upstream fix exists;
    already mitigated in code (`_NoPickleJSONDisk`) and tracked in `.trivyignore`.

With the backlog clean, the workflow step now runs `grype ... --config .grype.yaml --fail-on high`
with **no swallow and no `continue-on-error`** — a genuinely new HIGH/CRITICAL finding fails the
job, and a missing SBOM is now also a hard failure instead of silently skipping the check.

## 3. BOM taxonomy triage against this platform

| BOM type | Status here | Reasoning |
|---|---|---|
| **SBOM** | Exists + documented | §1 above — syft (CycloneDX+SPDX) + grype + cyclonedx-py + Dependency-Track |
| **VEX** | Exists, minimal form | `.grype.yaml` (repo root) now carries a per-finding VEX-style record for each suppressed vulnerability — id, affected package, and a "not exploitable here / no fix exists" justification — rather than a full standalone VEX document format. See §2 |
| **CBOM** (cryptography) | Exists, differently named | Magna Carta's `ENCRYPTION-MATRIX.md` (MC-014) already catalogs the platform's real cryptographic assets (AES-GCM vault, argon2id/bcrypt password hashing, JWT signing) — the substance of a CBOM already exists as a compliance doc, not worth duplicating under a new acronym |
| **SaaSBOM** (external service dependencies) | Exists, differently named | `docs/ZERO_COST_VENDOR_MATRIX.md` already documents the AI Gateway's external dependency chain (Ollama, HuggingFace Inference, OpenRouter free tier, Fly.io) with the same intent a SaaSBOM would serve — again, don't duplicate under a new name |
| **OBOM** (operational/runtime) | Exists, differently named | `CLAUDE.md`'s Production Infrastructure Stack table + `docker-compose.production.yml` already function as this platform's OBOM |
| **PBOM** (pipeline/build tooling) | Exists, thin | `.forgejo/workflows/` itself is the record of build tooling; no separate manifest exists cataloging runner versions/linters/compilers as data, but the CI-as-code already serves that purpose for a platform this size |
| **AI-BOM / ML-BOM** | **Built 2026-08-19 — see [AI-BOM.md](AI-BOM.md)** | `src/core/tranc3_inference.py` runs in **bootstrap mode** (no trained weights, no dataset, tries Ollama → OpenRouter → stub). An AI-BOM cataloging training data provenance, hyperparameters, and foundational-model lineage would describe a model that doesn't exist yet. Building this now would be speculative padding, the same judgment already applied to Data Registry/Data Share Framework/Solutions Matrix in `MATRIX-INDEX.md` §4 — revisit once `Luminous`/`Tranc3Engine` actually trains or fine-tunes something. **Superseded in part, 2026-08-19.** That reasoning was right about models we *train* and answered a narrower question than the one that mattered: it said nothing about models we *consume*. The platform consumes 16 model references across 6 families and 2 hosted providers, each with a licence, an origin and an execution location — questions that arise whether or not anyone fine-tunes anything. [AI-BOM.md](AI-BOM.md) closes that half; training-lineage AI-BOM remains premature. The consumption inventory immediately found one thing worth knowing: the Llama family, the estate's most-used models, carry Meta's Community Licence rather than an OSI-approved open source licence, with an unmet "Built with Llama" attribution obligation |
| **HBOM** (hardware) | **Genuine gap — not applicable** | The platform runs on rented Fly.io compute and Cloudflare Workers; no owned hardware exists to catalog. Only becomes relevant if the "founder's local server" mentioned in `CLAUDE.md`'s Zero-Cost Self-Hosted Architecture section is ever funded and brought online |
| **F-BOM / FBOM** (firmware) | **Genuine gap — not applicable** | No embedded/IoT/OT devices exist on this platform |
| **QBOM** (quantum-readiness) | **Genuine gap — not applicable today** | No quantum computing work exists outside `src/quantum/`'s Think Tank *research* (qiskit-based simulation), which is not the same as production cryptography needing post-quantum migration tracking. Worth a one-line mention in a future `ENCRYPTION-MATRIX.md` revision, not a standalone doc |
| **KBOM** (Kubernetes) | Not applicable | This platform is explicitly Docker Compose + Traefik, not Kubernetes (`docker-compose.production.yml`, `CLAUDE.md` Architecture section) — a KBOM has no cluster to describe |
| **FinBOM / cost tracking** | Exists, differently named | `docs/ZERO_COST_VENDOR_MATRIX.md` and the `COST-AND-REVENUE-GOVERNANCE.md` addendum already cover the "which service costs what, who owns it" question a FinBOM would answer |
| **ZT-BOM / identity BOM** | Exists, differently named | [PERMISSIONS-ACCESS-MATRIX.md](PERMISSIONS-ACCESS-MATRIX.md) already documents the Role Registry, Access Registry, and Zero Trust IAM as the platform's identity/permission graph |
| **XBOM (unified/everything BOM)** | Not a real standard, not built | No standards body maintains an "XBOM spec" — it's an architectural pattern (multiple CycloneDX-family BOMs correlated in one store), not a document type. This Matrix Index / BOM Matrix pairing already functions as this platform's version of that correlation, without inventing a new schema |

## 4. On the researched CI pipeline (Cosign, Conftest/OPA, generic multi-platform YAML)

Three pieces of the pasted research don't map cleanly onto this platform today, and building them
speculatively would duplicate or contradict what's already decided:

- **Cosign artifact signing** — has no attachment point. Neither `deploy-fly.yml` nor
  `deploy-cloudflare.yml` pushes a container image to a registry Cosign could sign; `fly deploy`
  builds and deploys directly. Signing would only make sense once/if a registry step is introduced.
- **Conftest/OPA policy gating** — this platform's existing gates (bandit's medium+ severity gate,
  ruff's lint gate, and Grype's *intended* fail-on-high gate once §2 is fixed) are all plain
  bash/CLI checks. Introducing a full Rego/OPA policy engine for 2–3 threshold checks is more
  machinery than the actual policy surface justifies, and cuts against the platform's stated
  zero-cost/minimal-dependency posture.
- **A platform-agnostic Jenkins/Azure DevOps/CircleCI pipeline** — this platform's actual CI is
  Forgejo (primary) + GitHub Actions (narrow, PR-gating checks) per `CLAUDE.md`'s CI/CD section.
  Building a third, generic pipeline for CI systems this platform doesn't run would be dead
  configuration from day one.

None of these are ruled out forever — they're ruled out *for this platform, today*, for the
specific reasons above, not dismissed as bad ideas in general.

## 5. Cross-references

- [ERROR-REMEDIATION-MATRIX.md](ERROR-REMEDIATION-MATRIX.md) §3 — the real SBOM/CVE pipeline this
  doc builds on rather than duplicates.
- [MATRIX-INDEX.md](MATRIX-INDEX.md) — the master triage this doc follows the same method as.
- `docs/ZERO_COST_VENDOR_MATRIX.md` — the SaaSBOM/FinBOM-equivalent vendor dependency chain.
- [PERMISSIONS-ACCESS-MATRIX.md](PERMISSIONS-ACCESS-MATRIX.md) — the ZT-BOM-equivalent identity
  graph.
- Magna Carta's `ENCRYPTION-MATRIX.md` (MC-014) — the CBOM-equivalent cryptographic asset inventory.
