# Python 3.11 → 3.14 Upgrade Feasibility Assessment

**Type:** Research/assessment only. No code, Dockerfile, CI, or dependency file in this repo was
changed to produce this document.

**Date:** 2026-08-07

**Prepared for:** Governance record of the platform-wide Python version decision (this repo also
carries a working document at `docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md`, dated
2026-08-01 — see **§0** below for how the two relate; this file independently re-verifies the
same ground rather than copying that one's conclusions).

---

## 0. Relationship to the existing `docs/architecture/` assessment

A prior assessment already exists at `docs/architecture/PYTHON-3.14-UPGRADE-ASSESSMENT.md`
(dated 2026-08-01, six days before this one). It records that a Stage 1 change already landed:
`.github/workflows/python.yml`'s `test` job matrix gained a `python-version: '3.14'` entry with
`experimental: true` / `continue-on-error: true`, scoped to `aeonmind/python/**` only. This
investigation independently confirmed that change is present in the file today (§3 below) and
largely corroborates that document's inventory (Dockerfile counts, CI pin counts, dependency risk
list). Two things this assessment adds that the architecture-path one does not appear to have
checked:

1. A **concrete, verified build breakage** in one of the dependabot branches themselves — the
   `docker/Dockerfile.api` bump leaves a hardcoded `python3.11` path stale (§5.1). This is a
   specific instance of exactly the "runtime/build mismatch" risk the architecture doc discusses
   only in the abstract.
2. A **live baseline test run** on this sandbox's actual Python 3.11.15 interpreter with the
   pinned `requirements.txt` versions actually installed (§4), rather than reasoning from the
   pins alone.

This document does not supersede the architecture-path one; the two should be reconciled (or one
retired) by whoever owns the actual upgrade decision — that reconciliation is out of scope for
either assessment.

---

## 1. Current pin locations (inventory)

| Surface | Value found | File / evidence |
|---|---|---|
| Root package | `requires-python = ">=3.11"` | `pyproject.toml:8` |
| `tranc3-bots` | `requires-python = ">=3.11"` | `tranc3-bots/pyproject.toml:9` |
| `aeonmind/python` | `requires-python = ">=3.10"` — **lower floor than root** | `aeonmind/python/pyproject.toml:11` |
| `rust_extensions/tranc3_crypto` | `requires-python = ">=3.10"` — **lower floor than root** | `rust_extensions/tranc3_crypto/pyproject.toml:9` |
| Ruff | `target-version = "py311"` | `pyproject.toml:14` |
| mypy | `python_version = "3.11"` | `pyproject.toml:56` |
| `setup.py` / `setup.cfg` / `runtime.txt` / `.python-version` | None exist anywhere in the repo | confirmed via `find` |
| Interpreter actually running in this sandbox | Python 3.11.15 | `python --version` |

**Verdict: the floor is already inconsistent before 3.14 enters the picture.** Root and
`tranc3-bots` sit on `>=3.11`; `aeonmind/python` and `rust_extensions/tranc3_crypto` sit on
`>=3.10`. Any 3.14 work should reconcile this first (or explicitly accept the inconsistency),
since layering a new ceiling on top of two different floors compounds the ambiguity.

### Dockerfile base images

```
Root Dockerfile              FROM python:3.11-slim@sha256:e031123e...
docker/Dockerfile.api        FROM python:3.11-slim@sha256:e031123e...  (both builder + runtime stages)
docker/Dockerfile            FROM python:3.11-slim-bookworm@sha256:f5cf0344...
docker/Dockerfile.worker     FROM python:3.11-slim@sha256:e031123e...
tranc3-bots/Dockerfile       FROM python:3.11-slim@sha256:e031123e...
```

Across the 92 directories under `workers/`, 84 have a Python-based Dockerfile (`FROM python:...`).
Of those 84:

- **74** are on `python:3.11-slim` (one shared pinned digest,
  `sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3`)
- **9** are already on `python:3.12-slim` (`fabulousa-service`, `observatory`, `tranceflow`,
  `library-service`, `artifactory-service`, `litellm-service`, `lab-service`, `cryptex`, `vrar3d`)
- **1** (`ffmpeg-worker`) is on `python:3.12-slim-bookworm`

The other 8 non-Python worker directories are Rust (`nexus-ws-rs`, `vault-service-rs`,
`rate-limit-service-rs`), Go (`monitoring-go`), or Node (`bullmq-queue-service`,
`remotion-render-service`, `cranbania`) and are out of scope for a *Python* version upgrade.

