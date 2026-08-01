# Python 3.11 → 3.14 Upgrade Assessment

**Status:** Assessment complete, Stage 1 (non-blocking CI signal) landed. Not a merge — a
staged project, tracked here rather than in a single PR.

**Date:** 2026-08-01

## 1. Current state (inventory)

The repository's Python version floor is inconsistent and its CI has almost no coverage of
anything beyond 3.11:

| Surface | Current state |
|---|---|
| Root `pyproject.toml` | `requires-python = ">=3.11"`, `ruff target-version = "py311"`, `mypy python_version = "3.11"` |
| `aeonmind/python/pyproject.toml` | `requires-python = ">=3.10"` — **lower floor than root** |
| `rust_extensions/tranc3_crypto/pyproject.toml` | `requires-python = ">=3.10"` — **lower floor than root** |
| `tranc3-bots/pyproject.toml` | `requires-python = ">=3.11"` |
| GitHub Actions (`.github/workflows/`) | Before Stage 1, 8 of 15 workflow files hardcoded `python-version: "3.11"` (14 total references — some files reference it more than once, e.g. `python.yml` four times, `test.yml` three, `ci.yml` twice), and the sole exception (`python.yml`'s `test` job) ran only a `['3.10', '3.11', '3.12']` matrix, scoped to `aeonmind/python/`, not the main backend. Stage 1 (below) adds `3.14` to that same job as a `continue-on-error` entry — configured now, its first actual run still pending the next PR that touches `aeonmind/python/**`. |
| Forgejo (`.forgejo/workflows/`, the primary CI/CD system per this repo's own CLAUDE.md) | Every one of 16 workflow files hardcodes `"3.11"`. No Python-version matrix exists anywhere in Forgejo (`registry-push.yml` does use a `strategy.matrix`, but for multi-image builds, not Python versions). |
| Magna Carta submodule CI | `layer-b-ci.yml` hardcodes `"3.11"` |
| Docker base images | ~80 worker Dockerfiles on `python:3.11-slim` (one shared pinned SHA256 digest), 9 workers on `python:3.12-slim`, `ffmpeg-worker` on `python:3.12-slim-bookworm`. Root `Dockerfile`, `docker/Dockerfile*`, and `tranc3-bots/Dockerfile` all on `python:3.11-slim`. All Python base images are pinned by digest, not just tag — an upgrade requires resolving new digests, not just editing a tag string. |
| `.python-version` / `runtime.txt` | Neither exists anywhere in the repo. Fly.io apps (`fly.toml`, `tranc3-bots/fly.toml`) build via Dockerfile, so the Docker base image is the actual source of truth for their Python version — there's no separate Fly buildpack version to track. |

**Before Stage 1, nothing in CI had ever exercised 3.13 or 3.14.** The widest matrix in the repo
topped out at 3.12, and only for one sub-project. Python 3.14 is now configured (Section 5) but
awaits its first actual run.

## 2. Dependency risk (packages sensitive to interpreter version)

Reasoned from known release-cadence patterns, not from an actual `pip install` against 3.14 in
this environment — **Stage 1 below is what turns this into verified fact**.

**Low risk — expect wheels are already available:**
`numpy`, `cryptography`, `pydantic`/`pydantic-core` (Rust via maturin, fast wheel turnaround),
`duckdb`, `polars` (Rust-based), `lxml` (manylinux wheels typically land quickly),
`psycopg2-binary`, `torch`, `sqlalchemy`, `redis`, `msgpack`, `datasets`, `sentencepiece`. These
all have active maintenance and manylinux/abi3 wheel pipelines that have historically kept pace
with new CPython releases within weeks of GA.

**Genuine risk — verify explicitly before relying on it:**
- **`qiskit-aer`** (`requirements.txt`, `requirements-ai.txt`, used by Think Tank /
  `src/quantum/`) — a C++ extension with a *historically* slower cadence for new-Python-version
  wheel releases than the pure-Python `qiskit` package it pairs with. This is the one dependency
  in the estate most likely to still be missing a 3.14 wheel or to require a source build.
- **`opentelemetry-exporter-otlp-proto-grpc`** (several workers, `>=` floating pins) — `grpcio`'s
  C-extension has occasionally lagged new CPython versions in the past; floating the pin also
  means the exact version that resolves is not controlled today.

**Hygiene gap, not directly a 3.14 blocker, but worth fixing in the same project:**
Three workers ship **zero** dependency pins at all — `triposr-worker`, `blender-worker`,
`ffmpeg-worker` (`fastapi`, `uvicorn`, `pillow` unpinned). On a fresh interpreter these will
resolve to whatever the latest wheels happen to be at build time, untested against anything.
`haystack-service`, `dspy-service`, `llamaindex-service` pin `pydantic==2.8.2`, materially older
than the `2.11.5`–`2.13.4` used everywhere else — worth reconciling regardless of the Python
version work, since it's existing drift.

## 3. Why staged, not a mass edit

- ~90 Dockerfiles pinned by digest, ~30 CI workflow files hardcoding `"3.11"`, and a
  `requires-python` floor that's already inconsistent before touching 3.14. A single PR touching
  all of it is unreviewable and, if something in the qiskit-aer/grpc tail breaks, unrevertable
  without reverting everything else with it.
- The workers are independently deployable (own Dockerfile, own `requirements-worker.txt`, own
  Fly/compose entry) — that independence is exactly what makes a staged rollout cheap: each stage
  is a small, revertible unit.

## 4. Staged plan

| Stage | What | Risk | Status |
|---|---|---|---|
| **0** | Reconcile the `requires-python` floor: root/`tranc3-bots` at `>=3.11` vs. `aeonmind/python`/`tranc3_crypto` at `>=3.10`. Decide one floor (recommend `>=3.11` everywhere, since that's already the majority and the CI reality) before layering 3.14 on top of an inconsistent base. | None (docs/config only) | Not started — needs an owner decision, not just a mechanical edit |
| **1** | Add `'3.14'` to the existing `aeonmind/python` CI matrix (`.github/workflows/python.yml`) as the first real, empirical signal — nothing in this repo has actually been run against 3.14 yet. | Low — additive, non-blocking if marked `continue-on-error` | **Done this session** (see below) |
| **2** | Once Stage 1 is green (or its failures are understood), explicitly verify `qiskit-aer` and `opentelemetry-exporter-otlp-proto-grpc` against 3.14 — `pip install` in a 3.14 venv and confirm a wheel resolves, not a source build. This is the one step that can't be reasoned about from release history alone. | Investigation only | Blocked on Stage 1 signal |
| **3** | Pick one low-traffic P3 worker as a pilot (e.g. `analytics-service` — no genuinely risky deps per Section 2), bump its Dockerfile to `python:3.14-slim` + resolve the new digest, run its test suite. | Low — single worker, independently revertible | Blocked on Stage 2 |
| **4** | Roll the same Dockerfile bump to the rest of the P3 workers in small batches, watching each for build/test failures before continuing. | Low per-batch | Blocked on Stage 3 |
| **5** | P0–P2 workers, root `Dockerfile`/`docker/Dockerfile*`/`tranc3-bots/Dockerfile`, then retarget every hardcoded `"3.11"` CI pin (GitHub Actions and Forgejo) to `"3.14"`. This stage ships what 3.14 *runs on* — it does not touch `requires-python`, `ruff target-version`, or `mypy python_version`; per Section 6, those describe the *minimum* supported version and stay at 3.11 unless a separate, explicitly approved decision drops 3.11 support. | Moderate — this is the stage that actually changes what ships | Blocked on Stage 4 |
| **6** | Pin the three currently-unpinned workers (`triposr-worker`, `blender-worker`, `ffmpeg-worker`) to the versions confirmed working in Stage 3–5, and reconcile the `pydantic==2.8.2` drift in `haystack-service`/`dspy-service`/`llamaindex-service` to match the rest of the estate. Bundled here since it's the same "pin things properly before/while touching the interpreter" work. | Low | Blocked on Stage 5 |

## 5. What's landed so far

**Stage 1** — `.github/workflows/python.yml`'s `test` job matrix now includes `'3.14'`
(`continue-on-error: true` on the added entry only, so a 3.14 failure surfaces as a visible
warning without blocking the `3.10`/`3.11`/`3.12` results or gating any PR). This is genuinely
non-blocking: existing version coverage and PR gating remain unchanged. `strategy.fail-fast: false`
was added alongside it — without it, GitHub Actions cancels sibling matrix jobs the moment any one
job fails, and `continue-on-error` does not exempt a job from that cancellation trigger, so a 3.14
failure could have cancelled the 3.10/3.11/3.12 jobs mid-run before this change. The one
behavioural side effect: a genuine failure on 3.10, 3.11, or 3.12 itself no longer cancels its
siblings early either — all four legs now always run to completion, at the cost of some CI time in
that scenario.

## 6. Explicitly out of scope here

- Whether to move the *floor* past 3.11 (i.e. drop 3.11 support) is a separate decision from
  *adding* 3.14 support — this assessment only covers reaching 3.14, not deprecating anything.
- No Dockerfile, requirements file, or non-aeonmind CI workflow has been changed. Stage 1 is
  additive and scoped to the one sub-project that already had multi-version infrastructure.
