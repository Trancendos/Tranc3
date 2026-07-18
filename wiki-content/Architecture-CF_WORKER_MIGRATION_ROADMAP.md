# Cloudflare Worker Migration Roadmap
## Trancendos Platform — Zero-Cost Self-Hosted Architecture

> **Status note.** Every Location supports three deployment modes — Cloud Only (current
> default for all Locations), Hybrid, and Local/Self-Hosted. Migrating the workers below is
> the **Hybrid/Local path**, gated on funding a repaired or replacement local server — it is
> not a committed timeline, and the CF Workers this document maps are the correct, intentional
> Cloud Only implementation until that funding exists. Nothing here implies these workers are
> being abandoned or are "wrong" as currently deployed.

### Executive Summary

This document maps all 26+ deployed Cloudflare Workers to self-hosted Python/FastAPI equivalents, for when the platform moves a Location from Cloud Only toward Hybrid or Local mode. This eliminates all third-party dependencies that could incur costs, protects the zero-cost model, and gives full control over the platform.

**Strategy**: Replace Cloudflare Workers with Python FastAPI workers, SQLite for D1, in-memory/file storage for KV/R2, and the newly-ported Service Mesh for inter-worker communication.

---

## Migration Priority Matrix

| Priority | Criteria | Workers |
|---|---|---|
| **P0 — Critical** | Core platform functionality, auth, real-time | infinity-ws-api, infinity-auth-api, tranc3-ai (done), infinity-void (done), api-gateway (done) |
| **P1 — High** | User-facing services, monitoring, notifications | trancendos-users-service, infinity-monitoring-dashboard, trancendos-notifications-service, infinity-ai-api |
| **P2 — Medium** | Business logic, file management, identity | trancendos-products-service, trancendos-orders-service, trancendos-payments-service, infinity-files-api, infinity-os-identity, infinity-one |
| **P3 — Low** | Supporting services, can be stubs initially | infinity-hive, infinity-lighthouse, infinity-adaptive-intelligence, infinity-adminos-mesh, infinity-cost-monitor, the-grid-api, orchestrator, dpid-registry, arcadia-exchange, arcadia-royal-bank |

---

## Worker Migration Map

### ✅ Already Migrated (3/26)

| CF Worker | Self-Hosted Replacement | Port | Status |
|---|---|---|---|
| `tranc3-ai` | `workers/tranc3-ai/worker.py` | 8001 | ✅ Complete |
| `infinity-void` | `workers/infinity-void/worker.py` | 8002 | ✅ Complete |
| `trancendos-api-gateway` | `workers/api-gateway/worker.py` | 8003 | ✅ Complete |

---

### P0 — Critical Migration (2 workers)

#### 1. infinity-ws-api → workers/infinity-ws/worker.py (Port 8004)
- **CF Service**: WebSocket API for real-time communication
- **Maps to**: The Nexus
- **Features**:
  - WebSocket connection management (upgrade, heartbeat, close)
  - Channel-based pub/sub messaging
  - JWT authentication on WebSocket upgrade
  - Rate limiting per connection
  - Message broadcasting to channels
  - Connection state tracking
- **Replaces**: CF WebSocket Durable Objects
- **Zero-Cost**: FastAPI WebSocket + asyncio

#### 2. infinity-auth-api → workers/infinity-auth/worker.py (Port 8005)
- **CF Service**: OAuth2/SSO authentication API
- **Maps to**: Infinity (auth)
- **Features**:
  - OAuth2 authorization code flow
  - JWT token issuance and validation
  - Refresh token rotation
  - Session management
  - Multi-factor authentication (TOTP)
  - User registration and login
  - Password hashing (argon2)
  - Rate limiting on auth endpoints
- **Replaces**: CF Workers + KV session storage
- **Zero-Cost**: FastAPI + SQLite + python-jose

---

### P1 — High Priority Migration (4 workers)

#### 3. trancendos-users-service → workers/users-service/worker.py (Port 8006)
- **CF Service**: User management CRUD API
- **Maps to**: Infinity / user management
- **Features**: User profiles, preferences, roles, avatars, account management
- **Storage**: SQLite replaces D1

#### 4. infinity-monitoring-dashboard → workers/monitoring/worker.py (Port 8007)
- **CF Service**: Real-time monitoring dashboard
- **Maps to**: The Observatory
- **Features**: System metrics, health aggregation, alert management, log querying
- **Storage**: SQLite for metrics, in-memory for real-time data

#### 5. trancendos-notifications-service → workers/notifications/worker.py (Port 8008)
- **CF Service**: Push notification service
- **Maps to**: Notification hub
- **Features**: Email notifications (SMTP), in-app notifications, WebSocket push, notification preferences
- **Storage**: SQLite queue

#### 6. infinity-ai-api → workers/infinity-ai/worker.py (Port 8009)
- **CF Service**: AI API proxy
- **Maps to**: Luminous / AI API
- **Features**: AI inference proxy, model selection, request queuing, response caching
- **Integration**: Uses src/ai_gateway/ for routing

---

### P2 — Medium Priority Migration (5 workers)

#### 7. trancendos-products-service → workers/products-service/worker.py (Port 8010)
- **CF Service**: Products catalogue API
- **Maps to**: Arcadia / Products
- **Features**: Product CRUD, categories, search, pricing

