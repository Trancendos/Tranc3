# Data Transfer Matrix

> **What this is.** A narrow, honest look at cross-border data transfer for a platform that is
> currently single-operator with no confirmed multi-region user base. This document does not
> attempt a formal Standard Contractual Clauses (SCC) or adequacy-decision assessment — that would
> be premature paperwork for a userbase that doesn't yet exist at that scale. What it does do is
> document real data-locality facts already true today, and one genuine finding: a fully-built data
> residency enforcement module that exists in code but isn't mounted anywhere.

**Owner:** Trancendos Platform Engineering · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Where data actually lives today

| Component | Location | Basis |
|---|---|---|
| `tranc3-backend` / `tranc3-bots` (Fly.io, legacy path) | London, UK (`lhr`) | `fly.toml`: `primary_region = "lhr"` |
| Cloudflare Workers (26 legacy, see `CLAUDE.md`) | Cloudflare's global edge network | Workers execute at whichever edge node is nearest the request — this is CDN-style compute, not a chosen data-residency decision |
| Self-hosted workers (`docker-compose.production.yml`) | Wherever The Citadel/OCI host physically is | Single-host deployment; no cross-region replication exists |
| SQLite files (see `docs/governance` — Database Registry, `src/backup/registry.py`) | Local disk on whichever host runs that worker | No managed multi-region database service is in use |

**Practical read:** this platform does not currently transfer personal data across jurisdictions
in the sense SCC/adequacy assessments exist for — there is one primary compute location (or
Cloudflare edge caching, which doesn't persist PII), not a multi-region architecture moving user
data between jurisdictions.

## 2. Finding: `src/storage/data_residency.py` exists, is well-built, and is unwired

A complete data-residency enforcement module already exists:

- `DataResidencyMiddleware` — ASGI middleware that blocks `POST`/`PUT`/`PATCH`/`DELETE` requests
  with a 403 when the active region (`DATA_RESIDENCY_REGION` env var, default `eu-west`) isn't in
  the allowed list (`DATA_RESIDENCY_ALLOWED_REGIONS`, default `eu-west,eu-central`), and stamps
  every response with an `X-Data-Residency-Region` header.
- `enforce_residency()` / `@residency_required` — a function-level check and decorator for the
  same enforcement outside the middleware path.
- `region_namespaced_path()` / `ensure_region_dir()` — helpers to namespace on-disk storage paths
  by region (e.g. `/data/users.db` → `/data/eu-west/users.db`).
- Audit integration — violations and allowed writes both emit an Observatory event
  (`data_residency_violation` / `data_residency_write`).

**It is not imported anywhere** — not in `api.py`, not in any router, not in any worker. `grep`
confirms zero call sites outside the module itself. This mirrors this session's earlier
`CapacityGuard` finding (`docs/governance/THRESHOLD-MATRIX.md` §5): a real, complete mechanism that
was built and then never wired in.

**One thing that *is* wired:** `scripts/soc2_evidence_collector.py`'s `collect_data_residency()`
reads the same `DATA_RESIDENCY_REGION`/`DATA_RESIDENCY_ALLOWED_REGIONS` env vars and produces the
`data_residency_YYYYMM.json` evidence artifact referenced in `docs/compliance/SOC2_TYPE_II.md`'s
retention schedule — so the *config* is real and evidenced even though the *enforcement* isn't
active.

## 3. Recommendation (not actioned this pass)

Unlike `CapacityGuard`, this module is **not** safe to wire in purely observationally —
`DataResidencyMiddleware` actively blocks writes with a 403 when misconfigured, so mounting it
without first confirming `DATA_RESIDENCY_REGION`/`DATA_RESIDENCY_ALLOWED_REGIONS` are set correctly
in every environment risks 403-ing all writes platform-wide. This needs an explicit decision and a
staged rollout (warn-only first, `DATA_RESIDENCY_ENFORCE=false`), not an unattended wiring pass —
flagged here for a future session rather than actioned now.

## 4. Existing GDPR coverage (not duplicated here)

Consent management, Subject Access Request (SAR) and erasure endpoints, 90-day audit log
retention, and ICO registration status are already documented in
`docs/compliance/ISO27001_SOA.md` (controls 5.31, 5.34, 8.10), `docs/compliance/SOC2_TYPE_II.md`
(CC6.3, C1.2, P1.1, P4.2), and `docs/compliance/RISK_REGISTER.md`'s R-004. This document is
scoped to cross-border transfer only, to avoid re-documenting what those files already cover.

## 5. Cross-references

- `docs/governance/THRESHOLD-MATRIX.md` §5 — the CapacityGuard precedent for a dormant-but-real
  mechanism
- `docs/compliance/ISO27001_SOA.md`, `SOC2_TYPE_II.md`, `RISK_REGISTER.md` — GDPR controls this
  document deliberately doesn't repeat
- `docs/architecture/infrastructure-modes.md` — Cloud Only / Hybrid / Local deployment modes,
  relevant if a future Local/self-hosted mode changes the location facts in §1
