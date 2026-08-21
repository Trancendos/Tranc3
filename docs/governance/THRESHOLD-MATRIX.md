---
title: "Threshold Matrix"
category: Reference
last-reviewed: 2026-07-30
status: needs-update
---

# Threshold Matrix

> **What this is.** A single rollup of every numeric threshold enforced anywhere on the platform —
> rate limits, capacity ceilings, circuit-breaker trip points, and model-advancement bars — that
> today live scattered across six-plus independent modules with no cross-reference between them.
> This document does not introduce new threshold *logic*; it is the map that was missing, plus a
> short list of genuine consolidation opportunities and one dormant system it makes visible again.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-27

---

## 1. Why this exists

Before this document, a question as simple as "what happens when Groq's free tier gets close to
its daily limit, and does anything alert on it?" required reading five unrelated files to answer.
Nothing here was broken — most of the individual mechanisms are well-built — but nothing tied them
together, and one of them (§5) turned out to be built and completely unused.

## 2. Billing / API rate limits — `src/monetisation/billing.py`

| Tier | Price (GBP/mo) | req/hour | req/day |
|---|---|---|---|
| free | £0 | 100 | 500 |
| pro | £29 | 1,000 | 10,000 |
| business | £149 | 10,000 | 100,000 |
| enterprise | custom | unlimited (`-1`) | unlimited (`-1`) |

Enforced by `check_rate_limit()` (`src/monetisation/billing.py:126`), which raises on the hourly
figure. These are **per-tenant API** limits — distinct from every other section below, which are
**platform-wide external-provider or internal-resource** limits.

## 3. AI provider rotation — `src/ai_gateway/provider_rotation.py`

Eleven free-tier providers, each with its own `ProviderLimit` (daily/hourly request or token
ceiling), rotated in priority order (LiteLLM → Ollama → Groq → Cerebras → SambaNova → Gemini Flash
→ OpenRouter → Mistral → DeepSeek → HuggingFace → Together AI → Cloudflare AI):

- **`stop_threshold = 0.80`** — rotate to the next provider once a provider hits 80% of its own
  limit (`should_rotate()`).
- **`hard_stop_threshold = 0.95`** — refuse to route to a provider at 95% (`is_available()`).
- 5 consecutive errors trigger a cooldown (`_consecutive_errors >= 5`).

Documented free-tier ceilings (from the module's own header comment): Groq 14,400 req/day, Cerebras
30 req/min, SambaNova 50K tokens/req, Gemini Flash 1,500 req/day, OpenRouter 200 req/day/model,
Cloudflare AI 10,000 neurons/day.

## 4. Capacity Guard — `src/capacity/guard.py` (see §5 — currently dormant)

A separate, more general 4-band escalation ladder, keyed by `CapacityService` rather than by
provider:

| Utilisation | Band | Action |
|---|---|---|
| ≥ 80% | WARNING | Observatory event, log only |
| ≥ 90% | ALERT | Observatory event (severity=WARNING) |
| ≥ 95% | CRITICAL | Observatory event (severity=CRITICAL) |
| ≥ 100% | HARD STOP | `CapacityExceededError` raised, further calls blocked |

Default limits (`_DEFAULT_LIMITS`, `src/capacity/guard.py:109`) cover Groq (14,400 req/day),
Gemini (1,500 req/day), Cerebras (1M tokens/day), SambaNova (500 req/day), OpenRouter (20 req/min),
HuggingFace (300 req/day), GitHub Models (150 req/day), plus platform-wide budgets: AI token budget
(100K/day default tenant), storage (10 GB default), file uploads (1,000/day), queue depth (10K
in-flight), and platform requests (10K/hour, 100K/day).

**Known doc/code drift:** `guard.py`'s own module docstring claims 90%+ crossings get "Cryptex
notified" — `_emit()` (`src/capacity/guard.py:255`) only ever calls `Observatory.record()`; there is
no Cryptex call anywhere in the file. Treat the docstring's Cryptex claim as aspirational, not
implemented, until `src/cryptex/` actually subscribes to `capacity.threshold_crossed` events.

## 5. The dormant system — CapacityGuard had zero callers

Before this pass, `CapacityGuard` (§4) was fully built, self-consistent, and had **zero call sites
anywhere in the codebase outside its own module** and **zero test coverage** — a real 4-band
escalation ladder that never actually ran. It's now wired additively from two independent feeds:

- `ProviderLimit.record_request()` (`src/ai_gateway/provider_rotation.py`) for the six providers
  that have a matching `CapacityService` entry (Groq, Cerebras, SambaNova, Gemini, OpenRouter,
  HuggingFace) — see `_feed_capacity_guard()` in that module.
- `AIGateway.route()` (`src/ai_gateway/gateway.py`) feeds every request's token usage into
  `CapacityService.AI_TOKENS_DAILY` — see that module's own `_feed_capacity_guard()` (same name,
  different module, both additive). This one is a **platform-wide aggregate**, not per-tenant:
  `consume()` has no tenant dimension, so all tenants land in one shared counter — see
  `docs/governance/TOKEN-EFFICIENCY-MATRIX.md` §4 for the honest gap this leaves.