**Verdict: worker base images are already a three-way split (3.11 / 3.12 / 3.12-bookworm)**, all
pinned by digest, not just tag, so any bump — to 3.12, 3.13, or 3.14 — requires resolving a new
digest per Dockerfile, not a mechanical tag edit.

### CI `python-version` matrix entries

```
.github/workflows/*.yml     : 8 files hardcode "3.11" (test.yml, ci.yml, codecov.yml,
                               production-gate.yml, publish-matrix-site.yml, rust.yml,
                               submodule-pins.yml, and python.yml's lint/install-check jobs)
.github/workflows/python.yml: test job matrix = ['3.10','3.11','3.12'], PLUS a '3.14' entry
                               with experimental:true / continue-on-error:true (already landed,
                               see §3) — scoped to aeonmind/python/** only, not the main backend
.forgejo/workflows/*.yml    : 16 of 30 files hardcode python-version: "3.11" (adaptive-ci.yml x4,
                               audit-key-check.yml, benchmark-eval.yml x4, ci.yml x3,
                               citadel-preflight.yml, compliance-gate.yml, dependency-audit.yml x4,
                               dependency-scanner.yml x4, deploy-self-hosted.yml, e2e-playwright.yml,
                               nightly.yml, phase7-nanoservices.yml x3, phase8-trancex.yml x3,
                               proactive-health.yml, proactive-security.yml x2, production-gate.yml)
compliance/magna-carta       : both .github/workflows/layer-b-ci.yml and
  (submodule)                  .forgejo/workflows/layer-b-ci.yml hardcode python-version: "3.11"
```

No Forgejo workflow anywhere runs a Python-version matrix (`registry-push.yml` has a
`strategy.matrix`, but for multi-image Docker builds, not Python versions).

**Verdict: before this investigation, nothing in CI had ever actually executed on 3.13 or 3.14.**
The one 3.14 matrix entry that exists today (`python.yml`) is additive, non-blocking, and scoped
to a 93-file sub-package (`aeonmind/python/`), not the FastAPI backend, the 84 Python workers, or
`tranc3-bots`.

---

## 2. Dependency compatibility risk

Root `requirements.txt` / `requirements-ai.txt` (installed and verified against in this sandbox —
see §4) carry the packages most likely to be version-sensitive. Actual installed versions in this
Python 3.11.15 sandbox, confirmed by `import` + `__version__`:

| Package | Pinned / installed version | Risk on 3.14 |
|---|---|---|
| `numpy` | 2.1.3 | **Likely** — NumPy has shipped 3.13/3.14 wheels within weeks of each CPython GA in recent cycles; 2.1.3 is itself over a year old by the time 3.14 GA'd, so the *currently pinned* version may predate 3.14 wheel availability even if newer 2.x releases have it. Needs a real `pip install numpy==2.1.3` against a 3.14 interpreter to confirm — not assumed here. |
| `torch` | 2.13.0+cu130 | **Uncertain** — PyTorch has historically lagged new CPython minors by a release cycle or two (e.g. 3.12 support arrived several torch minors after 3.12 GA). 2.13.0 is a recent release, but whether *this exact pin* has a 3.14 wheel is a fact to verify against the real PyPI/download.pytorch.org index, not to assume. |
| `pydantic` / `pydantic-core` | 2.13.4 / 2.46.4 | **Likely** — Rust-via-maturin build, historically fast wheel turnaround (pydantic-core has shipped new-Python-version wheels within the GA week in past cycles). |
| `cryptography` | 48.0.1 | **Likely** — actively maintained, manylinux wheels typically land quickly; still worth confirming the specific pin. |
| `psycopg2-binary` | 2.9.12 | **Uncertain** — psycopg2-binary wheel releases have occasionally lagged; the project itself recommends `psycopg` (v3) for new work partly for this reason. Worth checking explicitly. |
| `sentencepiece` | 0.2.1 | **Uncertain** — C++ extension, has had gaps between new CPython GA and wheel availability in past cycles. |
| `qiskit` | 2.4.1 (pure Python) | **Likely** — pure-Python package, no C-extension wheel to lag. |
| `qiskit-aer` | 0.17.2 | **Genuine risk, flagged in the existing `docs/architecture/` doc too** — this is a C++ extension (used by Think Tank / `src/quantum/`) and has historically had a slower wheel cadence than the `qiskit` package it pairs with. This is the single dependency in the estate most likely to still be missing a 3.14 wheel or need a source build. |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.42.1 (root); `>=1.24.0` floating in `workers/library-service/requirements.txt` | **Uncertain** — depends transitively on `grpcio`, whose C-extension has occasionally lagged new CPython releases. The floating `>=` pin in `library-service` also means the exact resolved version isn't controlled today, compounding the uncertainty. |
| `grpcio` | 1.83.0 (as resolved in this sandbox) | Same caveat as above — verify directly. |

