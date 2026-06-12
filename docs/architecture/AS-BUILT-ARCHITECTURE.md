# Tranc3 — As-Built Architecture

**Version:** 1.0.0 | **Classification:** UNCLASSIFIED — INTERNAL | **Date:** 2026-06-12

> This is the canonical as-built architecture document. Use this for audits. `docs/DOC-02-System-Architecture.md` is aspirational and may not reflect production state.

## 1. Platform Overview

Tranc3 is a self-hosted, zero-cost Python/FastAPI platform deployed as a Docker Compose stack. All services run as isolated FastAPI workers with SQLite local state. No shared database. No mandatory paid external services.

**Infrastructure backbone:**
- **Traefik** — TLS termination, reverse proxy, rate limiting (port 443/80)
- **HashiCorp Vault** — Secret management, Shamir unseal
- **Prometheus + Grafana** — Metrics + dashboards
- **Loki + Promtail** — Log aggregation
- **IPFS** — Distributed content storage

## 2. Worker Topology (As-Built)

### P0 — Always-on critical path

| Service | Port | Binary | DB | Replaces CF Worker |
|---|---|---|---|---|
| infinity-ws (The Nexus) | 8004 | `workers/infinity-ws/main.py` | SQLite | infinity-ws-api |
| infinity-auth (Infinity Core) | 8005 | `workers/infinity-auth/worker.py` | SQLite | infinity-auth-api |

### P1 — Core user-facing

| Service | Port | Binary | DB |
|---|---|---|---|
| infinity-portal-service | 8042 | `workers/infinity-portal-service/` | SQLite |
| infinity-one-service | 8043 | `workers/infinity-one-service/` | SQLite |
| infinity-admin-service | 8044 | `workers/infinity-admin-service/` | SQLite |
| infinity-shards-service | 8045 | `workers/infinity-shards-service/` | SQLite |
| users-service | 8006 | `workers/users-service/` | SQLite |
| monitoring | 8007 | `workers/monitoring/` | SQLite |
| notifications | 8008 | `workers/notifications/` | SQLite |
| infinity-ai | 8009 | `workers/infinity-ai/` | SQLite |
| infinity-bridge-service | 8070 | `workers/infinity-bridge-service/` | SQLite |
| cranbania (The Town Hall) | 8071 | `workers/cranbania/` | SQLite |
| hive-service (The HIVE) | 8060 | `workers/hive-service/` | SQLite |

### P2 — Extended platform

| Service | Port |
|---|---|
| the-grid | 8010 |
| products-service | 8011 |
| orders-service | 8012 |
| payments-service | 8013 |
| files-service | 8014 |
| identity-service | 8015 |
| gateway-service | 8040 |
| sentinel-station-service | 8041 |
| dimensional-nexus-service | 8050 |
| ffmpeg-worker | 8052 |
| swarm-coordinator-service | 8053 |

### P3 — Supporting services

rate-limit-service (8026), vault-service (8038), workflow-engine-service (8034), langchain-integration-service (8036), deepagents-orchestrator-service (8037), and 12+ others at ports 8016–8033.

## 3. Authentication Architecture

```
Browser → Traefik → infinity-portal-service (:8042)
                         ↓ [Infinity Gate — role-based routing, embedded]
                   ┌──── Admin  →  infinity-admin-service (:8044)
                   ├──── User   →  Arcadia (web/)
                   └──── DevOps →  Citadel (docker-compose)
                         ↓ [delegates credential verification to]
                   infinity-auth (:8005) — OAuth2/SSO/MFA engine
```

JWT tokens signed with `JWT_SECRET` (HS256). Zero Trust IAM in `src/auth/zero_trust.py` enforces device posture + geographic policies on every request.

## 4. AI Inference Architecture

```
Client → infinity-ai (:8009) → AIGatewayRouter (src/ai_gateway/)
         ↓ Tier 1: Ollama (:11434) — local, zero cost
         ↓ FAIL → Tier 2: HuggingFace free tier
         ↓ FAIL → Tier 3: OpenRouter :free
         ↓ FAIL → Tier 4: TRANC3_BACKEND_URL
         ↓ FAIL → Tier 5: OfflineProvider (stub)
```

LRU cache (1000 entries), circuit breaker per provider, token budgets per tenant.

## 5. Compliance Architecture

```
FastAPI app.py
  ├── MagnaCarta middleware (src/compliance/magna_carta.py)
  │     └── MC-RULE-001..009 evaluated per request
  ├── CABMiddleware (src/compliance/cab_gate.py)
  │     └── X-Change-ID required on admin/config/deploy mutations
  ├── ZeroTrust middleware (src/auth/zero_trust.py)
  │     └── JWT verification, device posture, risk scoring
  └── Compliance checker (src/compliance/checker.py)
        └── DEFSTAN + Magna Carta register evaluation
```

## 6. Data Architecture

- **No shared database.** Each worker owns `data/databases/<worker>.db`
- **WAL mode** enabled on all SQLite databases for concurrent reads
- **Secrets:** Vault at `workers/vault-service/` (port 8038) — AES-GCM encrypted
- **Audit trail:** The Observatory (`workers/monitoring/`, port 8007) — append-only log

## 7. Network Boundaries

```
Internet → Traefik (443/80) → [TLS termination]
                ↓
        Internal Docker network
                ↓
        Workers (8004–8080) — no direct internet exposure
                ↓
        SQLite / local filesystem (no external DB)
```

## 8. Payments Architecture (payments-service :8013)

Payments route **exclusively** through FCA-authorised PSP (Stripe). The `payments-service` holds no card data. All payment operations are delegated to the PSP API. See `docs/compliance/FCA-ALIGNMENT.md`.

## 9. Change History

| Date | Author | Change |
|---|---|---|
| 2026-06-12 | Trancendos | Initial as-built documentation |
