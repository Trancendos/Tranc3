---
title: "GPU Matrix"
category: Reference
last-reviewed: 2026-07-30
status: needs-update
---

# GPU Matrix

> **What this is.** A map of which platform services genuinely need a GPU, which are CPU-first by
> design, and what actually happens today when no GPU is available — since the Zero-Cost
> Self-Hosted Architecture's founding constraint (CLAUDE.md's Fortiere section) is that GPU
> hardware is currently **not funded**: every deployment mode today is Cloud Only, and GPU-backed
> local inference is gated on the same server-funding blocker as the rest of the self-hosted path.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-27

---

## 1. Current reality: zero GPU in production

There is no GPU deployed anywhere in the live stack today. `docker-compose.production.yml`'s only
GPU-capable service, `vllm` (line 1884), ships behind an opt-in Docker Compose `profiles: [gpu]`
gate with its NVIDIA device reservation **commented out by default** (lines 1911–1918) — it does
not run unless someone both enables the `gpu` profile *and* uncomments the device block on hardware
that actually has an NVIDIA GPU. Every other AI Gateway provider in the priority chain (Ollama,
llama.cpp, Groq, Cerebras, SambaNova, Gemini, OpenRouter, Mistral, DeepSeek, HuggingFace, Together,
Cloudflare AI — `src/ai_gateway/provider_rotation.py`) is CPU/API-only. This matrix documents the
plan for when GPU funding lands, not a currently-running deployment.

## 2. Services that would benefit from GPU when funded

| Service | GPU use | Current fallback | Recommended foundation |
|---|---|---|---|
| **Luminous** (`src/bio_neural/`, Cornelius MacIntyre) | Local high-throughput LLM inference | AI Gateway's 12-tier CPU/API rotation (§3 below) | `vllm-project/vllm` — already the CLAUDE.md-recommended foundation and the only service actually wired into `docker-compose.production.yml`'s `gpu` profile |
| **Sashas Photo Studio** (Madam Krystal, image generation) | Stable Diffusion inference (ComfyUI primary, AUTOMATIC1111 fallback) | Offline placeholder as last resort (per CLAUDE.md) | GPU lives on the external ComfyUI/A1111 instance itself — `workers/sashas-photo-studio/main.py` only makes HTTP calls out to it, no GPU code in this repo. See Environmental Matrix §3 and the open MC-013 provenance item (`docs/governance/TRANCENDOS-MODELS-MATRIX.md` §10) for the compliance side of this integration |
| **TranceFlow** (Junior Cesar, 3D/games) | Godot Engine rendering, planned | Not yet integrated (CLAUDE.md: "Godot Engine integration planned") | `godotengine/godot` — CLAUDE.md-recommended; GPU need is deferred until the integration itself starts |
| **The Studio / Imaginarium** (Voxx) | Orchestrates the above (Fabulousa + TateKing + TranceFlow + Studio + Photo) | Delegates to each sub-service's own fallback | No GPU need of its own — inherits whichever of the above it's calling |

No other of the 43 Locations has a GPU-shaped workload today. This table is exhaustive as of this
matrix's last-verified date, not a placeholder pending future entries.

## 3. CPU-first inference chain — the actual default path

Per CLAUDE.md's 5-tier AI Gateway summary and the fuller 12-provider rotation in
`src/ai_gateway/provider_rotation.py`:

```text
Ollama (local, zero-cost) → llama.cpp (local, GGUF, CPU) → Groq → Cerebras → SambaNova
  → Gemini Flash → OpenRouter :free → Mistral → DeepSeek → HuggingFace → Together AI
  → Cloudflare AI → Offline stub
```

vLLM sits at "Tier 0" alongside llama.cpp/Ollama in `.env.example`'s own tier comments, but unlike
those two it requires the `gpu` Compose profile — so in practice, on hardware without a GPU, the
chain above (all CPU/API) is what actually serves every request.

**This chain is `provider_rotation.py`'s own order — not the only one in the codebase.** At least
three other, independently-configured provider orderings exist and do not match it or each other:
`src/core/config.py`'s default (`"ollama,openrouter,huggingface,stub"`),
`src/core/ml_pipeline.py`'s hardcoded `["tranc3", "ollama", "openrouter", "huggingface", "groq"]`,
and `workers/infinity-ai/service.py`'s own documented chain (`ollama → groq → cerebras →
openrouter → huggingface → together → deepseek → offline`). This is the same category of
duplication as the circuit breakers (`docs/architecture/decisions/TASD-001-circuit-breaker-consolidation.md`)
— multiple independent implementations of "the" fallback order that have drifted apart — flagged
here honestly rather than picking one and presenting it as canonical when the code doesn't agree.
Consolidating them is a real future pass, not attempted in this document.

## 4. VRAM / cost budgets — not yet meaningful to set

No VRAM budget, per-model memory ceiling, or cost-per-GPU-inference tracking exists anywhere in the
codebase (verified by direct search — nothing in `src/capacity/guard.py`'s `CapacityService` enum,
nothing in `src/ai_gateway/`). Setting one now would be inventing numbers with no hardware to
validate them against. **Recommendation, not built this pass:** once GPU hardware is funded and
`vllm`'s device reservation is actually uncommented, add a `CapacityService.VLLM_VRAM_BYTES` (or
equivalent) entry to `src/capacity/guard.py`'s `_DEFAULT_LIMITS` (see
`docs/governance/THRESHOLD-MATRIX.md` §4) sized to the real card's VRAM, not before. Tracking a
placeholder number here would be actively misleading rather than merely incomplete.

## 5. Cross-references

- CLAUDE.md's "Zero-Cost Self-Hosted Architecture (Fortiere)" section — the funding gate this
  entire matrix is downstream of
- `docs/governance/ENVIRONMENTAL-MATRIX.md` — the sustainability angle of eventually running local
  GPU hardware vs. today's cloud-provider-hosted CPU/API chain
- `docs/governance/THRESHOLD-MATRIX.md` §3 — the full free-tier provider limit table this chain
  rotates through today
- `docker-compose.production.yml` (vllm service, ~line 1884), `.env.example` (`VLLM_*` vars)