**No worker under `workers/*/requirements*.txt` pulls `torch`, `numpy`, `qiskit`, `grpcio`
(directly), `sentencepiece`, `faiss`, or `tensorflow`** — confirmed by grep across all 92 worker
requirements files. These heavy/native-extension dependencies are confined to the root
application (`requirements.txt`, `requirements-ai.txt` — Luminous/`src/bio_neural/`, Think
Tank/`src/quantum/`, `src/training/`, `src/deepmind/`). This materially narrows the blast radius:
**a worker-by-worker rollout does not inherit the root app's heaviest dependency risk**, because
the workers mostly carry only `fastapi`/`starlette`/`uvicorn`/`httpx`/`pydantic` (all in the
"likely" column above).

**Explicit uncertainty statement, per the task brief:** this environment has no live PyPI access,
so every "likely / uncertain / likely not" judgment above is reasoned from each project's
historical wheel-release cadence around prior CPython GAs (3.12, 3.13), not from checking the
actual 3.14 wheel index today. **Before committing to any 3.14 timeline, someone with PyPI access
must run `pip install --dry-run` (or a real install) for each pinned version above against a 3.14
interpreter and record which ones resolve to a wheel vs. fall back to `sdist` + local compile.**
That step has not been done here, by either this assessment or the existing `docs/architecture/`
one — both are reasoning from release-cadence history.

### Hygiene gaps found (not 3.14 blockers per se, but adjacent and worth fixing in the same effort)

- **Three workers ship zero dependency pins**: `workers/ffmpeg-worker/requirements.txt`
  (`fastapi`, `uvicorn`), `workers/triposr-worker/requirements.txt` (`fastapi`, `uvicorn`,
  `pillow`), `workers/blender-worker/requirements.txt` (`fastapi`, `uvicorn`) — all three
  literally just list bare package names with no version at all. On a fresh 3.14 build these
  resolve to whatever the latest wheel happens to be at build time, untested against anything —
  including against 3.11 today.
- **`workers/library-service/requirements.txt` uses floating `>=` pins throughout**
  (`fastapi>=0.111.0`, `pydantic>=2.7.0`, `opentelemetry-exporter-otlp-proto-grpc>=1.24.0`, etc.),
  unlike the majority of workers sampled (`analytics-service`, `cryptex`, `the-lab`,
  `sashas-photo-studio`, `tateking`, `tranc3-bots`), which are exact-pinned with an explicit
  `# Exact-pinned — Do NOT use >= or ~=` header. This means `library-service`'s actual resolved
  dependency set is not reproducible today, independent of the Python version question.

---

## 3. Known CPython 3.12–3.14 breaking changes — grepped against this codebase

