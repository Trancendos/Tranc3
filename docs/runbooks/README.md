# Operational Runbooks — Trancendos Platform

> **Classification:** UNCLASSIFIED — PUBLIC  
> **Applies to:** DEF STAN 00-600 (Supportability) — REQ-SU-005  
> **Owner:** The Citadel / DevOps  
> **Review cycle:** Quarterly

This directory contains operational runbooks for all Tier-1 and Tier-2 Tranc3
platform services. Each runbook follows a standard structure aligned with
ITIL incident management and DEF STAN 00-600 supportability requirements.

## Index

| Runbook | Service | Priority | Port |
|---|---|---|---|
| [api-backend.md](api-backend.md) | tranc3-backend (FastAPI) | P0 | 8000 |
| [infinity-auth.md](infinity-auth.md) | Infinity Core Auth | P0 | 8005 |
| [infinity-ws.md](infinity-ws.md) | The Nexus (WebSocket) | P0 | 8004 |
| [infinity-portal.md](infinity-portal.md) | Infinity Portal + Gate | P1 | 8042 |
| [ai-gateway.md](ai-gateway.md) | AI Gateway (infinity-ai) | P1 | 8009 |
| [database.md](database.md) | PostgreSQL / SQLite stores | P1 | 5432 |
| [zero-downtime-deploy.md](zero-downtime-deploy.md) | Rolling deployment procedure | — | — |

## Runbook Template

Each runbook covers:
1. **Service overview** — purpose, dependencies, SLA
2. **Health check** — endpoint, expected response
3. **Start / stop / restart** — exact commands
4. **Common incidents** — symptom → diagnosis → resolution
5. **Escalation path** — who to contact, when
6. **Recovery procedures** — data backup, restore, rollback
7. **Monitoring** — key metrics, alert thresholds
