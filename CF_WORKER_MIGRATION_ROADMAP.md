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
  Worker, including the emotion/consciousness/tokenize/predict routes. This
  **is** Traefik-routed (`PathPrefix(/api/ai)`) and functional — it is the
  worker actually reachable at the CF Worker's old path today.
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
- **`workers/the-void/`** — a standalone 289-line Python implementation.
  **Not** referenced anywhere in `docker-compose.production.yml`. Not
  mentioned in `CLAUDE.md`. This is the only one of the four that is
  genuinely dead code.

**This needs an explicit decision, not a cleanup**: three different vault
services are live simultaneously (`infinity-void` behind the gateway,
`vault-service` reachable only directly, `vault-service-rs` behind a
separate un-gatewayed path). Which one secrets actually get written to
today is unclear from the code alone — that depends on which URL each
consumer worker was configured to call, which this audit did not trace.
Deleting any of the three live services without first confirming no
consumer depends on it risks silent data loss. Only `workers/the-void/`
(never deployed) is safe to remove outright.

## 3. `trancendos-api-gateway` (routing / auth / rate-limiting)

The CF Worker implements `AuthService`, `RateLimiter`, and `CircuitBreaker`
classes in front of the platform's other CF Workers.

Three self-hosted mechanisms exist, each partially overlapping:

- **Traefik native routing** — per-service `PathPrefix` router labels in
  `docker-compose.production.yml`. Does path routing only; no auth,
  rate-limiting, or circuit-breaker logic.
- **`workers/api-gateway/`** (port 8003) — a Python port of the CF gateway's
  auth/rate-limit/circuit-breaker logic, itself also Traefik-routed at a
  catch-all `PathPrefix(/api/)` (lower priority than the dedicated
  `/api/backend`, `/api/ai`, `/api/void`, `/api/infinity-ai` routers, so it
  doesn't currently conflict — Traefik's longest-prefix-wins default
  handles the overlap correctly).
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
