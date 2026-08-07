# Duplicate Worker Findings — 2026-08-07 systematic sweep

**Status:** Open — decisions below need a human owner call, not a code fix. Nothing in this
doc has been silently resolved; see `docs/services/the-artifactory/README.md`'s Verification Log
(round 4) for what *was* fixed in the same pass (two dead Go workers deleted, `cranbania`
submodule-checkout gap fixed on 3 of 7 pytest-running workflows).

## Why this doc exists

The EA workbook (`docs/architecture/ea-workbook/`) covers only 6 of 90+ services in real depth.
A systematic structural duplication pass across all 92 `workers/` directories (cross-referenced
against `docker-compose.production.yml`'s 173 services) surfaced findings beyond the three that
prompted the sweep (`queue-service-go` — already deleted; `monitoring-go`/`rate-limit-service-go`
— deleted this pass; `bullmq-queue-service` vs `queue-service` — below). The findings below are
**live production services**, not dead code — deleting or consolidating any of them is an
infrastructure decision with real consequences (broken URLs, lost data paths), not a cleanup.

## 1. Three Rust workers run concurrently with their Python originals

Unlike `rate-limit-service-go`/`monitoring-go` (undeployed stubs, now deleted), these three Rust
(`Cargo.toml`) workers are **fully built, containerized, and Traefik-routed in
`docker-compose.production.yml` right alongside their Python equivalents** — both implementations
of the same logical service are live at once, on different routes:

| Rust worker | Port / route | Python original | Port / route |
|---|---|---|---|
| `rate-limit-service-rs` | 8099, `rate-limit-service-rs.trancendos.com` / `/rate-limit-rs` | `rate-limit-service` | 8026, routed via api-gateway |
| `vault-service-rs` | 8094, `vault-service-rs.trancendos.com` / `/vault-rs` | `vault-service` ("The Void") | 8038 |
| `nexus-ws-rs` | host `8100:8004`, `nexus-ws-rs.trancendos.com` / `/nexus-rs` | `infinity-ws` ("The Nexus") | 8004, routed at `api.trancendos.com/ws` |

`nexus-ws-rs`'s own compose comment literally says *"Nexus WebSocket hub (Rust) — The Nexus
real-time comms hub"* — same entity, same stated purpose as `infinity-ws`, different language.

**A second, independent compliance problem on top of the duplication:** all three Rust workers'
own `traefik.http.routers.*.rule` labels in `docker-compose.production.yml` route them via
`Host(...trancendos.com)` — genuine subdomains — not the `https://trancendos.com/<path>`
subdirectory scheme CLAUDE.md's Deployment Topology section mandates for every other Trancendos
service ("All Trancendos services are subdirectories of `trancendos.com`, not subdomains"). This
table documents that existing (non-compliant) routing accurately, on purpose — it is not proposing
new subdomains, and rewriting the URLs here to look like subdirectories would misdescribe how
these three services actually resolve today. Whichever option below is chosen, fixing the Traefik
`rule=` labels to match the subdirectory convention is part of the work, not a separate task.

**Why this matters:** two live implementations of a rate limiter, a secrets vault, and a
real-time comms hub is a materially worse state than an unwired stub — it means two independent
sources of truth for rate-limit counters, two independent AES-GCM vaults potentially holding
different secrets under the same logical name, and two WebSocket hubs a client could connect to
and get different peers on. Nothing in this repo's docs currently explains which one (if either)
is canonical, or whether the Rust workers are an intentional performance-rewrite-in-progress
migration path (in which case the Python originals should be marked deprecated-pending-cutover)
or an abandoned experiment nobody removed from compose (in which case the Rust services should be
removed).

**Recommendation, not yet actioned:** whoever owns `The Void`/`The Nexus`/rate-limiting should
decide and document one of:
1. Rust is the intended replacement — deprecate the Python service, migrate its Traefik route
   over, and delete the Python one once traffic is confirmed moved.
2. Rust was an experiment that should be removed — delete the 3 Rust services and their compose
   blocks/Traefik routes.
3. Both are intentionally kept for a specific reason (e.g. A/B performance testing) — document
   that reason and which one holds authoritative state, so an operator hitting either route knows
   what they're actually talking to.

## 2. `bullmq-queue-service` (Node) vs `queue-service` (Python) — same responsibility, no clear owner

Both are live, deployed, generic named-queue job systems:

- `workers/queue-service/worker.py` (Python/SQLite): self-identifies `WORKER_NAME = "the-hive"`,
  "Priority task queue with retry logic, dead-letter, and stuck-task sweep." Routes: `/enqueue`,
  `/dequeue`, `/complete`, `/fail`, `/status`, `/queues`.
- `workers/bullmq-queue-service/src/server.ts` (Node/TypeScript, Valkey/BullMQ-backed): header
  comment "Entity: The HIVE / Lead AI: The Queen." Routes: `POST /queues/:name/jobs`,
  `GET /queues/:name/jobs/:id`, `GET /queues/:name/counts`. Compose's own inline comment calls it
  a **"Node.js job queue scaffold for The HIVE."**

Neither compose block sets an env var (`QUEUE_SERVICE_URL`, `BULLMQ_*`, etc.) pointing any other
worker at either of them — as deployed today, **neither has an established consumer**, so this is
lower urgency than the Rust findings above (nothing is actively relying on a specific one being
authoritative yet), but the ownership boundary needs to be decided before anything starts
consuming either, or the same "two sources of truth" problem as above will recur.

**Not the same as `hive-service`:** `workers/hive-service/worker.py` also brands itself "The
HIVE," but its own docstring explicitly disambiguates: *"Bridge 3 — The HIVE (THIS): Data
movement and swarm system coordination... This is The HIVE — for data movement and swarm
coordination ONLY. AI/Agent/Bot traffic uses The Nexus. User traffic uses InfinityBridge."* That's
a data-routing bridge, not a job/task queue — a naming-collision false positive, not a third real
duplicate. Left alone.

**Recommendation, not yet actioned:** pick one of `queue-service`/`bullmq-queue-service` as the
canonical generic job queue, wire future consumers only to that one, and either delete the other
or repurpose it for a genuinely distinct role (the SQLite vs Valkey backends imply different
durability/throughput tradeoffs that could justify keeping both under different, non-overlapping
names — but that needs to be a stated decision, not silence).

## 3. Lower-priority findings from the same sweep (documented, not requiring a decision)

- **`monitoring` vs `health-aggregator`** — push-based alerting/dashboard vs pull-based active
  polling + cascade-failure prediction. Real overlap in "who's the source of truth for service
  health," but neither is a language-duplicate or unwired stub, so no urgency comparable to
  §1/§2. Worth a follow-up ownership decision (e.g. `health-aggregator` feeds `monitoring`'s
  alerting rather than running two independent dashboards).
- **`audit-service` vs `observatory`** — looked like a duplicate purely from CLAUDE.md's
  near-identical one-line descriptions of both as "The Observatory audit trail." The actual code
  is not duplicative: `audit-service` is a hash-chained tamper-evident audit log,
  `observatory` is a 7-backend observability/telemetry router (Tempo, Prometheus, Loki, etc.).
  CLAUDE.md's `observatory` description is the stale part, not the code — a doc fix, not a
  consolidation.
- **`langchain-integration-service`/`llamaindex-service`/`haystack-service`/`dspy-service`** and
  **`cache-service`/`storage-service`** — checked for overlap, confirmed genuinely complementary
  (distinct upstream frameworks; ephemeral cache vs durable storage). Not flagged.

## Scope note

~65 of the 92 `workers/` directories have unique, non-colliding names, are confirmed present in
`docker-compose.production.yml`, and were not individually read for finer-grained cross-service
responsibility overlap beyond a docstring/`Entity:` sweep (e.g. `ledger-service` vs
`payments-service`/`orders-service`, or `topology-service` vs `model-router-service` were not
checked). If a deeper pass is wanted, that's follow-up work, not covered here.
