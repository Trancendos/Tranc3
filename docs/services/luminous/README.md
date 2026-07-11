# Service Doc-Pack — Luminous (Core Platform Brain)

| Field | Value |
|---|---|
| **Entity** | Luminous |
| **Lead AI** | Cornelius MacIntyre |
| **Status** | 🔧 Partial (per `CLAUDE.md` service table) |
| **Code** | `src/bio_neural/`, `src/core/` |
| **HTTP surface** | `/luminous/*` router — mounted in `api.py` (`app.include_router(_luminous_router)`) |
| **Gate tier** | Partial → GOV + DDD (scoped) + RACI + SIM + ASD + TFM + POL + STD; behavioural claims flagged where code is scaffold-only |

> **Truthfulness:** every claim below cites code in `src/bio_neural/` or `src/core/`. Where a
> path is a scaffold or fallback (not yet load-bearing) it is marked **PARTIAL**/**PLANNED**.
> Implementation status is owned by the `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`.

## 1. Service Governance Charter (GOV)

- **Mission:** Luminous is the platform's AI intelligence & orchestration core — model inference,
  bio-neural experiments (consciousness/neuromorphic), and the adaptive runtime fabric.
- **Owner (RACI-A):** Cornelius MacIntyre (Lead AI).
- **Scope (current):** an `/luminous` FastAPI router exposing status, an IIT Φ calculator, and a
  neuromorphic spiking-network endpoint; plus the `src/core/` inference/runtime modules used by the
  main backend. **Out of scope (current):** a single unified orchestration entrypoint — orchestration
  primitives exist as separate modules (see DDD) but are not yet fronted by one API.

## 2. Detailed Design Document (DDD)

### HTTP surface (`src/bio_neural/routes.py`, prefix `/luminous`)
| Method | Route | Backing code | Notes |
|---|---|---|---|
| GET | `/luminous/status` | inline | Reports `consciousness` / `neuromorphic` module availability |
| POST | `/luminous/consciousness/phi` | `IITCalculator.calculate_phi` | Body `{state: list[float]}`; state normalised to a distribution, passed to the calculator **as a `torch.Tensor`** (it calls `.detach().cpu().numpy()` internally); returns `{phi, state_dim}`. Returns `503` if torch/numpy are absent |
| POST | `/luminous/neuromorphic/process` | `NeuromorphicProcessor.process(x, learn=False)` | Body `{input: list[float], timesteps:int}`. `timesteps` is echoed (it is fixed at processor construction, **not** a `process()` kwarg). `process` **fail-softs** — it catches SNN errors internally and returns a fallback `{output, spike_rate, energy_estimate}` rather than raising, so a shape mismatch yields that degraded payload, not a hard error |

### Bio-neural core (`src/bio_neural/`)
- **`consciousness_engine.py`** — `IITCalculator` (Φ via whole-vs-parts entropy differences,
  `calculate_phi` / `calculate_integrated_information`), `GlobalWorkspace(nn.Module)`,
  `SelfAwarenessModule(nn.Module)`. IIT-based; research-grade.
- **`neuromorphic.py`** — `LIFNeuron`, `SpikingLayer`, `STDPLearning`, `SpikingNeuralNetwork`,
  `NeuromorphicProcessor` (leaky integrate-and-fire + STDP).

### Runtime/inference fabric (`src/core/`, selected)
`model.py` / `advanced_model.py` / `ml_pipeline.py` (inference), `tokenizer.py` +
`multilingual_tokenizer.py`, provider adapters (`ollama_adapter.py`, `openrouter_adapter.py`,
`llama_cpp_adapter.py`), `adaptive_fabric.py`, `mape_k.py` (MAPE-K control loop),
`self_evolution.py`, `cell_orchestrator.py`, `smart_container.py`, `output_safety.py`,
`resource_limits.py`, `adaptive_rate_limiter.py`, `quantum_inference.py`, `startup_validator.py`.
These are libraries consumed by the backend; not all are exposed via the `/luminous` router.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** library-first. Bio-neural experiments are exposed through a thin FastAPI router; the
  heavier `src/core/` modules are imported directly by `api.py` at startup.
- **Dependencies:** `torch`/`numpy` (bio-neural), optional local/free LLM providers (Ollama →
  OpenRouter free → llama.cpp) via `src/core/*_adapter.py`. Torch/heavy deps are import-guarded — the
  `/luminous` endpoints return `503` on `ImportError` rather than crashing.
- **Decision:** keep consciousness/neuromorphic as opt-in research surfaces (import-guarded, fail-soft)
  so the core backend has no hard dependency on them.

## 4. RACI Matrix

| Activity | Cornelius MacIntyre (Lead) | Platform Owner | The Chaos Party (test) | The Observatory |
|---|---|---|---|---|
| Inference/runtime modules | **R/A** | C | C | I |
| Bio-neural endpoints | **R/A** | I | R | I |
| Model-provider adapters (zero-cost) | **R/A** | C | I | I |
| Incident (inference down) | **R** | I | C | **A** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** the main backend (`api.py`) mounts `/luminous` and imports `src/core/` inference
  modules; the AI Gateway (`src/ai_gateway/`) and Ollama/OpenRouter adapters provide model access.
- **Downstream:** returns Φ / spiking-network results and model inferences to callers.
- **Auth boundary (current):** the `/luminous` router does **not** enforce auth itself — front it
  with platform auth (Infinity) at the gateway (**PLANNED**). Endpoints validate request bodies and
  fail soft (`400`/`503`/`500` with sanitised detail via `safe_error_detail`).

## 6. Architecture Scalability Document (ASD)

- **Load model:** Φ and neuromorphic calls are CPU/torch-bound and O(state/timesteps); intended for
  low-rate experimentation, not hot-path serving.
- **Zero-cost limits & hard stops:** model access uses free providers only (Ollama local →
  OpenRouter `:free` → llama.cpp); `resource_limits.py` and `adaptive_rate_limiter.py` bound usage.
  No paid inference dependency.
- **Degradation:** torch/provider absence → `503`; the backend keeps running (import-guarded).

## 7. Deployment Scope Matrix (DSM)

- **Mode awareness:** No — this entity's own code does not call `PlatformInfraMode` / `src/platform/infrastructure_mode.py`. (Some platform-wide, cross-cutting code *does* branch on the mode — `src/routers/adaptive.py` and `src/routers/ecosystem.py` read/set `PLATFORM_INFRA_MODE`/`SYSTEM_MODE` directly, and `Dimensional/architecture/storage_factory.py` selects a storage provider from `SYSTEM_MODE` — but none of that code is owned by this or any other one of the 43 named entities; it is shared platform infrastructure, not this service's own logic. The Citadel is the only one of the 43 named entities whose own code branches on the mode — see `docs/services/the-citadel/README.md`.) This entity's deployment scope is determined externally — by which `docker-compose.production.yml` service block runs, and where — not by in-process mode detection.
- **Runtime placement:** mounted in the `tranc3-backend` monolith (`api.py`); runs wherever that monolith's `docker-compose.production.yml` service block is deployed, on whatever port/host the monolith uses (compose service `tranc3-backend`)
- **Persistence:** SQLite/volume shared with the rest of the monolith (`tranc3-backend` has a named volume in compose)
- **Note:** an optional local LLM backend (`ollama`, its own compose service with a dedicated volume for model weights) gives Luminous materially better inference cost/latency on Local-Only or Hybrid — Cloud-Only free-tier CPU hosts cannot realistically serve local model weights, so Cloud-Only falls back to the AI Gateway's free-tier cloud providers (OpenRouter/HuggingFace) instead of Ollama.

| Setup | What runs, and where | Data locality | Hard blockers / caveats |
|---|---|---|---|
| **Cloud-Only** | the `tranc3-backend` compose block runs on a single cloud host (e.g. Fly.io / Oracle Free Tier); Traefik/edge in front | backed by the monolith's attached volume — persists across redeploys as long as the volume is preserved | no entity-specific blocker beyond whatever applies to the monolith as a whole |
| **Hybrid** | same monolith block; per `docs/architecture/infrastructure-modes.md`'s Hybrid diagram, persistent data can sync to local TrueNAS while the monolith itself still runs wherever it's deployed | monolith volume, optionally mirrored to local TrueNAS via Syncthing | requires `CITADEL_LOCAL_STACK=true` if a local compose stack should run alongside the cloud one, per `should_run_citadel_docker()` in `infrastructure_mode.py` |
| **Local-Only** | same monolith block, run entirely on local/Citadel hardware behind local Traefik | fully local, volume-backed | none beyond standard local-hardware ops (backup, power, network) |

- **Zero-cost posture per mode:** Cloud-Only defaults to the `zero_cost_cloud` AI-rotation chain; Hybrid/Local-Only default to `zero_cost_full` (`config/platform/infrastructure_mode.yaml`) — this only affects AI-Gateway-routed calls, not this entity's own logic
- **Switching modes:** operator-level via `PLATFORM_INFRA_MODE` (or legacy `SYSTEM_MODE`); this entity needs no code change to move between modes, only a redeploy-target change for the monolith as a whole

## 8. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Tensors / NN | PyTorch (`torch`, `nn.Module`) | OSS |
| Consciousness metric | IIT Φ (`IITCalculator`) | in-process |
| Neuromorphic | LIF + STDP spiking net | in-process |
| Model providers | Ollama / OpenRouter `:free` / llama.cpp | free tiers only, rotate on failure |
| Control loop | MAPE-K (`mape_k.py`) | in-process |

## 9. Policy (POL)

- Reuses platform policy (`POL-AI-001`, `docs/defstan/`); no paid model APIs; outputs pass
  `output_safety.py` before return where wired.

## 10. Procedure (PROC)

- **Add a bio-neural endpoint:** implement in `src/bio_neural/`, expose via `routes.py`, keep the
  heavy import inside the handler (import-guarded), return `503` on `ImportError`.

## 11. Runbook (RUN)

- **`/luminous/status` degraded:** check `consciousness`/`neuromorphic` module fields; a `degraded`
  value indicates a failed import — verify `torch`/`numpy` in the image.
- **`phi` returns 0.0 unexpectedly:** `IITCalculator.calculate_phi` returns `0.0` on any internal
  error (it wraps the entropy math in try/except). Confirm the `state` vector is non-zero, and that
  it reaches the calculator as a `torch.Tensor` (a plain ndarray triggers an `AttributeError` on
  `.detach()` → caught → `0.0`; the route converts to a tensor for this reason).
- **`neuromorphic/process` output looks degraded (`spike_rate: 0.0`):** `NeuromorphicProcessor.process`
  catches internal SNN errors and returns the fallback `{output, spike_rate: 0.0, energy_estimate: 0.0}`
  — usually an input-shape mismatch against the configured net. The handler calls `process(x)`; a
  `timesteps=` kwarg would be a `TypeError` (real signature `process(x, learn=False)`).

## 12. Standards (STD)

- Error detail sanitised (`safe_error_detail`); logs sanitised (`sanitize_for_log`).
- Heavy deps import-guarded; endpoints fail soft with typed HTTP status codes.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-02 | Claude (session) | `src/bio_neural/routes.py`, `consciousness_engine.py`, `neuromorphic.py`, `api.py` mount | Routes, classes, mount point, and the PARTIAL neuromorphic/phi fallbacks verified against code |
