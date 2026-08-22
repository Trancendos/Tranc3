---
title: "Python 3.11 → 3.14 Upgrade Assessment"
category: Architecture
last-reviewed: 2026-08-18
status: needs-update
---

# Python 3.11 → 3.14 Upgrade Assessment

**Status:** Stages 1, 2 and 6 landed. **82 of the 84 workers with a requirements file are
Python-3.14-ready; 2 are hard-blocked** (`tranceflow` and `vrar3d`, on `open3d` — see Section 2b).
Stage 3 onward (actually moving base images) is unblocked for the 82 and not yet started. Still a
staged project, tracked here rather than in a single PR.

> **Correction, same day.** An earlier revision of this document claimed "84 ready, 0 blocked".
> That was wrong, and wrong in a way worth recording: the readiness script only resolved exact
> `==` pins, so a *floating* requirement whose package has no 3.14 release at all was silently
> counted as fine and mentioned only in an informational "unpinned" list. `open3d` is exactly
> that case. The script now checks floating requirements for the one thing that is knowable
> without resolving them — whether the package has any 3.14-usable release at all — and reports
> it as a blocker. The lesson is the same one as Section 2a's: a checker that quietly skips what
> it cannot evaluate reports a better number than the truth.

**Date:** 2026-08-01, substantially revised 2026-08-12 when Stage 2 replaced this document's
predictions with measured data. **Section 2's original risk ranking was wrong in both
directions** — see Section 2a. Read Section 2a, not Section 2, for the current picture.

## 1. Current state (inventory)

The repository's Python version floor is inconsistent and its CI has almost no coverage of
anything beyond 3.11:

