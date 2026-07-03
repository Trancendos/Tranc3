# Service Doc-Pack — The Nexus (WebSocket Communication Hub)

| Field | Value |
|---|---|
| **Entity** | The Nexus (`PID-NXS`) |
| **Lead AI** | Nexus-Prime (`AID-NXS-01`); Prime: Cornelius MacIntyre |
| **Status** | 🔧 Self-hosted (per `CLAUDE.md` service table) |
| **Code** | `workers/infinity-ws/worker.py` |
| **Port** | 8004 (Dockerfile `EXPOSE` + `uvicorn.run(..., port=8004)`); Traefik `PathPrefix('/ws/')` in `docker-compose.production.yml` |
| **Replaces** | Cloudflare `infinity-ws-api` (zero-cost — FastAPI WebSocket + asyncio, no CF Durable Objects) |

> **Truthfulness:** every claim cites `workers/infinity-ws/worker.py`. Status is owned by the
> `CLAUDE.md` service table; identity by `PLATFORM_ENTITIES.md`. Note the running `/health` payload
> reports `lead_ai: "The Nexus"` (the location name) — the canonical Lead AI is **Nexus-Prime**
> (location and Lead AI are tightly coupled and share the name in `PLATFORM_ENTITIES.md`).

## 1. Service Governance Charter (GOV)

- **Mission:** real-time AI communications + transfer hub — WebSocket connection management,
  channel pub/sub, and message broadcast for the platform.
- **Owner (RACI-A):** Nexus-Prime (Lead AI); Prime Cornelius MacIntyre.
- **Scope:** a single FastAPI worker (`The Nexus — WebSocket API` v1.0.0) exposing a JWT-authenticated
  WebSocket plus internal HTTP status routes.

## 2. Detailed Design Document (DDD)

### HTTP / WS surface (`workers/infinity-ws/worker.py`)
| Method | Route | Auth | Backing |
|---|---|---|---|
| GET | `/health` | **public** | connection/channel counts + entity block |
| GET | `/stats` | `X-Internal-Secret` (when `INTERNAL_SECRET` set) | `ConnectionManager.stats` |
| GET | `/channels` | `X-Internal-Secret` (as above) | `ConnectionManager.get_channels()` |
| WS | `/ws?token=&user_id=` | **JWT** (HS256) on upgrade | `websocket_endpoint` → `ConnectionManager` |

- `/stats` and `/channels` are mounted on an `APIRouter(dependencies=[Depends(require_internal_auth)])`;
  `require_internal_auth` is a **no-op unless `INTERNAL_SECRET` is set** (then it 401s on mismatch).
  `/health` is registered directly on `app` and is always open.

### ConnectionManager
- State: `channel → set[WebSocket]` (`_channels`), `WebSocket → set[channel]` (`_subscriptions`),
  `WebSocket → metadata` (`_connections`), and `WebSocket → (count, window_start)` for **per-connection
  message rate limiting** (`_msg_rate` / `is_message_rate_limited`).
- Methods: `connect`, `disconnect`, `subscribe`, `unsubscribe`, `broadcast`,
  `_broadcast_to_channel`, `get_user_channels`.
- `WSMessage` is a Pydantic envelope for messages.

### Auth
- **WebSocket:** JWT via `pyjwt` (`verify_token`, `algorithms=["HS256"]`, keyed by `JWT_SECRET`);
  `ExpiredSignatureError`/`InvalidTokenError` return `None` (rejected). `JWT_SECRET` is **required** —
  the worker **raises a `RuntimeError` and fails fast at import/startup** if it is unset.
- **Internal HTTP:** shared `X-Internal-Secret` header on `/stats` + `/channels`.

## 3. Technical Architecture Solutions Design (TASD)

- **Style:** single stateless-ish FastAPI worker; connection state is **in-process** (dicts keyed by
  `WebSocket`). A Rust rewrite exists in-repo (`workers/nexus-ws-rs/`, also port 8004) — the two are
  alternative implementations of the same hub, not co-running services.
