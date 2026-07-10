# CF Worker → Self-Hosted Migration Roadmap

This document tracks the actual, code-verified migration status of the three
Cloudflare Workers `CLAUDE.md` marks "legacy, being decommissioned." It replaces
speculative status claims with what a direct audit of the deployed code found.

Audited 2026-07-09 by reading `cloudflare/<name>/` (the CF Worker source),
the corresponding `workers/` self-hosted replacement(s), and
`docker-compose.production.yml`'s actual Traefik wiring — not documentation
claims.

## Summary table

| CF Worker | Self-hosted status | Blocking issue |
|---|---|---|
| `tranc3-ai` | ~60% — functionally covered, but split across two implementations | `infinity-ai` (the intended successor) has no Traefik route |
| `infinity-void` | ~90% — functionally complete | Three parallel implementations exist; only one is canonical |
| `trancendos-api-gateway` | ~50% — routing exists, but duplicated three ways | No single source of truth for auth/rate-limiting |

## 1. `tranc3-ai` (AI edge proxy)

The CF Worker (`cloudflare/tranc3-ai/src/index.js`) exposes
`/api/v1/ai/{chat,embeddings,analyze-emotion,consciousness,tokenize,predict}`
with JWT verification against `infinity-auth-api` and stub fallbacks.

Two self-hosted things exist:

- **`workers/tranc3-ai/`** (port 8001) — a near-verbatim Python port of the CF
  Worker, exposing the same paths the CF Worker did
  (`/api/v1/ai/{chat,embeddings,analyze-emotion,consciousness,tokenize,predict}`).
  Its own Traefik router rule, `PathPrefix(/api/ai)`, does **not** actually
  match those paths (`/api/v1/ai/...` doesn't start with `/api/ai`), so this
  route is currently unreachable. The paths work anyway because
  `workers/api-gateway/`'s catch-all router (`PathPrefix(/api/)`, explicit
  `priority=1`) matches first and proxies `/api/v1/ai/*` to
  `TRANC3_AI_SERVICE_URL` → `tranc3-ai`, confirmed in
  `workers/api-gateway/router.py`. So the legacy CF paths are reachable
  today, but via the api-gateway proxy, not the dedicated `tranc3-ai`
  Traefik route as originally stated here.
- **`workers/infinity-ai/`** (port 8009) — a different, more modern design
  (5-tier `AIGatewayRouter`, LRU cache, token budgets) exposing an
  OpenAI-compatible `/v1/chat/completions` surface. This is the worker
  `CLAUDE.md`'s routing table names as the `tranc3-ai` successor. It covers
  chat only — no emotion/consciousness/tokenize/predict equivalents exist
  here. **Fixed 2026-07-09**: this worker had no Traefik labels at all (only
  reachable directly on :8009); it's now routed at `/api/infinity-ai`
  (stripped prefix) — see `docker-compose.production.yml`.

**Open decision**: are `tranc3-ai` and `infinity-ai` two workers that stay
(different API surfaces, both legitimate), or should `tranc3-ai`'s
non-chat routes be ported into `infinity-ai` and `workers/tranc3-ai/`
retired? Not resolved by this audit.

## 2. `infinity-void` (encrypted secrets vault)

The CF Worker uses AES-256-GCM + PBKDF2 (100k iterations) over a D1-backed
schema.

**Correction (2026-07-09): this is not three candidates with one deployed —
it's three vault services simultaneously live in production**, plus one
genuinely dead one:

- **`workers/infinity-void/`** (port 8002) — faithful port of the CF
  Worker's AES-256-GCM/PBKDF2 crypto and schema. Deployed, Traefik-routed at
  `/api/void`.
- **`workers/vault-service/`** (port 8038) — an OpenBao (HashiCorp Vault
  fork) wrapper. Deployed in compose but has **no Traefik labels** — only
  reachable directly on :8038, not through the gateway path. Its own
  `DEPRECATED.md` (dated 2026-06-14) says it's "superseded by
  `workers/the-void/`" — but `the-void` is the one thing in this list that
  is *not* deployed, so the deprecation note doesn't match what's actually
  running.
