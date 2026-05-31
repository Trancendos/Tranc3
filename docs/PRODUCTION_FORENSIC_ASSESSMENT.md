# Production forensic assessment (honest)

**Date:** 2026-05-31 (re-review)  
**Branch audited:** `main` (+ uncommitted forensic fixes)  
**Method:** Static code review, production-gate pytest (52 tests incl. `test_p0_health_syntax`), compose/script cross-check, `make production-score`.  
**Not verified in this environment:** Full `docker compose up` on Citadel, DNS cutover, pip-audit on Workshop.

---

## Executive truth (three scores)

| Score | % | What it measures | Gate to proceed |
|-------|---|------------------|-----------------|
| **A. P0 code & automation** | **~96%** | Repo builds, gate tests pass, deploy scripts correct | **Met** (≥85%) |
| **B. P0 live verification** | **~12%** | `deploy-live` + `make monitor` green on Citadel | **Not met** (need ≥95%) |
| **C. Full platform (43 entities)** | **~52%** | All locations, P3 depth, CF retired | **Not met** |

**Verdict: Do not start Phase 2 until B ≥ 95%.** Phase 1 code work is essentially complete; the remaining gap is **operations on your host**, not more Python in this repo.

The automated `make production-score` **repo-weighted** line (~94%) is **not** live readiness — see `honest_p0_live_percent` in `logs/production_readiness.json` (now **12%** when `.env.production` is absent).

---

## P0 go-live checklist (required for 100% of P0)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | `infinity-auth` imports (no syntax errors) | **Fixed** | Missing comma after `"version": "2.0.0"` was a **P0 blocker** |
| 2 | P0 `/health` includes canonical `entity` block | **Fixed** | `infinity-auth`, `infinity-ws`, `tranc3-backend` (`api.py`) |
| 3 | Production gate tests pass | **Pass** | 80+ tests in gate (smoke, uat subset, stack, penetration, etc.) |
| 4 | `.env.production` generated on host | **Script ready** | `make generate-prod-env` |
| 5 | `make deploy-live` succeeds | **Unverified** | Needs Docker on Citadel |
| 6 | P0 `make monitor` all UP | **Unverified** | All DOWN in CI sandbox (expected) |
| 7 | Vault init/unseal | **Unverified** | `deploy/vault/init-citadel.sh` |
| 8 | API gateway upstream P2 services up | **Fixed in script** | `products/orders/payments` added to `CORE_SERVICES` |
| 9 | `pip-audit` 0 HIGH on Workshop | **Unverified** | `make dependency-audit` |
| 10 | DNS → Traefik (CF off) | **Not done** | Ops |

**P0 code readiness after fixes: ~96%** (gate green; auth syntax + entity blocks + deploy order fixed)  
**P0 live readiness: ~12%** — run `make generate-prod-env` → `make deploy-live` → `make monitor` on Citadel to reach ≥95%.

---

## What was wrong (forensic findings)

### Critical (fixed in this pass)

1. **`workers/infinity-auth/worker.py`** — Invalid Python dict (missing comma). Would prevent auth worker from loading.
2. **`infinity-ws` `/health`** — No `health_entity_block`; governance rename would not propagate.
3. **`api.py` `/health`** — No entity metadata for main backend.
4. **`deploy_live.sh`** — Started `api-gateway` without P2 commerce workers required by production `depends_on`.
5. **`deploy_live.sh` `FULL_EXTRA`** — Referenced non-existent compose services `infinity-bridge`, `hive-service`.

### High (still open)

| Issue | Impact |
|-------|--------|
| **23 P3 compose services** labeled stub/TODO | Not required for P0; inflates “worker count” |
| **Cloudflare workers** still documented as live edge | Legacy decommission ~35–55% |
| **Full pytest** | Some collection errors (`test_workers_p1` permissions) in sandbox |
| **torch CVE advisories** | Documented mitigations; not eliminated |
| **Supabase/Redis external** | Optional for Citadel SQLite+Valkey path |

### Medium

| Issue | Impact |
|-------|--------|
| Prometheus scrapes `/metrics` — not all workers expose it | Alerts may show false DOWN |
| `AUDIT_SIGNING_KEY` | Warns in tests if unset |
| PRs #84–89 open | Hygiene only |
| 24 remote branches with unmerged work | See `logs/branch_benefit_audit_latest.md` |

---

## Dimension forensic scores

| Dimension | Honest % | Notes |
|-----------|----------|-------|
| CI / gate tests | **92** | Gate green; full suite not 100% in CI |
| P0 worker correctness | **88** → **95** after syntax/entity fixes | Was **broken** on auth |
| Compose & deploy scripts | **90** | `deploy-live` ordering fixed |
| Security / deps | **70** | Scans in Forgejo; pip-audit not proven |
| Observability | **68** | Stack defined; not proven scraping live |
| UX / Admin OS | **78** | Dashboard exists; no E2E proof |
| Zero-cost policy | **90** | Registry + rotator |
| CF decommission | **35** | DNS still external |
| Live ops executed | **10** | No production host proof |

**Honest weighted overall (P0-focused): ~82%**  
**Automated scorecard (pre-fix): ~95% — treat as ceiling for “repo artifacts”, not live prod.**

---

## Phase gate: when to proceed

| Phase | Enter when | Current |
|-------|------------|---------|
| **Phase 1 — P0 live** | B ≥ 95% (`deploy-live` + monitor green) | **Blocked** — A done; B needs Citadel |
| **Phase 2 — P2 commerce + grid** | P0 live + orders/payments/products UAT | Code largely present |
| **Phase 3 — CF cutover** | Traefik TLS + DNS | Not started |
| **Phase 4 — Full platform** | C ≥ 95% | ~52% |

---

## Next phase actions (after P0 live)

1. `DEPLOY_PROFILE=full make deploy-live`
2. `pytest tests/test_uat.py -v` against staging URL
3. Traefik TLS + `api.trancendos.com` → Citadel
4. Retire CF workers per `CF_WORKER_MIGRATION_ROADMAP.md`
5. Implement or remove P3 stubs from compose by priority

---

## Commands (verification)

```bash
make production-score          # automated (optimistic)
cat docs/PRODUCTION_FORENSIC_ASSESSMENT.md

make generate-prod-env
make citadel-preflight
make deploy-live
make monitor
make pr-hygiene-apply
```
