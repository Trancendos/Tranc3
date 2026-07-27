# Environmental Matrix

> **What this is.** The platform's sustainability/environmental posture, honestly split into what's
> actually known vs. what's a reasonable estimate vs. what's simply not tracked yet. Before this
> document, the entire footprint of the platform's environmental thinking was a single placeholder
> row in Magna-Carta's `EXTERNAL-FRAMEWORK-MAPPING.md` ("ESG impact of AI compute → Optional
> sustainability note in model cards") — a mapping suggestion, not an assessment. This matrix does
> not claim to have measured anything; it states plainly where real data would need to come from.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-27

---

## 1. Why zero-cost and low-environmental-impact aren't the same claim

CLAUDE.md's Zero-Cost Self-Hosted Architecture (Fortiere) optimizes for £0 spend, not for lowest
carbon footprint — the two often correlate (free-tier API calls to shared cloud infrastructure are
typically more energy-efficient per request than dedicated hardware sitting mostly idle) but they
are not the same axis, and nothing in the existing zero-cost documentation (`COST-AND-REVENUE-
GOVERNANCE.md`, `docs/ZERO_COST_VENDOR_MATRIX.md`) makes an environmental claim. This matrix is the
first place that does, and it does so cautiously.

## 2. Current deployment mode — Cloud Only, by CLAUDE.md's own admission

Every one of the 43 Locations is currently in **Cloud Only** mode (CLAUDE.md's Fortiere section):
"the founder's local server needs repair/replacement money that isn't available yet." That means
the platform's actual environmental footprint today is **entirely inherited from its hosting
providers** — Fly.io (region `lhr`) and Cloudflare Workers — not from any hardware Trancendos
itself operates. This matrix does not independently verify either provider's own environmental
claims (renewable-energy sourcing percentages, PUE figures, carbon-neutral commitments); it notes
that verifying them, if this becomes a real requirement, is a vendor-due-diligence exercise
belonging with `docs/ZERO_COST_VENDOR_MATRIX.md`, not a number to assert here without a source.

## 3. Per-mode qualitative comparison

| Mode | Status | Environmental characteristics (qualitative, not measured) |
|---|---|---|
| **Cloud Only** | Current default, all 43 Locations | Footprint is the hosting provider's shared-infrastructure efficiency; Trancendos has no operational control over it beyond choice of provider/region |
| **Hybrid** | Blocked on server funding | Mixes provider-inherited footprint with whatever the self-hosted portion draws locally; net effect depends entirely on the local hardware's efficiency and utilisation, neither of which exist yet to measure |
| **Local/Self-Hosted** | Blocked on server funding | Full operational control, and full operational responsibility — a poorly-utilised always-on local server can have a *worse* footprint than efficient shared cloud infrastructure at the same workload; this is not a given win and shouldn't be assumed as one purely because it's self-hosted |

The honest conclusion: **moving from Cloud Only toward Local/Self-Hosted is not automatically an
environmental improvement.** It trades a shared-infrastructure footprint (someone else's efficiency
problem to solve at scale) for a dedicated-hardware footprint (Trancendos's own efficiency problem
to solve at a much smaller scale, likely with lower average utilisation). This matrix flags that
trade-off explicitly rather than assuming the self-hosted/zero-cost narrative is automatically also
the green narrative.

## 4. GPU and the environmental angle

See `docs/governance/GPU-MATRIX.md` — no GPU runs in production today. If/when `vllm`'s NVIDIA
device reservation is uncommented (GPU-Matrix §1), that is the single highest-power-draw piece of
hardware anywhere in this architecture, and the point at which an actual power-draw figure (from
the GPU vendor's TDP spec, not an estimate) should be added here rather than deferred further.

## 5. What this matrix does not claim

- No carbon-footprint figure, in any unit, for any part of the platform.
- No PUE (Power Usage Effectiveness) figure for Fly.io or Cloudflare — their own published claims
  exist publicly but are not reproduced here without being fetched and cited at the time a real
  environmental review is scoped.
- No "carbon-neutral" or "green hosting" claim on Trancendos's own behalf. Any such claim would
  need to trace to the underlying providers' actual commitments, which is out of scope for this
  pass.

## 6. Recommendation for the next real step

The single most valuable next action here is not more documentation — it's picking one measurable
proxy (e.g., total AI Gateway request volume per month, from `src/capacity/guard.py`'s
`PLATFORM_REQUESTS_DAILY`/`PLATFORM_REQUESTS_HOURLY` counters, see
`docs/governance/THRESHOLD-MATRIX.md` §4) and mapping it against a published per-request energy
estimate from whichever provider serves the majority of that traffic. That would turn §5's "we
don't claim anything" into a real, if rough, first number. Not attempted this pass — it depends on
`docs/governance/THRESHOLD-MATRIX.md` §5's CapacityGuard feed actually accumulating real traffic
data first, which as of this matrix's date it has only just started doing.

## 7. Cross-references

- CLAUDE.md's Fortiere / Zero-Cost Self-Hosted Architecture section — the deployment-mode
  definitions this matrix maps onto
- `docs/governance/GPU-MATRIX.md` — the hardware most likely to change this matrix's numbers first
- `docs/governance/THRESHOLD-MATRIX.md` §4–5 — the request-volume counters §6's recommendation
  depends on
- `docs/ZERO_COST_VENDOR_MATRIX.md` — where a real per-vendor environmental due-diligence pass
  would belong
