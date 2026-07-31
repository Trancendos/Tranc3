# Error, Vulnerability, Remediation & Self-Healing Matrix

> **What this is.** Five items from the matrix brainstorm — Error Code Registry, CVE Matrix,
> Remediation Matrix, Self-Healing Matrix, and Diagnosis/Resolution Matrix — turned out to describe
> one conceptual pipeline once traced through the codebase, not five unrelated systems: an error
> surfaces with a canonical code, gets scanned/classified against known vulnerability patterns,
> triggers an automated remediation bot or auditor fix, and self-healing regenerates the failed
> component. Each stage is real, independently-running code — but as §6 makes explicit, nothing
> currently connects the stages into one traceable, end-to-end flow. This doc maps the shared
> pipeline concept to the real code behind each independent stage, not a built, wired-together
> pipeline.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Error Code Registry

`src/errors/error_catalog.py`'s `ErrorCode` enum is the platform's canonical error taxonomy —
already referenced across the compliance layer (`docs/governance/CODE-COMPLIANCE-MATRIX.md`) and
exercised in `tests/test_compliance.py`. Every structured error raised by the FastAPI backend and
its routers is expected to map to one of these codes rather than an ad hoc string, giving The
Observatory (`src/observability/`) a consistent taxonomy to aggregate on.

## 2. Diagnosis (causal reasoning)

`src/intelligence/causal_reasoner.py` — a rule-based causal inference engine, explicitly scoped to
**understanding cause-and-effect between nanoservice events**, distinct from `causal_bus.py`'s
vector-clock-ordered message delivery (a transport concern, not a reasoning one). This is the real
code behind "Diagnosis Matrix": given a failure signal, it reasons about what upstream condition
likely caused it, rather than just logging the symptom.

## 3. CVE / Vulnerability tracking

- `src/platform/intelligent_scanner.py` and `zero_cost_service_map.py` — platform-side vulnerability
  surface tracking.
- `.forgejo/workflows/security-scan.yml` (pip-audit, bandit, ruff, npm audit, Semgrep, gitleaks —
  **not** Safety, deliberately removed per the workflow's own comment: "no longer free for
  commercial use") and `dependency-audit.yml` (weekly + on-PR dependency scanning) — the actual
  CI-enforced CVE detection layer, already documented in `CLAUDE.md`'s CI/CD section.

**Correction:** an earlier version of this doc claimed no SBOM is generated anywhere in this
pipeline — wrong. `security-scan.yml` already runs a real SBOM pipeline more complete than the
BOM/supply-chain research this session separately produced: `cyclonedx-py` for Python and `npm sbom`
for JS/TS per-language, plus a dedicated `sbom-generation` job running **syft** (CycloneDX JSON +
SPDX JSON) and **grype** (vulnerability matching against that SBOM), with results optionally
uploaded to a self-hosted **Dependency-Track** instance (`DTRACK_API_KEY`). The self-hosted-BOM
recommendation from this session's chat history is already built, not a future step.

## 4. Remediation

Two real, independent remediation layers exist:

- **`src/healing/nanocode_bots.py`** — a `NanoCodeBotDispatcher` routing five specific
  `FailureMode`s (compliance-metadata drift, stale embeddings, free-tier exhaustion, rate-limiting,
  service-unreachable) to dedicated `NanoBot` subclasses (`ComplianceMetadataBot`,
  `StaleEmbeddingBot`, `FreeTierBot`, `RateLimitBot`, `ServiceUnreachableBot`), each implementing
  its own automated repair action, with full execution history retained for observability.
- **`src/audit/automated_auditor.py`** — a scheduled `AutomatedAuditor` that validates compliance
  register evidence paths, runs Magna Carta rule validators, performs security posture checks, and
  **auto-remediates simple issues** (backup triggers, secret rotation triggers), writing results to
  `compliance/audit_results.yaml`.

These are deliberately separate: the NanoCode bots repair *runtime* failures (a service degrading
right now); the Automated Auditor repairs *compliance drift* (a posture check failing on schedule).

## 5. Self-Healing

`src/observability/self_healer.py`'s `SelfHealer` — explicitly framed as the platform's "immune
system": polls configured services as `CellState`s (name, url, healthy, consecutive_failures),
classifies each as `degraded` (≥2 consecutive failures) or `critical` (≥5), and calls any registered
`on_recovery_needed` hooks when a cell degrades. Zero external dependencies — stdlib + httpx only,
matching the platform's zero-cost posture.

**Correction:** an earlier version of this doc overstated what this actually does — the module
itself only logs (WARNING on degraded, CRITICAL on critical) and invokes whatever hooks are
registered; it does not itself perform a cooldown reset or emit an alert. `api.py`'s startup
(`get_healer()` → `run_forever()`) wires the monitor into the running app and it does poll P0/P1
cells for real, but **no `on_recovery_needed` hook is registered anywhere in this repo** — grepping
the whole tree finds zero calls to `on_recovery_needed`. Today this is a real, live degradation
*monitor* (logging + a `recovery_actions_taken` counter), not yet a self-*healer* in the sense of
taking automated corrective action — registering a real hook (e.g., triggering a worker restart) is
the natural next step, not built today.

`src/adaptive/cell_automaton.py` extends the same "cell" metaphor with adaptive, rule-based
regeneration logic — worth a closer look together with `self_healer.py` if this system is extended
further, since both currently use the cell/regeneration framing independently.

## 6. The pipeline, end to end

```text
Error raised (ErrorCode) → CVE/vulnerability scan (CI + intelligent_scanner.py) →
  causal_reasoner.py diagnoses root cause → NanoCodeBotDispatcher or AutomatedAuditor remediates →
  SelfHealer / cell_automaton.py confirms recovery, closes the loop
```

No single module currently owns this end-to-end flow — each stage is real and independently
tested, but nothing wires diagnosis → remediation → healing into one traceable request/incident ID
today. That wiring (not new capability, just connective tissue) is the natural next step if this
pipeline is prioritized further.

## 7. Cross-references

- `docs/governance/CODE-COMPLIANCE-MATRIX.md` — Layer 0/1 CI enforcement this pipeline's CVE
  scanning belongs to.
- `docs/governance/HARD-STOP-MATRIX.md` — the circuit breakers this pipeline's remediation bots
  interact with (a `ServiceUnreachableBot` repair and a circuit breaker's OPEN state are related
  but distinct: one repairs, the other protects).
