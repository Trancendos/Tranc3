# Forensic Assessment — Creative Delivery, Governance and The Lab

**Scope.** The path a request takes from words to artefact: creative routing,
the Imaginarium fan-out, Fabulousa, The Lab, and the Town Hall gates that were
supposed to sit across all of it. Assessed 2026-09-04 against the repository at
`claude/cloud-only-production-ready-25usvd`.

**Method.** Every number below was read off code, Dockerfiles and
`docker-compose.production.yml` and is reproducible by the scripts named. Where
something could not be measured from this container it says so. Nothing here is
inferred from the entity table's intentions.

---

## 1. The finding that organises the rest

One defect shape accounts for most of what was wrong, in every subsystem
examined:

> **A control exists, runs, and reports — and does not act.**

It is not carelessness. Each instance passes review, passes tests, and produces
output that looks like success. That is precisely why it survives:

| Instance | Looked like | Actually did |
|---|---|---|
| PRINCE2 in `governance.py` | A registered policy scoring 0.92 | No `check` function, so `evaluate()` returns UNKNOWN, and UNKNOWN is neither FAIL nor WARN — `/townhall/check` reports PASS |
| `ALLOWED_LANGUAGES` in The Lab | A 12-language capability list | Referenced once, at its own definition. Nothing validated against it |
| Imaginarium's image leg | A fan-out call | Tested `status_code == 202` against a service answering 200, so the result was discarded with no error recorded |
| Imaginarium's project status | `completed` | Written unconditionally, including when every leg failed |
| Cargo.lock marker guard | A malformed-file check | Unreachable for every non-empty file. Its replacement was fail-open in a second way — see register item 19 |
| `.trivyignore` suppression | A governed acceptance | Silenced a CVE on a register entry dispositioned FIX |
| CI's Pytest job (until `f98aadb4`) | A test run | `-x` plus `\|\| true`: five tests, result ignored |

**Assessment.** The platform's controls are not under-built; they are
under-*wired*. The remediation pattern that works is not "add a control" but
"make the existing one refuse", then calibrate a test by mutating the thing it
protects and confirming the test fails.

---

## 2. Measured state

### 2.1 Creative routing — `src/creative/routing.py`

13 capabilities, verified against the module each worker's Dockerfile `CMD`
actually runs (`scripts/check_creative_routes.py`, 12 endpoints verified):

| Status | Count | Capabilities |
|---|---|---|
| ROUTED | 1 | `code.generate` |
| DEGRADED | 5 | `image.create`, `game.create`, `video.create`, `design.create`, `creative.brief` |
| ABSENT | 7 | `image.edit`, `image.upscale`, `game.asset.add`, `model3d.create`, `design.component`, `design.accessibility`, `music.create` |

**One capability in thirteen can deliver what its name promises.**

The dominant cause is not missing code. It is that several creative Locations
ship two FastAPI applications — a thin `main.py` and a much richer `worker.py`
— and the Dockerfile decides which runs. The rich one is frequently the one
nobody deployed:

| Location | Dockerfile runs | Where the real API lives |
|---|---|---|
| Imaginarium | `main.py` (92 lines, `/orchestrate` returns "not yet ready") | `worker.py` — **now deployed by this work** |
| TranceFlow | `main.py` → `router.py` (`/tranceflow/projects`) | `worker.py` (games, assets, scenes, entities) — not deployed |
| TateKing | `main.py` (541 lines, real FFmpeg) | `worker.py` (projects, clips) — not deployed |
| Warp Radio | `main.py` (54 lines, read-only) | `worker.py` (playlists, tracks) — not deployed |

The second cause is absent backends. ComfyUI, AUTOMATIC1111, Godot and the
`ffmpeg` binary are not services in `docker-compose.production.yml`, and the
workers' defaults named `localhost` — which inside a container is the worker
itself.

### 2.2 The Lab — `src/lab/languages.py`, `scripts/lab_capability_report.py`

29 languages declared. Verification tier measured from binaries the built image
demonstrably contains:

