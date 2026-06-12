# CranBania — The Town Hall

**Port:** 8071  
**Source:** https://github.com/Trancendos/CranBania  
**Lead AI:** Tristuran  
**Entity:** The Town Hall — Governance hub (PRINCE2, ITIL, Agile/Kanban, ITSM, rooms, templates)

## Overview

CranBania is a full-featured, zero-cost Kanban + ITSM + Agile board that implements
The Town Hall entity within the Trancendos platform. It is a TypeScript/Next.js
application with:

- Kanban board with card types: feature, bug, incident, change, epic, task
- Sprint management with burndown charts
- ITSM-lite: SLA timers, incident queue, SLA scheduler, breach escalation
- PRINCE2-lite governance layer
- Visual canvas boards (Lucid/Miro-style nodes + edges + presence)
- Workshop system with AI-assisted heuristic populate and template library
- MCP server (40+ tools) — registered with The Spark on startup
- Forgejo/Woodpecker CI — aligned with The Workshop
- Magna Carta alignment (see `docs/magna-carta-alignment.md` in CranBania repo)
- Import/export (JSON), webhook registry, Observer audit events

## Deployment

CranBania is deployed as a Docker service (`cranbania` in `docker-compose.production.yml`).
It builds from the CranBania repo (git submodule at `workers/cranbania/` or from the
cloned repo at this path).

### Add as git submodule (recommended)

```bash
git submodule add https://github.com/Trancendos/CranBania workers/cranbania
git submodule update --init --recursive
```

### Environment variables

See `.env.example` (CranBania section). Key vars:

| Variable | Required | Description |
|---|---|---|
| `CRANBANIA_PORT` | No | Port (default 8071) |
| `CRANBANIA_DATA_DIR` | Yes | Volume mount for board JSON data |
| `CRANBANIA_API_KEY` | Recommended | API authentication token |
| `CRANBANIA_CRON_SECRET` | Recommended | SLA scheduler CRON auth secret |
| `CRANBANIA_FORGEJO_URL` | No | The Workshop URL for CI dispatch |
| `CRANBANIA_WEBHOOK_SECRET` | No | Shared secret for Forgejo webhooks |
| `CRANBANIA_OBSERVATORY_URL` | No | The Observatory URL for audit events |

## MCP Registration with The Spark

CranBania exposes 40+ MCP tools via `mcp/server.ts` (stdio transport).
The Spark (`src/mcp/`) will discover and proxy CranBania tools when
`CRANBANIA_MCP_ENABLED=true` is set. Tools include:

- `list_board`, `board_summary`, `create_card`, `update_card`, `move_card`
- `get_card`, `get_card_journal`, `add_comment`, `add_code_change`
- `create_sprint`, `create_epic`, `list_backlog`
- `get_sla_report`, `run_sla_checks`
- `create_visual_board`, `add_visual_node`, `add_visual_edge`
- `start_workshop`, `run_workshop`, `list_workshop_templates`
- `register_webhook`, `export_workspace`
- ... and more

## Integration points

| Tranc3 entity | Integration |
|---|---|
| **The Spark** | CranBania MCP server registered as external tool source |
| **The Workshop** | Forgejo webhooks → CranBania cards; CI status on board |
| **The Nexus** | Optional WebSocket upgrade for real-time presence |
| **The Observatory** | `card.sla_breach`, `workshop.completed` events emitted |
| **Magna Carta** | Governance gate (POL-OPS-002) — change cards require CAB field |
| **Infinity Auth** | `CRANBANIA_API_KEY` or JWT via Infinity Portal |

## API

CranBania exposes a REST API at `http://localhost:8071/api/`:

| Endpoint | Method | Description |
|---|---|---|
| `/api/board` | GET | Full board state |
| `/api/cards` | GET/POST | List / create cards |
| `/api/cards/:id` | GET/PATCH/DELETE | Card operations |
| `/api/cards/:id/move` | POST | Move card to column |
| `/api/cards/:id/journal` | GET | Card activity journal |
| `/api/sprints` | GET/POST | Sprint management |
| `/api/sprints/:id/burndown` | GET | Sprint burndown data |
| `/api/itsm/incidents` | GET/POST | Incident queue |
| `/api/itsm/sla` | GET | SLA report |
| `/api/visual-boards` | GET/POST | Visual canvas boards |
| `/api/governance/prince2` | GET | Prince2 stage overview |
| `/api/export` | GET | Full workspace export (JSON) |
| `/api/import` | POST | Import workspace (JSON) |
| `/api/webhooks` | GET/POST | Webhook registry |
| `/api/summary` | GET | Board summary for AI agents |
