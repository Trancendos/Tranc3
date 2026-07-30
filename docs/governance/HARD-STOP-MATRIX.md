# Hard Stop Matrix

> **What this is.** A single map of every mechanism on the platform that can outright halt
> something — an AI, a request, a provider, a spend — rather than merely rate-limit or degrade it.
> Before this document these were five unrelated concepts that happened to share the word "stop":
> a Sovereign-tier kill switch, four independent circuit breakers, a quota-based request refusal,
> and a regex endpoint blocklist. Nothing here was broken; nothing was cross-referenced either.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-27

---

## 1. The five stop mechanisms

| # | Mechanism | Scope | What actually stops | Trigger |
|---|---|---|---|---|
| 1 | `emergency_stop()` | Trance-One → a Prime + its managed AIs | A T2ance Prime and everything it manages, cascaded | Manual call, `initiated_by` an orchestrator |
| 2 | Circuit breakers (×4 implementations) | Per-service-name or per-named-breaker | Calls to that one service/breaker only | Consecutive-failure count (see Threshold Matrix §6) |
| 3 | AI Gateway provider hard-stop | One AI provider (Groq, Gemini, …) | Routing to that provider only — rotates to the next | 95% of that provider's own quota (`hard_stop_threshold`) |
| 4 | CapacityGuard hard stop | One `CapacityService` resource | Raises `CapacityExceededError` on further `consume()` calls for that resource | 100% utilisation (see Threshold Matrix §4–5) |
| 5 | Zero-Cost Enforcer blocklist | Any outbound HTTP call matching a pattern | That specific call, before it's made | Endpoint URL matches a `BLOCKED_SERVICES` regex |

None of these five currently trigger each other's stop *decisions*. A Trance-One emergency stop
doesn't touch AI Gateway providers; a provider hard-stop doesn't touch circuit breakers; the
Zero-Cost blocklist is a pattern match, not a threshold. That's not necessarily wrong — they
operate at genuinely different layers — but it means there is no single place that answers "has
anything been hard-stopped right now," which is the gap this document closes by enumeration, and
the gap §6's recommendation closes structurally.

**One accounting-only exception:** `ProviderLimit.record_request()` (row 3's mechanism) now also
mirrors usage into row 4's `CapacityGuard.consume()` (`docs/governance/THRESHOLD-MATRIX.md` §5) —
that's a one-way data feed so CapacityGuard's Observatory escalation events fire against real
provider traffic, not a control-flow connection. Row 3's own 95% hard-stop decision remains fully
independent of row 4 and is unaffected by whatever CapacityGuard does with the mirrored numbers.

## 2. Sovereign-tier emergency stop — `src/entities/templates/trance_one_base.py`

`TrancOneBase.emergency_stop(target_aid, reason, initiated_by="orchestrator")`
(`trance_one_base.py:188`) is called **on** a Trance-One instance (Cornelius MacIntyre, The Queen,
or tAImra) to hard-stop a **Prime** (`target_aid`) and cascade to every AI that Prime manages.
Every call is recorded as an `EmergencyStopRecord` (`record_id`, `target_aid`, `reason`,
`initiated_by`, `initiated_at`, `cascaded_to`) kept in the Trance-One instance's own history — this
is the audit trail for tier-1 kill-switch actions. There is deliberately no equivalent method on
`t2ance_base.py` or `tranc3_base.py`: Tranc3/T2ance AIs are already subject to a Prime's or
Cornelius's direct HIL-A authority, so they don't need their own emergency-stop primitive — this
matrix documents that as an intentional design choice, not a gap.

This is distinct from — and does not currently coordinate with — the Governance Board's
Intervention system (`src/models/intervention.py`, see `docs/governance/TRANCENDOS-MODELS-MATRIX.md`
§8), which is the Board's *collective* authority over a malfunctioning Trance-One AI itself.
Together they cover both directions: Trance-One can hard-stop a Prime beneath it; the Board can
act on a Trance-One above the Primes. Recommendation (not actioned this pass): an `emergency_stop`
call is exactly the kind of event the Board's Intervention system should be able to see — consider
wiring `EmergencyStopRecord`s into `src/models/intervention.py`'s audit trail in a future pass so a
pattern of repeated stops on the same Prime is visible to the Board, not just to the one Trance-One
that issued them.

## 3. Circuit breakers — three unrelated classes, see Threshold Matrix §6

- `src/mesh/circuit_breaker.py`'s `CircuitBreaker` — generic, config-driven (5 failures / 30s
  reset / 3 half-open successes to close).