| | Before | After |
|---|---|---|
| Verifiable at all | 2 | 5 |
| At `test` tier | 0 | 1 (Python) |
| At `none` | 27 | 24 |

`/lab/run` answers 501 by design — AST import-blocking was never a sandbox, and
the code says so honestly. The consequence is that The Lab could generate code
in 29 languages and execute none of it. Five checkers were pip-installable and
are now in the image; node, go, `rustc` and `javac` are not, and belong in a
verification sidecar rather than in a 200MB code-assistant image.

`TABBY_URL` still defaults to `localhost:8080` with no Tabby service in compose,
so tier 1 of The Lab's "adaptive chain" is permanently dead and every request
falls through to Ollama. Low impact (connection refused is instant), but it
means the documented chain has three live tiers, not four.

### 2.3 Fabulousa

Four endpoints, all Penpot proxying. No design tokens, no components, no
widgets, no modules, no templates, no accessibility checking.

The design system **exists** — `web/src/trancendos/tokens.ts` (325 lines),
nine components under `web/src/components/ui/`, Storybook stories, hand-written
ARIA — but it lives in Arcadia's front-end, not in the Location whose job
description is styling, UX and UI.

**Zero automated accessibility verification anywhere.** Neither
`.github/workflows/` nor `.forgejo/workflows/` runs axe, pa11y or Lighthouse.
The ARIA attributes are written and unverified.

### 2.4 The Town Hall

Before this work: a policy registry with hardcoded scores, no lifecycle record,
no stages, no criteria, no evidence, no decision. A grep across `workers/` for
the Town Hall returns one health check and no callers. Nothing built anywhere
in the estate passed through it.

Now: 10 criteria across 7 stages, applied per deliverable kind across 8 kinds,
with `advance()` raising rather than warning. CranBania (the submodule holding
the real Kanban/PRINCE2 board) is not checked out in this environment and is
**not assessed**.

---

## 3. SWOT

### Strengths

- **The naming and identity spine is real and unusually disciplined.** 43
  entities, a CMDB identity resolver, per-Location ownership resolution that
  records "unresolved" rather than guessing. Most estates this size cannot
  answer "who answers for this service".
- **Honesty is already the house style in code.** Photo Studio's offline branch
  returns `"placeholder": true`. The Lab's `/lab/run` returns 501 with the real
  reason. `ServiceOwnership.resolved` is a field. This is rarer than it sounds
  and it is what made a forensic pass possible at all.
- **Guard scripts are cheap, fast and enforced.** 14 `check_*.py` gates run in
  `ci.yml`; each is seconds, not minutes, and each fails rather than warns.
- **Zero-cost posture is coherent**, not merely thrifty: self-hosted Penpot,
  Ollama, LiteLLM and Vault are all in compose and real.

### Weaknesses

- **Deployed ≠ written.** The `main.py`/`worker.py` split is an estate-wide
  hazard, not a creative-tier one. Verified for 8 creative workers; **unaudited
  for the other ~70.**
- **Capability claims outrun capability.** 1 of 13 creative capabilities and 5
  of 29 Lab languages can do what their names say.
- **Verification is the systematic gap.** Generation exists everywhere;
  checking exists almost nowhere. No a11y gate, no code execution, no build.
- **Documentation drifts from code by default.** Fixed for the PLM (generated +
  drift-checked); untreated everywhere else.
- **Two submodules are unchecked out here**, so CranBania and Magna Carta
  cannot be assessed and any claim about them is unsupported.

### Opportunities

- **The gate is now a place to hang everything else.** Chaos Party, Cryptex,
  The Artifactory and The Library each already produce exactly the evidence one
  criterion asks for. Wiring them to file it automatically converts four
  existing services into an enforced lifecycle for free.
- **One verification sidecar** with node, go, rustc and javac would take The
  Lab from 5 verifiable languages to ~20 without touching its image.
- **Fabulousa serving `tokens.ts`** turns an existing, real design system into
  a platform capability, and makes `design.accessibility` implementable rather
  than aspirational.