| Surface | Current state |
|---|---|
| Root `pyproject.toml` | `requires-python = ">=3.11"`, `ruff target-version = "py311"`, `mypy python_version = "3.11"` |
| `aeonmind/python/pyproject.toml` | `requires-python = ">=3.10"` — **lower floor than root** |
| `rust_extensions/tranc3_crypto/pyproject.toml` | `requires-python = ">=3.10"` — **lower floor than root** |
| `tranc3-bots/pyproject.toml` | `requires-python = ">=3.11"` |
| GitHub Actions (`.github/workflows/`) | Before Stage 1, 8 of 15 workflow files hardcoded `python-version: "3.11"` (12 total references — some files reference it more than once, e.g. `python.yml` three times, `test.yml` twice, `ci.yml` twice), and the sole exception (`python.yml`'s `test` job) ran only a `['3.10', '3.11', '3.12']` matrix, scoped to `aeonmind/python/`, not the main backend. Stage 1 (below) adds `3.14` to that same job as a `continue-on-error` entry — configured now, its first actual run is still pending the next PR that touches `aeonmind/python/**`. |
| Forgejo (`.forgejo/workflows/`, the primary CI/CD system per this repo's own CLAUDE.md) | 16 of 30 workflow files hardcode `python-version: '3.11'`. No Python-version matrix exists anywhere in Forgejo (`registry-push.yml` does use a `strategy.matrix`, but for multi-image builds, not Python versions). |
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
- **`qiskit-aer`** (`requirements.txt` only — `requirements-ai.txt` pins the pure-Python
  `qiskit==2.4.1` but not `qiskit-aer`; used by Think Tank /
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

## 2a. Dependency risk — MEASURED (2026-08-12, supersedes Section 2)

Section 2 above was explicitly reasoning, not measurement. `scripts/check_python314_readiness.py`
(added with this revision) replaces it with fact: it reads every worker's pinned requirements and
asks PyPI, per exact pinned version, whether an artifact usable by CPython 3.14 on **linux/x86_64**
actually exists — pure-Python wheel, cp314 manylinux/musllinux wheel, or abi3 wheel. The
linux/x86_64 restriction matters: every worker ships as a linux/amd64 `python:*-slim` container, so
a macOS or Windows cp314 wheel proves nothing about whether the image builds.

**Section 2's predictions were wrong in both directions.**

| Section 2 said | Reality (measured) |
|---|---|
| `qiskit-aer` — "the one dependency in the estate most likely to still be missing a 3.14 wheel or require a source build" | **Already fine.** The exact pinned `qiskit-aer==0.17.2` ships `qiskit_aer-0.17.2-cp314-cp314-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`. `qiskit==2.4.1` is an abi3 wheel (`cp310-abi3-manylinux_2_28_x86_64`), forward-compatible with 3.14 by construction. |
| `opentelemetry-exporter-otlp-proto-grpc` — "grpcio's C-extension has occasionally lagged" | **Already fine.** The exporter itself is pure-Python (`1.42.1-py3-none-any.whl`); its `grpcio` dependency ships cp314 manylinux *and* musllinux x86_64 wheels at 1.83.0. |
| (not mentioned at all) | **`duckdb==1.3.0` was a real blocker** — no cp314 wheel at that version; the lowest stable release that has one is **1.4.2**. Affected `analytics-service`, `cache-service`, `storage-service`. |
| (not mentioned at all) | **`pyyaml==6.0.2` was a real blocker** — 6.0.3 is the patch release that added 3.14 wheels. Affected `infinity-ai`, `swarm-coordinator-service`. |

The lesson worth keeping: the packages that felt risky (heavy C++/Rust extensions with visible
maintenance) had all kept pace, and the packages that blocked were mundane ones nobody thought to
check. Ranking dependency risk by "how complicated does this package feel" produced exactly the
wrong worklist — which is why this is now a script that runs, not a table someone reasons about.

**Both blockers are fixed** (Stage 6's dependency half, pulled forward because it was the only
thing standing between the estate and 3.14 readiness):

- `duckdb==1.3.0` → `1.4.2` in `analytics-service`, `cache-service`, `storage-service`
- `pyyaml==6.0.2` → `6.0.3` in `infinity-ai`, `swarm-coordinator-service`

Both were smoke-tested on the **current 3.11 runtime** against the APIs these workers actually use
(`duckdb.connect`/`execute`/`fetchall` round-trip; `yaml.safe_load`) before being applied, since
the bump ships on 3.11 today and only pays off on 3.14 later. DuckDB's storage format is stable
across the 1.x line, so an existing 1.3-written `.duckdb` file is readable by 1.4 — worth
confirming on the first deploy that touches a populated volume rather than taking on trust.

After those five one-line bumps: **84 workers ready, 0 blocked.**

## 2b. `open3d` — the one hard blocker left (2026-08-12)

`tranceflow` and `vrar3d` both depend on `open3d` (floating, `>=0.18`). **No release of `open3d`
— including the current 0.19.0 — publishes an artifact usable on CPython 3.14.** No cp314 wheel,
no abi3 wheel, no pure-Python fallback. This is not a "pin it higher" fix; there is no version to
pin to. Until upstream ships 3.14 wheels, those two workers cannot move off 3.11/3.12, whatever
the rest of the estate does.

That is survivable rather than fatal, because the workers are independently deployable: the
staged rollout can take the 82 ready workers to 3.14 and leave these two on their current base
image. It does mean the estate will be *mixed-version* for a while, which is worth stating
plainly rather than discovering during Stage 5.

Options, none of which need deciding yet:
- **Wait for upstream.** Cheapest; open3d has shipped new-CPython wheels before, just later than
  most.
- **Leave both workers on 3.11 indefinitely** and accept a permanently mixed estate.
- **Drop or replace `open3d`.** Both workers already carry `trimesh`, `pyvista` and `meshio`,
  which overlap much of what open3d is used for — worth checking whether the dependency is
  actually load-bearing in either worker before treating it as immovable. That check has not been
  done; do not assume it is removable.

### Still not covered by the measurement

- **Floating pins: 14 workers → 2.** `scripts/pin_worker_requirements.py` (new) converted 60
  floating requirements across 14 workers into exact `==` pins, resolving each to the newest
  stable release that both satisfies the existing constraint and is 3.14-usable — deliberately
  close to what a build would already have picked, so pinning freezes the version rather than
  moving anyone onto a new major. Only `open3d` in `tranceflow`/`vrar3d` is still floating, and
  only because there is no version worth pinning to (Section 2b). The script handles the
  OpenTelemetry instrumentation packages' `0.NNbM`-only release channel as a real release line
  rather than treating every one of their versions as an unusable prerelease.
- **Resolvable ≠ correct.** Pinning makes builds reproducible; it does not prove the newly-pinned
  versions behave identically to whatever floated before. The pins match what a build today would
  resolve, so this is not a behaviour change *as of today* — but it does freeze a version that
  will now stop drifting, which is the point.
- **6 directories have no requirements file at all** — `bullmq-queue-service`, `cranbania`,
  `nexus-ws-rs`, `rate-limit-service-rs`, `remotion-render-service`, `vault-service-rs`. These are
  the Rust/Node services and the CranBania submodule; they have no Python interpreter to upgrade,
  so their absence here is correct, not a gap.
- **Resolvable ≠ runs.** A wheel existing proves the image can build. It does not prove the worker
  behaves correctly on 3.14 — that is what Stage 3's pilot is for.

## 3. Why staged, not a mass edit

- ~90 Dockerfiles pinned by digest, ~30 CI workflow files hardcoding `"3.11"`, and a
  `requires-python` floor that's already inconsistent before touching 3.14. A single PR touching
  all of it is unreviewable and, if something in the qiskit-aer/grpc tail breaks, hard to revert
  without reverting everything else with it.
- The workers are independently deployable (own Dockerfile, own `requirements-worker.txt`, own
  Fly/compose entry) — that independence is exactly what makes a staged rollout cheap: each stage
  is a small, revertible unit.

## 4. Staged plan

| Stage | What | Risk | Status |
|---|---|---|---|
| **0** | Reconcile the `requires-python` floor: root/`tranc3-bots` at `>=3.11` vs. `aeonmind/python`/`tranc3_crypto` at `>=3.10`. Decide one floor (recommend `>=3.11` everywhere, since that's already the majority and the CI reality) before layering 3.14 on top of an inconsistent base. | None (docs/config only) | Not started — needs an owner decision, not just a mechanical edit |
| **1** | Add `'3.14'` to the existing `aeonmind/python` CI matrix (`.github/workflows/python.yml`) as the first real, empirical signal — nothing in this repo has actually been run against 3.14 yet. | Low — additive, non-blocking if marked `continue-on-error` | **Done this session** (see below) |
| **2** | Verify the risky dependencies against 3.14 for real rather than from release history. | Investigation only | **Done 2026-08-12** — and done for the *whole estate*, not just the two flagged packages, via `scripts/check_python314_readiness.py`. Did not need Stage 1's CI signal after all: PyPI's own release metadata answers "does a usable artifact exist" directly, per exact pinned version. See Section 2a. |
| **3** | Pick one low-traffic P3 worker as a pilot, bump its Dockerfile to `python:3.14-slim` + resolve the new digest, run its test suite. | Low — single worker, independently revertible | **Unblocked, not started.** Note: this row originally suggested `analytics-service` as the pilot "no genuinely risky deps per Section 2" — that was wrong, it was one of the five *blocked* workers (`duckdb`). It is fine now that the pin is bumped, but pick the pilot from the script's READY list rather than from intuition. The `python:3.14-slim` digest resolved 2026-08-12 is `sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc` — re-resolve at the time of use rather than trusting this value, since the tag moves with each patch build. |
| **4** | Roll the same Dockerfile bump to the rest of the P3 workers in small batches, watching each for build/test failures before continuing. | Low per-batch | Blocked on Stage 3 |
| **5** | P0–P2 workers, root `Dockerfile`/`docker/Dockerfile*`/`tranc3-bots/Dockerfile`, then retarget every hardcoded `"3.11"` CI pin (GitHub Actions and Forgejo) to `"3.14"`. This stage ships what 3.14 *runs on* — it does not touch `requires-python`, `ruff target-version`, or `mypy python_version`; per Section 6, those describe the *minimum* supported version and stay at 3.11 unless a separate, explicitly approved decision drops 3.11 support. | Moderate — this is the stage that actually changes what ships | Blocked on Stage 4 |
| **6** | Pin the currently-unpinned workers and reconcile the `pydantic==2.8.2` drift in `haystack-service`/`dspy-service`/`llamaindex-service` to match the rest of the estate. Bundled here since it's the same "pin things properly before/while touching the interpreter" work. | Low | **Dependency half done early 2026-08-12** (the five 3.14-blocking pins — see Section 2a — pulled forward because they were the only thing between the estate and readiness). Remaining: the 14 workers with floating pins, which is more than the three this row originally named — `tranceflow`/`vrar3d` (8 each) and `lab-service`/`library-service` (7 each) are larger than the originally-flagged trio. Full list in the script's output. |

## 5. What's landed so far

**Stage 2 + Stage 6 (dependency half)** — 2026-08-12. `scripts/check_python314_readiness.py` is
new: it walks `workers/*/requirements{-worker,}.txt`, and for every exact `==` pin asks PyPI
whether a 3.14/linux-x86_64-usable artifact exists, reporting blockers together with the lowest
stable version that would fix each one. Run it with no arguments for the whole estate, or pass
worker names to scope it. Exit code is 1 when anything is blocked, so it *can* gate a rollout
batch in CI — it is deliberately not wired into any workflow, because this upgrade is a staged
project rather than a merge gate, and a network-dependent check that fails on a PyPI hiccup is a
bad gate for unrelated PRs.

The first full run found 5 blocked workers, all fixed in the same pass (`duckdb==1.3.0` → `1.4.2`
in `analytics-service`/`cache-service`/`storage-service`; `pyyaml==6.0.2` → `6.0.3` in
`infinity-ai`/`swarm-coordinator-service`). Neither package was among the two this document had
predicted would be the problem, and both of *those* turned out to already be fine — Section 2a has
the full before/after. The estate now stands at 84 ready, 0 blocked.

**Stage 1** — `.github/workflows/python.yml`'s `test` job matrix now includes `'3.14'`
(`continue-on-error: true` on the added entry only, so a 3.14 failure surfaces as a visible
warning without blocking the `3.10`/`3.11`/`3.12` results or gating any PR). This is genuinely
non-blocking: existing version coverage and PR gating remain unchanged. A `continue-on-error: true`
job's own failure already never triggers `fail-fast` cancellation of its siblings — that exemption
is per-job and applies regardless of the `fail-fast` setting — so the 3.14 leg was never going to
cancel the 3.10/3.11/3.12 legs either way. `strategy.fail-fast: false` was added for the opposite
direction: without it, a genuine failure on 3.10, 3.11, or 3.12 (each `continue-on-error: false`,
the default) would cancel any in-progress/queued sibling job — including a still-running 3.14 job —
before it finishes, cutting short the exact empirical 3.14 signal this stage exists to collect. The
side effect: a failure on one stable leg (3.10/3.11/3.12) no longer cancels the *other* stable legs
early either, since `fail-fast: false` makes every matrix entry independent — all four legs now
always run to completion, at the cost of some CI time in that scenario.

## 6. Explicitly out of scope here

- Whether to move the *floor* past 3.11 (i.e. drop 3.11 support) is a separate decision from
  *adding* 3.14 support — this assessment only covers reaching 3.14, not deprecating anything.
  This is also why **Stage 0 is still not started**: reconciling the `requires-python` floor means
  raising `aeonmind/python` and `rust_extensions/tranc3_crypto` from `>=3.10` to `>=3.11`, which
  *drops* 3.10 support (and would retire the `3.10` leg of `python.yml`'s matrix). Every other
  stage here only adds; that one takes something away, so it stays an explicit owner decision
  rather than something inferred from "make it consistent".
- **No Dockerfile has been changed** — nothing yet runs on 3.14. As of 2026-08-12 the change
  surface is: five requirements pins bumped, one new script, and this document. The estate is
  *ready* for 3.14, which is not the same as being *on* it; Stages 3–5 are what would actually
  move it, and none of them have started.
- `requires-python`, `ruff target-version`, and `mypy python_version` all remain at 3.11
  throughout. Those describe the minimum supported version, not what the containers run.