Both feeds are intentionally **observational only**: neither raises, blocks a request, or changes
`provider_rotation.py`'s/`gateway.py`'s own rotation/hard-stop/budget decisions, which remain fully
authoritative. They exist purely so the 80/90/95/100% Observatory events actually fire against real
traffic instead of sitting unreachable. Covered by `tests/test_capacity_guard.py`,
`tests/test_provider_rotation_capacity_feed.py`, and `tests/test_ai_gateway_capacity_feed.py`.

## 6. Circuit breakers — four independent implementations (Phase 1 + 2 complete)

- `src/mesh/circuit_breaker.py`'s `CircuitBreaker` — generic per-service-name breaker, config via
  `CircuitBreakerConfig` (`src/mesh/types.py:48`): `failure_threshold=5`, `reset_timeout_ms=30000`,
  `half_open_success_threshold=3`.
- `src/validation/loop_validator.py`'s `CircuitBreaker` — a **separate class**, pre-instantiated
  with named breakers and per-breaker thresholds (`src/validation/loop_validator.py:255`):

| Breaker | `failure_threshold` | `recovery_timeout` |
|---|---|---|
| `model_inference` | 5 | 30s |
| `quantum_attention` | 3 | 10s |
| `consciousness_phi` | 5 | 15s |
| `database_write` | 3 | 60s |
| `redis_ops` | 5 | 30s |
| `stripe_api` | 3 | 120s |
| `evolution_cycle` | 10 | 60s |

- `src/nanoservices/circuit_breaker/circuit_breaker.py`'s `CircuitBreaker` — a **third, independent
  class** (with its own `CircuitBreakerMesh`, `CircuitConfig`, `CircuitMetrics`), found while
  extending the Nano Service Registry's discovery to cover this module — see
  `discover_library_nanoservices()` in `src/nanoservices/nano_registry.py`. Registered there as a
  `kind="library"` entry (no HTTP surface), not yet inspected for its own threshold defaults.
- `src/resilience/circuit_breaker.py`'s `CircuitBreaker` — a **fourth, independent class** (with
  its own `Bulkhead` + `ResilienceManager` companions, feeding `src/gateway/adaptive_proxy.py`),
  missed in an earlier pass of this table even though it was already covered by TASD-001.

**Consolidation status:** `docs/architecture/decisions/TASD-001-circuit-breaker-consolidation.md`
tracks this. Phase 1 (unify the `CircuitState` enum all four re-export, including harmonising
mesh's `"half-open"` → `"half_open"`) and Phase 2 (extract the one piece of logic genuinely
identical across all four — the OPEN→HALF_OPEN recovery-timeout check and a canonical structured
transition log, via `src/resilience/circuit_core.py`) are both done. Each breaker's
success/failure-counting semantics, half-open admission strategy, and config schema remain
deliberately distinct (see the ADR §2/§3.2) — full unification into one class (Phase 3) is
future work, not attempted here.

## 7. Model-governance advancement thresholds — `src/models/governance.py`

Distinct in kind from every threshold above: these gate a *decision* (should this AI's model
advance), not a resource ceiling.

| Constant | Value | Pipeline |
|---|---|---|
| `PRIME_MIN_ADVANCEMENT_PCT` | 3.0% | Standard (Tranc3) — Prime screen |
| `CORNELIUS_MIN_ADVANCEMENT_PCT` | 8.0% | Standard (Cornelius stage) + Cornelius-only (T2ance) |

See `docs/governance/TRANCENDOS-MODELS-MATRIX.md` §5 for the full pipeline. As of this pass, a
third gate exists here too — see `TRANCENDOS-MODELS-MATRIX.md` §10 (provenance check, MC-013).

## 8. Zero-cost enforcement ceilings — `config/zero_cost/providers.yaml`

`quota_hard_stop: true`, `daily_request_limit_per_provider: 5000` — a coarser, config-level backstop
sitting above the per-provider limits in §3/§4; see `docs/governance/COST-AND-REVENUE-GOVERNANCE.md`
for the full zero-cost enforcement chain (`ZeroCostEnforcer.BLOCKED_SERVICES`,
`src/master_worker/zero_cost_enforcer.py`).

## 9. Rate limiter primitives — `src/shared/rate_limiter.py`

Three limiter strategies (`TokenBucketLimiter`, `SlidingWindowLimiter`, `FixedWindowLimiter`) plus
an adaptive `_TenantBucket` that self-tunes its rate based on observed error rate (retunes every 60s
if the error rate stays below 1% for 300s+). These are the primitives; §2's billing tiers are one
consumer of them. No duplicate implementation was found here (unlike §6) — `src/mesh/rate_limiter.py`
exists as a filename but was empty/non-substantive at time of writing.

## 10. Cross-references

- `docs/governance/HARD-STOP-MATRIX.md` — the subset of these thresholds whose 100% crossing
  actually halts something, unified across tiers
- `docs/governance/COST-AND-REVENUE-GOVERNANCE.md` — the cost/revenue side of §8
- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` — §7's advancement thresholds in full context
- `docs/governance/TOKEN-EFFICIENCY-MATRIX.md` — the token-consumption-efficiency side of §3's
  provider ceilings (cache hit rate, per-tenant budgets, route ordering) — a different angle on the
  same providers, deliberately not duplicated here
- `tests/test_capacity_guard.py`, `tests/test_provider_rotation_capacity_feed.py` — coverage for §5