- **Observability:** optional OpenTelemetry via `instrument_worker(app, service_name="tranc3.infinity-ws")`,
  wrapped in try/except so OTel absence never blocks startup.
- **CORS:** `CORSMiddleware` with origins from `CORS_ORIGINS` (default `http://localhost:3000`).

## 4. RACI Matrix

| Activity | Nexus-Prime (Lead) | Platform Owner | The Chaos Party | The Observatory |
|---|---|---|---|---|
| WS connection/channel logic | **R/A** | C | R | I |
| Auth (JWT + internal secret) | **R/A** | C | R | I |
| Incident (hub down) | **R** | I | C | **A** |

## 5. Solutions Integration Model (SIM)

- **Upstream:** clients connect to `/ws` with a JWT minted by Infinity; internal services call
  `/stats`/`/channels` with `X-Internal-Secret`. Traefik routes `PathPrefix('/ws/')` to the worker.
- **Downstream:** broadcasts messages to subscribed channel members; emits OTel spans to The Observatory.
- **Auth boundary:** JWT on the socket; shared secret on internal HTTP; `/health` open for liveness.

## 6. Architecture Scalability Document (ASD)

- **Load model:** memory scales with concurrent connections × subscriptions; broadcast is O(members).
- **Scaling levers:** per-connection message rate limiting caps abuse; connection/channel counts exposed
  via `/health` + `/stats`.
- **Bottleneck / caveat:** connection state is **per-process** — horizontal scaling needs a shared
  fan-out (e.g. The HIVE / a broker) for cross-instance broadcast; not present today (**PLANNED**).
- **Zero-cost limits & hard stops:** no CF Durable Objects; pure asyncio. Rate limiting is in-process.

## 7. Technology Framework Matrix (TFM)

| Concern | Choice | Zero-cost stance |
|---|---|---|
| Transport | FastAPI WebSocket + asyncio | OSS |
| Auth | `pyjwt` HS256 | in-process |
| Message model | Pydantic `WSMessage` | in-process |
| Tracing | OpenTelemetry (optional) | self-hosted collector |

## 8. Policy (POL)

- Reuses platform policy (`POL-AI-001`, `docs/defstan/`). `JWT_SECRET`/`INTERNAL_SECRET` come from the
  environment/vault; never hard-coded. No paid transport dependency.

## 9. Procedure (PROC)

- **Add a channel operation:** extend `ConnectionManager` (keep `_channels`/`_subscriptions`/`_msg_rate`
  in sync) and route it through the WS handler; do not add cross-instance assumptions without a broker.

## 10. Runbook (RUN)

- **Startup crashes (`RuntimeError`) about `JWT_SECRET`:** the env var is unset — the worker fails fast
  at import and will not start; set it (`python -c "import secrets; print(secrets.token_hex(32))"`).
- **`/stats` / `/channels` return 401:** `INTERNAL_SECRET` is set and the caller's `X-Internal-Secret`
  header is missing/wrong.
- **Clients silently rejected on connect:** JWT invalid/expired (`verify_token` returns `None`); verify
  the token and `JWT_SECRET` match Infinity.
- **Broadcast reaches only some clients:** expected across replicas — state is per-process; use a single
  instance or add a shared fan-out.

## 11. Standards (STD)

- JWT HS256; secrets from env/vault. Per-connection message rate limiting enforced.
- OTel and CORS are configuration-driven; OTel failure is non-fatal.

## Verification Log

| Date | Verifier | Against | Result |
|---|---|---|---|
| 2026-07-03 | Claude (session) | `workers/infinity-ws/worker.py` (routes, `ConnectionManager`, `verify_token`, `require_internal_auth`, app/CORS/OTel), Dockerfile, `docker-compose.production.yml` | Routes, auth model, connection state, rate limiting, port, and Traefik routing verified against code |
