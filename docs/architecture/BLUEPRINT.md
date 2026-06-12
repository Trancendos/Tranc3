# Tranc3 Architecture Blueprint

**Version:** 1.0.0 | **Date:** 2026-06-12 | **Classification:** UNCLASSIFIED — INTERNAL

## 1. Vision

Tranc3 is the Trancendos platform engine: a zero-cost, fully self-hosted, multi-service AI platform deploying 38+ FastAPI workers, governed by Magna Carta runtime rules and DEFSTAN compliance requirements.

## 2. Architecture Principles

1. **Zero external cost by default** — All P0/P1 services operate on free/self-hosted infrastructure
2. **SQLite per worker** — No shared state, no distributed DB complexity
3. **Defense in depth** — ZeroTrust IAM + Magna Carta rules + CAB gate + Traefik WAF
4. **AI sovereignty** — 5-tier fallback ensures AI capability without paid APIs
5. **Compliance as code** — Register YAML + runtime checks, not just documentation

## 3. Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│                     INTERNET                         │
└────────────────────────┬────────────────────────────┘
                         │ HTTPS (443)
┌────────────────────────▼────────────────────────────┐
│              TRAEFIK (Reverse Proxy)                 │
│        TLS termination · Rate limiting · WAF         │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                COMPLIANCE LAYER                      │
│   ZeroTrust IAM · Magna Carta · CAB Gate             │
└────────────────────────┬────────────────────────────┘
                         │
┌──────────────┬──────────▼──────────┬────────────────┐
│   P0 Core    │    P1 User-facing   │   P2/P3 Extended│
│  :8004–8005  │    :8042–8071       │   :8010–8053   │
└──────────────┴─────────────────────┴────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                  DATA LAYER                          │
│   SQLite (per-worker) · IPFS · Local filesystem     │
└─────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│               OBSERVABILITY                          │
│   Prometheus · Grafana · Loki · The Observatory     │
└─────────────────────────────────────────────────────┘
```

## 4. Security Zones

| Zone | Services | Trust Level |
|---|---|---|
| DMZ | Traefik | Untrusted inbound |
| Application | P0–P3 workers | Internal authenticated |
| Data | SQLite, IPFS | Worker-local only |
| Management | Vault, Prometheus, Grafana | Admin-only |

## 5. Data Flow — User Authentication

```
User → POST /auth/login → infinity-portal-service (:8042)
     → infinity-auth (:8005) [OAuth2/MFA verification]
     → JWT issued (HS256, JWT_SECRET)
     → Infinity Gate routes by role
     → ZeroTrust middleware validates on every subsequent request
```

## 6. Data Flow — Compliant Mutation

```
Admin → PUT /admin/config → Traefik
     → CABMiddleware: requires X-Change-ID header
     → cab_gate.check_change(change_id) → approved bool
     → If approved: request proceeds
     → If not approved: 403 + CAB_REQUIRED error
     → The Observatory logs CAB decision + request metadata
```

## 7. Technology Stack

| Layer | Technology | Version | Cost |
|---|---|---|---|
| Runtime | Python | 3.11+ | Free |
| API framework | FastAPI | 0.115+ | Free |
| ASGI server | uvicorn | 0.30+ | Free |
| Database | SQLite | 3.x | Free |
| Proxy | Traefik | v3 | Free (open-source) |
| Secrets | HashiCorp Vault | 1.17 | BSL (free self-hosted) |
| Metrics | Prometheus | 2.x | Free |
| Dashboards | Grafana | 11.x | Free (open-source) |
| AI inference | Ollama | latest | Free |
| Container | Docker + Compose | 27.x | Free |

## 8. Compliance Stack

| Framework | Implementation | Register |
|---|---|---|
| DEFSTAN | `src/compliance/checker.py` | `compliance/register.yaml` |
| Magna Carta | `src/compliance/magna_carta.py` | `compliance/magna-carta/compliance/magna_carta_register.yaml` |
| ISO 27001 | Policy library | `docs/compliance/ISO27001_SOA.md` |
| GDPR | Privacy middleware | `docs/policies/POL-PRI-001-Data-Protection-Privacy.md` |
| SOC 2 | Evidence schedule | `docs/compliance/SOC2-EVIDENCE-SCHEDULE.md` |

## 9. Disaster Recovery

RPO: 24 hours (SQLite backup via cron-service)
RTO: 4 hours (Docker Compose redeploy from backup)
See: `scripts/dr_restore.py`