#### 8. trancendos-orders-service → workers/orders-service/worker.py (Port 8011)
- **CF Service**: Orders management API
- **Maps to**: Arcadian Exchange / Orders
- **Features**: Order lifecycle, status tracking, order history

#### 9. trancendos-payments-service → workers/payments-service/worker.py (Port 8012)
- **CF Service**: Payment processing API
- **Maps to**: Royal Bank of Arcadia / Payments
- **Features**: Payment initiation, status, refunds, transaction history

#### 10. infinity-files-api → workers/files-api/worker.py (Port 8013)
- **CF Service**: File management API
- **Maps to**: DocUtari (files)
- **Features**: File upload/download, metadata, versioning, thumbnails
- **Storage**: Local filesystem replaces R2

#### 11. infinity-os-identity → workers/identity/worker.py (Port 8014)
- **CF Service**: Identity management
- **Maps to**: Infinity identity
- **Features**: Identity verification, profile management, attribute storage

---

### P3 — Low Priority Migration (14 workers — stubs initially)

#### 12. infinity-one → workers/infinity-one/worker.py (Port 8015)
- **Maps to**: Infinity main app
- **Stub**: Health check + service registry

#### 13. infinity-hive → workers/infinity-hive/worker.py (Port 8016)
- **Maps to**: The HIVE
- **Stub**: Health check + data transfer API stub

#### 14. infinity-lighthouse → workers/infinity-lighthouse/worker.py (Port 8017)
- **Maps to**: The Lighthouse
- **Stub**: Health check + token verification stub

#### 15. infinity-adaptive-intelligence → workers/adaptive-intelligence/worker.py (Port 8018)
- **Maps to**: Luminous / AI core
- **Stub**: Health check + adaptive AI stub

#### 16. infinity-adminos-mesh → workers/adminos-mesh/worker.py (Port 8019)
- **Maps to**: Admin mesh
- **Stub**: Health check + mesh status endpoint

#### 17. infinity-cost-monitor → workers/cost-monitor/worker.py (Port 8020)
- **Maps to**: The Observatory (costs)
- **Stub**: Health check + cost tracking stub

#### 18. the-grid-api → workers/grid-api/worker.py (Port 8021)
- **Maps to**: The Digital Grid API
- **Stub**: Health check + workflow status

#### 19. orchestrator → workers/orchestrator/worker.py (Port 8022)
- **Maps to**: The Nexus (orchestrator)
- **Stub**: Health check + orchestration stub

#### 20. dpid-registry → workers/dpid-registry/worker.py (Port 8023)
- **Maps to**: DocUtari (IDs)
- **Stub**: Health check + document ID registry

#### 21. arcadia-exchange → workers/arcadia-exchange/worker.py (Port 8024)
- **Maps to**: Arcadian Exchange
- **Stub**: Health check + exchange API stub

#### 22. arcadia-royal-bank → workers/royal-bank/worker.py (Port 8025)
- **Maps to**: Royal Bank of Arcadia
- **Stub**: Health check + financial API stub

#### 23. trancendos-api-gateway-production → workers/api-gateway-prod/worker.py (Port 8026)
- **Maps to**: API gateway (production)
- **Note**: Same as api-gateway with production config

#### 24. trancendos-products-service → (covered by #7)
#### 25. trancendos-orders-service → (covered by #8)
#### 26. trancendos-payments-service → (covered by #9)

---

## Implementation Notes

### Port Allocation
- 8000: Tranc3 backend (FastAPI main)
- 8001: tranc3-ai worker ✅
- 8002: infinity-void worker ✅
- 8003: api-gateway worker ✅
- 8004–8026: New workers (see above)

### Common Patterns
Every worker follows the same structure:
```
workers/<name>/
├── worker.py           # FastAPI application
├── Dockerfile          # Container config
└── requirements-worker.txt  # Python dependencies
```

### Shared Libraries
Workers import from `src/`:
- `src/mesh/` — Service mesh for inter-worker communication
- `src/event_bus/` — Event bus for async messaging
- `src/ai_gateway/` — AI routing with failover
- `src/auth/zero_trust.py` — Zero Trust enforcement
- `src/observability/` — Structured logging, metrics

### Storage Strategy
| CF Storage | Self-Hosted Replacement |
|---|---|
| D1 (SQL) | SQLite (file-based) |
| KV (key-value) | In-memory dict + SQLite backup |
| R2 (object) | Local filesystem + optional IPFS |
| Queues | asyncio.Queue + event bus |
| Durable Objects | FastAPI WebSocket + SQLite state |

### Authentication
All workers validate JWT tokens using the shared `src/auth/` module. The API gateway handles initial authentication and propagates user context via headers.

---

## Timeline

Phase ordering below is priority, not a scheduled/committed timeline — actual execution
starts once Hybrid/Local funding exists, per the status note at the top of this document.

| Phase | Workers | Estimated Effort |
|---|---|---|
| **Phase 1** | P0: infinity-ws, infinity-auth | 2 workers |
| **Phase 2** | P1: users, monitoring, notifications, ai-api | 4 workers |
| **Phase 3** | P2: products, orders, payments, files, identity | 5 workers |
| **Phase 4** | P3: All stubs | 14 workers |
