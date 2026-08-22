---
title: "Token Efficiency Matrix"
category: Reference
last-reviewed: 2026-07-30
status: needs-update
---

# Token Efficiency Matrix

> **What this is.** `docs/governance/THRESHOLD-MATRIX.md` §3 already documents per-provider rate
> *ceilings* (Groq 14,400 req/day, Cerebras 30 req/hour, etc.) — this document is the different,
> narrower angle: the mechanisms that make token *usage itself* efficient, so those ceilings are
> reached slower. It deliberately doesn't repeat THRESHOLD-MATRIX's tables.

**Owner:** Luminous (Cornelius MacIntyre) · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Response cache — `LRUCache` (`src/ai_gateway/gateway.py`)

An in-memory LRU cache (`max_size=1000` by default, `cache_size` constructor param) sits in front
of every AI Gateway request. `GatewayMetrics.cache_hits` counts hits directly — a cache hit costs
zero provider tokens. `TenantAIConfig.cache_enabled` (default `True`) is the per-tenant on/off
switch; disabling it is a legitimate choice for tenants needing guaranteed-fresh responses, at the
cost of every request consuming its full token budget.

## 2. Per-tenant daily token budget (`src/ai_gateway/types.py`)

`TenantAIConfig.daily_token_budget` + `tokens_used_today` — checked in
`gateway.py` (`if config.tokens_used_today >= config.daily_token_budget: raise
GatewayError("TOKEN_BUDGET_EXCEEDED", ...)`). Two real presets:

| Tenant config | Daily token budget | Route priority order |
|---|---|---|
| `DEFAULT_TENANT_CONFIG` | 100,000 | ollama → groq → gemini → cerebras → sambanova → openrouter → huggingface → offline |
| `FREE_TIER_CONFIG` | 10,000 | ollama → groq → offline |

The route order itself is a token-efficiency mechanism, not just a cost one: `ollama` (local,
zero-latency-to-quota) is tried before any rate-limited cloud provider, so most requests never
touch a budget-metered provider at all.

## 3. What "efficiency" means here — cost, not quality

This document is scoped to *token consumption efficiency* (cache hits, budget tracking, route
ordering) — it does not cover prompt-engineering quality, output correctness, or model selection
for capability reasons. Those are product decisions per-feature, not a platform-wide mechanism to
document here.

## 4. Gaps, honestly stated

- **No cross-tenant cache sharing analysis** — the LRU cache is a single in-process cache; whether
  it's actually effective (high hit rate) or mostly cache-misses in practice hasn't been measured
  (`GatewayMetrics.cache_hits` exists but no dashboard/report currently surfaces a hit-rate
  percentage).
- **Token-budget escalation is wired, but as a platform-wide aggregate, not per-tenant.**
  `src/ai_gateway/gateway.py`'s `_feed_capacity_guard()` (added alongside
  `provider_rotation.py`'s per-provider feed — `docs/governance/THRESHOLD-MATRIX.md` §5) mirrors
  every request's token usage into `CapacityService.AI_TOKENS_DAILY`, so CapacityGuard's 80/90/95/100%
  escalation ladder does fire against real traffic. `TOKEN_BUDGET_EXCEEDED` (the per-tenant hard
  stop above) remains fully authoritative and unaffected. The gap: `CapacityGuard.consume()` has no
  tenant dimension, so all tenants' usage lands in one shared counter — a genuinely per-tenant
  80%/90% warning band would need tenant-keyed state added to CapacityGuard itself, not attempted
  here.

## 5. Cross-references

- `docs/governance/THRESHOLD-MATRIX.md` §3 — per-provider rate ceilings (the numbers this document
  deliberately doesn't repeat)
- `docs/governance/HARD-STOP-MATRIX.md` §4 — CapacityGuard's 4-band escalation pattern, referenced
  in §4's gap above as a template for a future token-budget escalation band
- `docs/governance/COST-AND-REVENUE-GOVERNANCE.md` — the zero-cost enforcement this efficiency
  work supports (slower budget consumption = less pressure to ever reach a paid tier)