- **`workers/vault-service-rs/`** (port 8094) — a Rust reimplementation,
  compose comment labels it "The Void — Rust/AES-GCM vault service."
  Deployed, Traefik-routed at `/vault-rs`. Functionally the same concept as
  `infinity-void` (AES-GCM, no external unseal step) but a second,
  independent implementation of it in a different language.
- **`workers/the-void/`** — a standalone 289-line Python implementation. Not
  referenced anywhere in `docker-compose.production.yml`. Not mentioned in
  `CLAUDE.md`'s routing table — **but** `SECURITY.md` (line 112) explicitly
  names it the "canonical vault," and `workers/vault-service/DEPRECATED.md`
  names it as that migration's intended target. So this is not dead code by
  design intent — it's the documented target state of an apparently
  never-completed deployment. It is simply not currently deployed in
  production compose, which itself contradicts `SECURITY.md`'s "canonical"
  claim.

**This needs an explicit decision, not a cleanup**: four vault-related
artifacts disagree with each other. Three services are live simultaneously
in production (`infinity-void` behind the gateway, `vault-service` reachable
only directly, `vault-service-rs` behind a separate un-gatewayed path), none
of which is `SECURITY.md`'s stated canonical (`the-void`, which isn't
deployed at all). Which service secrets actually get written to today is
unclear from the code alone — that depends on which URL each consumer
worker was configured to call, which this audit did not trace. Do not
delete any of these four without first (a) reconciling `SECURITY.md`'s
claim against actual deployment, and (b) confirming no consumer depends on
whichever is removed.

## 3. `trancendos-api-gateway` (routing / auth / rate-limiting)

The CF Worker implements `AuthService`, `RateLimiter`, and `CircuitBreaker`
classes in front of the platform's other CF Workers.

Three self-hosted mechanisms exist, each partially overlapping:

- **Traefik native routing** — per-service `PathPrefix` router labels in
  `docker-compose.production.yml`. Does path routing only; no auth,
  rate-limiting, or circuit-breaker logic.
- **`workers/api-gateway/`** (port 8003) — a Python port of the CF gateway's
  auth/rate-limit/circuit-breaker logic, itself also Traefik-routed at a
  catch-all `PathPrefix(/api/)` with an explicit `priority=1` label — lower
  than the default rule-length-based priorities of the dedicated
  `/api/backend`, `/api/void`, `/api/infinity-ai` routers, so it doesn't
  currently conflict with them. It's worth noting this catch-all is also
  what actually makes `tranc3-ai`'s legacy paths reachable today (see §1
  above) — `workers/api-gateway/` isn't purely redundant with the dedicated
  routers, it's load-bearing for at least one of them.
- **KrakenD** (`config/krakend/krakend.json`, port 8099/8090) — also
  implements JWT + rate-limiting, explicitly commented in its config as
  "replaces CF trancendos-api-gateway," but is not behind Traefik and is not
  referenced anywhere in `CLAUDE.md`'s routing table.

In practice: most individual workers (cache-service, cdn-service,
infinity-ai, infinity-void, etc.) already do their own `X-Internal-Secret`
header auth independently, so the CF gateway's centralized `AuthService` is
largely redundant with per-worker auth that already exists. This weakens
the case for needing either `workers/api-gateway/` or KrakenD as a hard
dependency, but a final call on which (if either) survives has not been
made.

**Recommendation**: treat Traefik native routing + per-worker
`X-Internal-Secret` auth as the primary path (matches the pattern most
already-complete workers use). `workers/api-gateway/` and KrakenD are
architecturally redundant with each other and with the per-worker auth
pattern; retiring one or both is worth doing but is a deployment change
that needs explicit confirmation before removal, not just a documentation
note.

## Known non-blocking items

- **R2 storage**: not enabled on the Cloudflare account (`r2_buckets_list`
  fails; requires a one-time manual dashboard toggle). Nothing in the
  current self-hosted architecture appears to require it — `storage-service`
  uses local filesystem per the zero-cost design — so this is not currently
  blocking anything.
