# Service Doc-Pack — Turing's Hub (AI Personality Creation Centre)

| Field | Value |
|---|---|
| **Entity** | Turing's Hub |
| **Lead AI** | Samantha Turing |
| **Status** | 🔧 Partial (per `CLAUDE.md` service table) |
| **Code** | `src/personality/` |
| **HTTP surface** | `/turingshub/*` router — mounted in `api.py` (`app.include_router(_turingshub_router)`) |
| **Gate tier** | Partial → GOV + DDD (scoped) + RACI + SIM + ASD + TFM + POL + STD |

> **Truthfulness:** claims cite `src/personality/`. Implementation status is owned by the
> `CLAUDE.md` service table; identity/ownership by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** Turing's Hub is the AI personality creation centre — it curates personality profiles
  and spawns new personality micro-services from a template.
- **Owner (RACI-A):** Samantha Turing (Lead AI).
- **Scope (current):** a `/turingshub` router over a `PersonalityMatrix` (profile registry) and a
  `PersonalitySpawner` (code generator). **Out of scope (current):** a hosted UI; spawning is an API
  + filesystem operation.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/personality/turingshub/routes.py`, prefix `/turingshub`)
| Method | Route | Backing code |
|---|---|---|
| GET | `/turingshub/status` | spawner (profile count + list) — the route uses only the spawner; the matrix is not touched here |
| GET | `/turingshub/personalities` | iterates `list(spawner._profiles.keys())` (the route's `list_profiles` `hasattr` guard is dead — that method is on `PersonalityMatrix`, not the spawner — so it takes the `_profiles` fallback), returning `{id, profile}` per id |
| GET | `/turingshub/personalities/{personality_id}` | profile lookup |
| POST | `/turingshub/spawn` | `PersonalitySpawner.spawn(...)` |
| GET | `/turingshub/matrix/active` | **PARTIAL** — returns `{active_personality}`, but `PersonalityMatrix` has no active-personality tracking, so the value is currently `null` (an "active" concept is PLANNED). The `_matrix()` import was corrected here to `PersonalityMatrix` (the old `EnhancedPersonalityMatrix` import raised and forced the error fallback) |

### Core (`src/personality/`)
- **`matrix.py`** — `PersonalityProfile` (load/save JSON, `build_system_prompt(user_context)`) and
  `PersonalityMatrix` (loads all profiles from `src/personality/profiles/`, `get` / `list_profiles` /
  `register`). **44** profile JSONs ship in `profiles/`. Wired into `api.py` as
  `EnhancedPersonalityMatrix` (import-guarded).
- **`spawner.py`** — `PersonalitySpawner.spawn(...)` generates a full personality micro-repo:
  `_write_config`, `_write_active_profile`, `_write_env_example`, `_write_api`, `_write_readme`,
  `_write_requirements`, `_write_docker`. Output base resolved via `_resolve_output_base` (sandboxed).
- **`lnn.py`** — liquid neural network; **`snn_qat.py`** — spiking NN quantization-aware training.
  Research modules in the personality package (not on the `/turingshub` router).
- **`profiles/`** — 44 JSON profiles. Note: `vesper-nightingale`, `atlas-meridian` are internal
  legacy profiles, **not** platform entities (per `CLAUDE.md` naming rules).

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** registry + code-generator. The matrix is an in-memory profile store loaded from disk;
  the spawner is a template-driven file emitter.
- **Decision:** personalities are **data** (JSON profiles) + a generator, not bespoke code per
  personality — new personalities are added as profiles and materialised on demand via `spawn`.

## 4. RACI Matrix

| Activity | Samantha Turing (Lead) | Platform Owner | The Chaos Party | The Observatory |
|---|---|---|---|---|
| Profile registry (matrix) | **R/A** | C | I | I |
| Personality spawning | **R/A** | C | R | I |
| Profile schema/standards | **R/A** | C | I | I |

## 5. Solutions Integration Model (SIM)

- **Upstream:** `api.py` mounts `/turingshub`. It also *attempts* to instantiate
  `EnhancedPersonalityMatrix` (an alias of `PersonalityMatrix`) at startup, but currently passes a
  config object where `PersonalityMatrix.__init__` expects a `profiles_dir` path — so that call
  raises and `personality_matrix` is left unset (fail-soft, logged). **PARTIAL/PLANNED:**
  `PersonalityProfile.build_system_prompt` exists but is **not yet consumed** by any in-repo inference
  path; wiring profiles into prompt construction (and fixing the startup arg) is pending.
- **Downstream:** `spawn` writes a generated personality repo to a sandboxed output base.
- **Auth boundary (current):** the `/turingshub` router does not enforce auth itself; `spawn` writes
  to filesystem — front with platform auth (Infinity) and restrict `spawn` in production (**PLANNED**).

## 6. Architecture Scalability Document (ASD)

- **Load model:** registry reads are O(profiles) at load; `spawn` is an I/O burst (writes a repo).
- **Zero-cost:** pure Python + filesystem; no paid dependency.
- **Degradation:** if `PersonalityMatrix` import fails, `api.py` logs a warning and continues with
  `EnhancedPersonalityMatrix = None` (import-guarded).

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Profile store | JSON files in `profiles/` | in-repo |
| Prompt assembly | `PersonalityProfile.build_system_prompt` | in-process |
| Code generation | template writers in `spawner.py` | in-process |
| Research NN | `lnn.py`, `snn_qat.py` (PyTorch) | OSS |

## 8. Policy (POL)

- Reuses platform policy (`POL-AI-001`, `docs/defstan/`). Generated repos must not embed secrets —
  `_write_env_example` emits an `.env.example`, never real credentials.

## 9. Procedure (PROC)

- **Add a personality:** drop a profile JSON in `src/personality/profiles/`; it is picked up by
  `PersonalityMatrix._load_all()`. Materialise via `POST /turingshub/spawn`.

## 10. Runbook (RUN)

- **`/turingshub/status` shows matrix unavailable:** `PersonalityMatrix` import failed — check the
  `api.py` startup warning and the `profiles/` directory.
- **`spawn` fails:** verify the resolved output base (`_resolve_output_base`) is writable and inside
  the sandbox; check the returned file list.

## 11. Standards (STD)

- Profiles are JSON with a stable schema (`PersonalityProfile._from_dict`).
- Spawn output is sandboxed via `_resolve_output_base`; no writes outside the resolved base.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-02 | Claude (session) | `src/personality/turingshub/routes.py`, `matrix.py`, `spawner.py`, `profiles/` (44), `api.py` mount | Routes, classes, profile count, spawner writers, and mount point verified against code |