- **`check_creative_routes.py` generalises.** The same parser, run over all
  ~80 workers, would find every other place the deployed entrypoint and the
  documented API disagree.

### Threats

- **A green board that means nothing is worse than a red one.** Every defect in
  §1 reported success. The controls added here are only worth what their
  calibration is worth — a test that passes under mutation is a new instance of
  the same disease, and two of mine were, and were rewritten.
- **Funding gates the honest fix for the DEGRADED tier.** Godot, ffmpeg,
  ComfyUI and a Lab sidecar all need the local server. No amount of code
  closes that.
- **Reviewer fatigue.** This assessment is possible because bots reviewed every
  commit. Three of their findings were real bugs, one of which I had introduced
  and then defended from a stale checkout.

---

## 4. Remediation register

Ordered by value per unit of effort. "Done" entries are on this branch.

| # | Action | Status | Notes |
|---|---|---|---|
| 1 | Verify every creative endpoint against its Dockerfile `CMD` | **Done** | `scripts/check_creative_routes.py`, in `ci.yml` |
| 2 | Deploy Imaginarium's real orchestrator | **Done** | Dockerfile ships `worker.py`; volume added |
| 3 | Fan out to every Location that can serve a leg | **Done** | 5 legs; Warp Radio excluded with a written reason |
| 4 | Give the Town Hall gates that refuse | **Done** | `src/townhall/plm.py` |
| 5 | Route a request in words to a Location | **Done** | `src/creative/routing.py`, `/creative/resolve` |
| 6 | Make commissioning pass through the lifecycle | **Done** | `/creative/commission`, authenticated |
| 7 | Measure The Lab's real language capability | **Done** | `scripts/lab_capability_report.py` |
| 8 | Install the pip-installable share of The Lab's toolchain | **Done** | 2 → 5 verifiable |
| 9 | Make `ALLOWED_LANGUAGES` enforce | **Done** | + `scripts/check_lab_languages.py` |
| 10 | Point Fabulousa at the Penpot the platform runs | **Done** | `PENPOT_URL=http://penpot-frontend` |
| 11 | Issue `PENPOT_TOKEN` into The Void | **Needs owner** | Fabulousa is reachable but unauthenticated |
| 12 | Fabulousa serves `tokens.ts`, components and widgets | **Open** | Closes `design.component` |
| 13 | Accessibility validator + axe/pa11y in CI | **Open** | Closes `design.accessibility`; the only ABSENT capability with no infrastructure dependency |
| 14 | Chaos Party and Cryptex file PLM evidence automatically | **Open** | Converts existing services into gate enforcement |
| 15 | Run the entrypoint audit across all ~80 workers | **Open** | Same parser, wider scope |
| 16 | Lab verification sidecar (node/go/rustc/javac) | **Open** | 5 → ~20 verifiable languages |
| 17 | Deploy TranceFlow / TateKing / Warp Radio `worker.py` | **Open** | Each needs its own volume + review |
| 18 | Godot, ffmpeg, ComfyUI as services | **Funding-gated** | The DEGRADED tier cannot close without them |
| 19 | Make the Cargo.lock guard fail closed on a truncated file | **Done** | Row 31 of §1. A stanza-local `name`+`version` test; the substring form let the lockfile header's own `version = 3` complete a package cut off after its name |
| 20 | Fail when a guard exists and no workflow runs it | **Done** | `scripts/check_guards_are_wired.py`. Written because `check_lab_languages.py` (row 9) shipped unwired while its docstring said otherwise; it found two more on its first run |

---

## 5. What this assessment does not cover

- **CranBania and Magna Carta.** Both submodules are unchecked out in this
  environment. Any statement about the Town Hall's Kanban/PRINCE2 board or the
  compliance framework's runtime rules would be unsupported.
- **The other ~70 workers.** The `main.py`/`worker.py` audit covered the eight
  creative ones. Item 15 exists because the rest are unknown, not because they
  are fine.
- **Runtime behaviour.** Everything here is static: source, Dockerfiles,
  compose. No container was built or run.