- `src/validation/loop_validator.py`'s `CircuitBreaker` — a different class, pre-instantiated with
  7 named breakers (`model_inference`, `quantum_attention`, `consciousness_phi`, `database_write`,
  `redis_ops`, `stripe_api`, `evolution_cycle`), each with its own threshold/timeout.
- `src/nanoservices/circuit_breaker/circuit_breaker.py`'s `CircuitBreaker` — a third, independent
  class found while extending the Nano Service Registry (see Threshold Matrix §6).

A breaker opening stops calls to exactly the one service/name it guards — the narrowest-scoped
"stop" on this list. See Threshold Matrix §6 for the full threshold table and the flagged
consolidation opportunity.

## 4. AI Gateway provider hard-stop — `src/ai_gateway/provider_rotation.py`

`ProviderLimit.is_available()` refuses routing to a provider once it hits 95% of its own daily,
hourly, or token limit (`hard_stop_threshold = 0.95`) — see Threshold Matrix §3. This is a soft
stop in effect (the Gateway rotates to the next of 11 providers), but a hard stop from that single
provider's point of view. Now feeds observationally into §5's CapacityGuard — see Threshold Matrix
§5.

## 5. CapacityGuard's 100% hard stop — `src/capacity/guard.py`

The only mechanism on this list that actually raises an exception on breach:
`CapacityGuard.consume()` raises `CapacityExceededError` at 100% utilisation of whichever
`CapacityService` it's tracking (Threshold Matrix §4 has the full limit table). Before this pass
this was unreachable dead code with zero callers; it's now fed observationally from AI Gateway
provider usage (Threshold Matrix §5) — but note its 100% raise is caught and swallowed at that
call site by design (the feed is observational-only), so today **no live code path actually lets
this exception propagate to a caller that would act on it.** That's an intentional scoping choice
for this pass, not an oversight: wiring a real caller that *does* act on `CapacityExceededError`
(e.g. `src/routers/`'s request-handling layer) is future work, tracked but not started.

## 6. Zero-Cost Enforcer blocklist — `src/master_worker/zero_cost_enforcer.py`

`BLOCKED_SERVICES` (`zero_cost_enforcer.py:42`) is a regex→reason dict checked against outbound
endpoint URLs — Azure/AWS/GCP paid compute, Cloudflare R2 overages, Bugzy AI, GitHub Actions,
Cloudflare Worker deploys, direct OpenAI/Anthropic/Cohere billing, direct DeepSeek, and
Together.ai's credit-based tier. This is a pre-flight blocklist (the call never happens), the only
mechanism here that acts *before* the fact rather than after a threshold is crossed. It also
enforces the module's own two escalation rules (>85% quota → pre-emptive rotation, >95% → immediate
rotation + alert) — see `docs/governance/COST-AND-REVENUE-GOVERNANCE.md` for the full zero-cost
enforcement chain this belongs to.

## 7. Recommendation: a single `/hard-stops` status surface

None of the five mechanisms above expose a unified "what is currently stopped, and why" view — each
has its own internal state (`_emergency_stops` list, per-breaker state, per-provider counters,
`CapacityGuard.status()`, no state at all for the regex blocklist since it's stateless). A future
pass could add a thin read-only aggregator (mirroring how `src/models/routes.py` exposes
governance/intervention state) that queries all five and returns one combined view — flagged here
as the natural next step, not built this pass, since it touches five independently-owned modules
and deserves its own review rather than being rushed in alongside this document.

## 8. Cross-references

- `docs/governance/THRESHOLD-MATRIX.md` — the numeric thresholds that trigger §3–§5
- `docs/governance/COST-AND-REVENUE-GOVERNANCE.md` — §6's full zero-cost enforcement chain
- `docs/governance/TRANCENDOS-MODELS-MATRIX.md` §8 — the Governance Board's Intervention system,
  the Board-side counterpart to §2's Trance-One-side emergency stop
- `tests/test_capacity_guard.py` — coverage for §5