| Change | Grep result | Verdict |
|---|---|---|
| `distutils` removed (3.12) | Zero hits for `import distutils` / `from distutils import` anywhere in `*.py` | **Clean** |
| `imp` module removed (3.12) | Zero hits for `import imp` / `from imp import` | **Clean** |
| PEP 594 "dead battery" stdlib modules removed (3.13): `cgi`, `cgitb`, `chunk`, `crypt`, `imghdr`, `mailcap`, `msilib`, `nis`, `nntplib`, `ossaudiodev`, `pipes`, `sndhdr`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`, `smtpd`, `asynchat`, `asyncore` | Zero hits | **Clean** |
| `ssl.wrap_socket` removed (3.12) | Zero hits | **Clean** |
| `typing.io`, `typing.re`, `typing.ByteString` removed/deprecated (3.13) | Zero hits | **Clean** |
| `unittest` deprecated aliases removed (3.12): `assertEquals`, `failUnless`, `failIf`, `assert_` | Zero hits | **Clean** |
| `collections.Callable`/`Mapping`/etc. imported from `collections` instead of `collections.abc` (hard error since 3.10, so already broken on 3.11 if present) | Zero hits | **Clean** |
| `inspect.getargspec` removed (3.11) | Zero hits | **Clean** |
| `pkgutil.ImpImporter` / `ImpImporter` remnants | Zero hits | **Clean** |
| `asyncio.get_event_loop()` implicit-loop-creation behavior — deprecated since 3.10, and calling it with **no running loop** already raises `RuntimeError` as of the 3.12+ deprecation path (confirmed by this codebase's own comments, see below) | **39 occurrences across 37 files** (see list below) | **Needs a review pass** — not a hard break today (each site still works when called from inside a running coroutine, which is where most of these live), but it's the one *forward-looking* asyncio risk actually present in this codebase, not a hypothetical one. |
| `datetime.utcnow()` / `datetime.utcfromtimestamp()` — deprecated since 3.12 (`DeprecationWarning`, not yet removed as of 3.13/3.14) | **19 files** (see list below) | **Hygiene item, not a blocker** — still functions on 3.14, but the deprecation warning has been live for three CPython releases and the pattern is trivially replaced with `datetime.now(datetime.UTC)`. |

**`asyncio.get_event_loop()` sites** (39 occurrences, 37 files):
`src/master/adapters/aeonmind_adapter.py`, `src/master/adapters/nanocode_adapter.py`,
`src/master/adapters/tranc3_bots_adapter.py`, `src/master/adapters/src_workers_adapter.py`,
`src/master/bot_swarm.py`, `src/skills/enhanced_registry.py` (×2), `src/mesh/service_mesh.py`,
`src/platform/intelligent_scanner.py` (×2), `src/deepmind/gemini_multimodal.py`,
`src/observability/library_pipeline.py`, `src/bio_neural/consciousness_integration.py` (×2),
`src/healing/healing_bridge.py`, `src/benchmark/performance_suite.py`, `src/section7/scheduler.py`,
`src/section7/threat_intel_loop.py` (×3), `src/event_bus/bus.py`,
`src/tensorflow_core/hybrid_engine.py` (×2), `src/devocity/portal.py`,
`src/knowledge/knowledge_brain.py` (×3), plus others found by the same grep in
`src/observability/observatory.py` and `src/intelligence/semantic_knowledge.py` — **but those
last two are false positives**: on inspection, both files only *mention*
`asyncio.get_event_loop()` in a code comment explaining why they deliberately use
`asyncio.get_running_loop()` instead (with a `try/except RuntimeError` fallback to
`self._lock = None`). Those two are the **correct** pattern already in use elsewhere in this
codebase, and are the concrete template to apply to the other 37 sites — this is existing
in-house precedent, not a hypothetical fix.

**`datetime.utcnow()` sites** (19 files): `src/monetisation/billing.py` (×2),
`src/settings_store.py`, `src/auth/db_user_manager.py` (×3), `src/training/evaluator.py`,
`src/compliance/api_routes.py`, `src/compliance/checker.py`, `src/personality/spawner.py`,
`src/registry/file_registry.py`, `src/workflow/builder.py`, `src/entities/tiers.py`,
`src/entities/lifecycle.py`, `src/cloud/federation_controller.py`,
`src/core/adaptive_fabric.py`, `src/security/security_framework.py`, `deploy/cuckoo/init.py`,
`shared_core/security.py`, `api.py`, `docs/reference/security-framework.py`,
`Dimensional/security.py`.

**No `uvloop` dependency anywhere** in `requirements.txt`, any worker `requirements*.txt`, or
`tranc3-bots` — confirmed by repo-wide grep. This removes one commonly-cited asyncio-adjacent
native-extension risk from the picture entirely for this codebase.

---

## 4. Test/CI readiness — baseline established in this sandbox

- **Interpreter**: `python --version` → `Python 3.11.15` (this sandbox's only interpreter; no
  3.12/3.13/3.14 interpreter is installed here, so nothing in this assessment could be run
  against 3.14 directly).
- **Dependencies are actually installed**, matching `requirements.txt` pins exactly:
  `fastapi==0.136.3`, `numpy==2.1.3`, `pydantic==2.13.4`/`pydantic_core==2.46.4`,
  `torch==2.13.0+cu130`, `cryptography==48.0.1`, `psycopg2==2.9.12`, `qiskit==2.4.1`,
  `qiskit_aer==0.17.2`, `grpcio==1.83.0`, `sentencepiece==0.2.1` — confirmed by direct `import`
  in this sandbox, not just by reading the pin file.
- **`pytest tests/test_smoke.py -q`**: 15 passed (once run via `python -m pytest`, using the
  environment's own site-packages — an initial run through a standalone `uv`-installed `pytest`
  binary failed with `ModuleNotFoundError: No module named 'fastapi'` because that binary carries
  its own isolated environment with none of the project's dependencies; this is a sandbox
  artifact, not a repo problem, and does not affect `make test`/`pytest` run normally from the
  project's own environment).
- **Full suite** (`python -m pytest tests/ -q`, i.e. close to `make test-fast`'s selection minus
  `-x`): run **twice, independently, back to back**, in this sandbox. Both runs produced the
  **exact same 6 failures, and only those 6**, all confined to a single file:
  `tests/test_waivers.py::test_route_create_waiver`,
  `test_route_create_waiver_invalid_request_returns_400`, `test_route_list_waivers`,
  `test_route_revoke_waiver`, `test_route_revoke_unknown_waiver_returns_404`,
  `test_check_expired_emits_and_reports_count` (exit code `1` both times). Critically,
  **`python -m pytest tests/test_waivers.py -q` run in isolation passes cleanly (36 passed, 0
  failed)** — so this is not a broken test file, it's **order-dependent state leakage between
  test files** when the full suite runs together (most likely shared in-memory/module-level state
  in the waiver registry that a preceding test file mutates and doesn't reset). This is a
  **pre-existing test-suite hygiene issue on Python 3.11 today, unrelated to the 3.14 question** —
  but it is directly relevant to "test/CI readiness" for the upgrade project, because the same
  fragility (a full-suite run not being a reliable pass/fail signal on its own) would persist on
  whatever Python version the suite is run against, and would make attributing a *future* 3.14
  failure to the interpreter bump vs. this pre-existing ordering issue harder than it needs to be.
  Recommend fixing the `test_waivers.py` isolation issue before (or alongside) any 3.14
  validation work, so a full-suite red/green signal can actually be trusted. This sandbox also had
  a second, externally-initiated `pytest` process (invoking `test_roles_suite_stewardship.py`,
  `test_roles_routes.py`, `test_matrix_suites.py`) running concurrently against the same shared
  `logs/test_results.jsonl` during part of this investigation — that file is gitignored
  (`.gitignore`: `logs/`) and accumulates across unrelated runs/sessions, so it was not used as a
  source of truth here; the FAILED-list comparison above is from this investigation's own two
  captured `pytest` invocations only.
- **No `tox.ini` or `noxfile.py` exists anywhere in the repo** — confirmed by `find`. There is no
  existing multi-version test matrix infrastructure for the main backend or `tranc3-bots`; the
  only multi-version matrix in the whole repo is `python.yml`'s `aeonmind/python` job
  (`['3.10','3.11','3.12']` + the new `3.14` experimental leg). **A tox/nox matrix (or an
  equivalent CI matrix job) would need to be added for the root app, `tranc3-bots`, and
  representative workers before 3.14 compatibility could be verified anywhere beyond
  `aeonmind/python`.**

---

## 5. Dependabot Docker-bump branches — are they safe to merge as-is?

**No, not as a way to complete the upgrade — and one of them is independently broken.**

### 5.1 Concrete build breakage found: `docker/Dockerfile.api`

`docker/Dockerfile.api` is a multi-stage build referenced by `docker-compose.yml`,
`docker-compose.development.yml`, `docker-compose.storage.yml`, and `docker-compose.uat.yml` (so
it is a live, in-use Dockerfile for dev/UAT environments, not dead code). Its runtime stage copies
site-packages from the builder stage using a **hardcoded Python-version path**:

```dockerfile
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
```

The dependabot branch `origin/dependabot/docker/docker/python-3.14-slim` was fetched and diffed
directly against `main` for this assessment. It bumps **only** the two `FROM python:3.11-slim@...`
lines to `FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6`
in both the `builder` and `runtime` stages — the `COPY --from=builder .../python3.11/...` line is
**left untouched**, still reading `python3.11`. On Python 3.14, `pip install` in the builder stage
installs to `/usr/local/lib/python3.14/site-packages`, so the runtime stage's `COPY` would either
fail outright (path doesn't exist) or silently copy nothing useful, depending on the Docker
builder's exact error behavior — **this is a real, verified, mechanical build break, confirmed by
reading the actual branch content** (`git show origin/dependabot/docker/docker/python-3.14-slim:docker/Dockerfile.api`),
not a hypothetical one. No other Dockerfile in the repo (root, `tranc3-bots/`, or any of the 84
worker Dockerfiles) has this hardcoded-path pattern — grep for `python3.11` across every
Dockerfile in the repo returns only this one file — so this specific defect is isolated to
`docker/Dockerfile.api`, but it means **that particular dependabot branch cannot be merged as-is
without also hand-editing the `COPY --from=builder` line.**

### 5.2 The other 87 branches are mechanically clean but incomplete

Every other dependabot branch checked (spot-checked: `workers/cryptex`, `workers/library-service`,
`workers/tateking`, plus the root `dependabot/docker/python-3.14-slim` and
`dependabot/docker/tranc3-bots/python-3.14-slim`) changes **only** the `FROM` line's tag+digest —
confirmed by diffing each against `main`. They do not touch `requires-python` in any
`pyproject.toml`, any CI `python-version:` matrix entry, `ruff target-version`, or
`mypy python_version`. All 84 Python-based worker Dockerfiles have a corresponding
`dependabot/docker/workers/<name>/python-3.14-slim` branch (verified 1:1 by diffing the branch
list against the worker directory list — no worker is missing a branch, and no branch targets a
non-Python-based worker).

**Merging any of these in isolation does not complete an upgrade** — it changes what the
container's interpreter *is* without validating that the pinned dependencies in that same
container's `requirements*.txt` actually install cleanly on it (§2's "uncertain" packages are
exactly the ones that could fail silently at `docker build` time, turning into a production
incident rather than a caught CI failure, since **no CI workflow in this repo builds and smoke-
tests worker Docker images against a matrix of Python versions** — confirmed by grep of both
`.github/workflows/` and `.forgejo/workflows/` for any Python-version-matrixed Docker build step;
none exists).

**Recommendation for these branches specifically:** do not merge any of them yet. Fix
`docker/Dockerfile.api`'s hardcoded path first (whether or not its own dependabot branch is used),
then treat the rest as raw material for Stage 3+ of the plan below — cherry-pick the `FROM` line
change for whichever pilot worker is chosen first, verified by an actual `docker build` +
container smoke test, rather than merging the branch wholesale on the assumption that a green
Dependabot check means the application still runs.

---

## 6. Recommendation: staged plan

Do not flip the platform to 3.14 in one PR. Proposed sequence, informed by §1–§5 above:

**Stage 0 — Reconcile the floor (no functional change).**
Decide one `requires-python` floor across `pyproject.toml`, `tranc3-bots/pyproject.toml`,
`aeonmind/python/pyproject.toml`, and `rust_extensions/tranc3_crypto/pyproject.toml` (currently
split `>=3.11` / `>=3.10`) before layering a 3.14 ceiling on an already-inconsistent base. This is
a docs/config-only change with no runtime risk, and it's a prerequisite for reasoning cleanly
about "what does 3.14 support mean" later.

**Stage 1 — Verify the "uncertain" dependencies against a real 3.14 interpreter.**
Before touching any Dockerfile, get access to an actual Python 3.14 environment (this sandbox
only has 3.11) and run `pip install` for each package flagged "uncertain" or "genuine risk" in
§2 — `qiskit-aer==0.17.2` above all, then `torch==2.13.0`, `psycopg2-binary==2.9.12`,
`sentencepiece==0.2.1`, and `opentelemetry-exporter-otlp-proto-grpc`/`grpcio`. Record which
resolve to a prebuilt wheel vs. fall back to source compilation. This is the one step that
converts every "likely/uncertain" judgment in this document from historical-pattern reasoning
into verified fact, for both this document and the existing `docs/architecture/` one.

**Stage 2 — Fix `docker/Dockerfile.api`'s hardcoded path, independent of the Python bump.**
The `COPY --from=builder /usr/local/lib/python3.11/site-packages ...` line should be made
version-agnostic (e.g. glob or an explicit build-arg) regardless of when 3.14 lands — it's
already a latent multi-stage-build fragility today (breaks on *any* future base-image bump, not
just 3.14).

**Stage 3 — Pilot on 1–2 low-risk standalone workers.**
Because §2 confirmed no worker requirements file pulls `torch`/`numpy`/`qiskit`/`grpcio`
(direct)/`sentencepiece`/`faiss`, workers are meaningfully lower-risk than the root app. Good
pilot candidates, in order of preference:

- **`workers/analytics-service`** — exact-pinned (`fastapi==0.136.3`, `pydantic==2.11.5`,
  `duckdb==1.3.0`, `polars==1.30.0`, `pandas==3.0.3`). `duckdb` and `polars` are both Rust-backed
  with historically fast wheel turnaround (per §2's "likely" reasoning, still unverified against
  a real 3.14 index per Stage 1). Currently on `python:3.11-slim`, so this is a genuine 3.11→3.14
  jump, not a repeat of the already-landed 3.11→3.12 workers.
- **`workers/cryptex`** — exact-pinned, minimal surface (`fastapi`, `starlette`, `uvicorn`,
  `pydantic`, `httpx` — no native-extension deps at all in the required set; the commented-out
  optional engines `pyclamd`/`yara-python`/`semgrep` aren't installed by default). Already on
  `python:3.12-slim`, making it a smaller 3.12→3.14 step — useful as a second, even-lower-risk
  data point alongside `analytics-service`'s bigger jump.

Avoid picking a worker with floating `>=` pins (`library-service`) or zero pins
(`ffmpeg-worker`, `triposr-worker`, `blender-worker`) as the *first* pilot — their current
dependency set isn't even reproducible on 3.11 today, so a 3.14 failure there would be
impossible to attribute cleanly to the interpreter bump versus pin drift. Pin them first (Stage 6
below), pilot after.

For the chosen pilot(s): take the `FROM` line from that worker's existing dependabot branch
(already using the correct, pre-resolved `python:3.14-slim` digest
`sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6`, confirmed identical
across every worker branch spot-checked), build the image, and actually run its test coverage (if
any exists — check `tests/test_workers_p0.py` and similar for coverage of the chosen worker)
against the built container, not just against the host 3.11 interpreter.

**Stage 4 — Roll to the rest of the P3 workers in small batches**, watching build + any available
tests after each batch, using the now-verified `FROM` line from the corresponding dependabot
branch each time.

**Stage 5 — P0–P2 workers, `tranc3-bots`, then the root app last.**
The root app carries every "uncertain"/"genuine risk" dependency identified in §2
(`torch`, `qiskit-aer`, `psycopg2-binary`, `sentencepiece`) and is the most complex Dockerfile
(multi-target, largest `requirements.txt`) — it should be the last thing moved, once Stages 1–4
have produced real evidence rather than reasoning. This stage also retargets every hardcoded
`"3.11"` CI pin (§1: 8 GitHub Actions files, 16 Forgejo files, 2 Magna Carta submodule files) —
but only changes *what CI runs on*, not `requires-python`/`ruff target-version`/
`mypy python_version`, which stay at the Stage 0 floor unless a separate, explicit decision drops
3.11 support entirely.

**Stage 6 — Hygiene cleanup, bundled here since it's the same "pin things properly while touching
the interpreter" work**: pin `ffmpeg-worker`, `triposr-worker`, `blender-worker`'s currently-bare
`requirements.txt` files to the versions confirmed working during the rollout; convert
`library-service`'s floating `>=` pins to exact pins matching the rest of the estate; sweep the 37
files using `asyncio.get_event_loop()` to the `get_running_loop()` + `try/except RuntimeError`
pattern already used correctly in `src/observability/observatory.py` and
`src/intelligence/semantic_knowledge.py`; replace the 19 files' `datetime.utcnow()` calls with
`datetime.now(datetime.UTC)`.

### On the existing dependabot branches specifically

**Do not merge them as a shortcut to "done."** As established in §5: 87 of the 88
Docker-base-image-bump branches are mechanically clean (FROM-line-only) but merging any one of
them changes a container's interpreter without validating that container's pinned dependencies
against it — exactly the runtime/build mismatch this task asked about — and **one of them
(`docker/docker/python-3.14-slim`, i.e. `docker/Dockerfile.api`) is independently broken** by a
stale hardcoded path unrelated to dependency compatibility. The correct use for these branches is
as a source of the pre-resolved `python:3.14-slim` digest for each Dockerfile, consumed during
Stages 3–5 above after each target has been through the verification those stages describe — not
as PRs to merge directly.
