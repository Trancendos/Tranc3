# The Town Hall

**Location:** The Town Hall · **Lead AI:** Tristuran · **PID:** PID-TWH

Governance, compliance, Agile/Kanban, ITSM/ITIL, PRINCE2, rooms (BoardRoom, WarRoom, MeetingRooms), and document templates (policies, ADD/DDD, blueprints, cookbooks, frameworks).

## What exists today

| Capability | Status | API |
|------------|--------|-----|
| Policy registry & compliance checks | **Live** | `GET /townhall/policies`, `POST /townhall/check` |
| Framework registry (YAML) | **Live** | `GET /townhall/frameworks` |
| BoardRoom / WarRoom / MeetingRooms | **Live** (in-memory sessions) | `POST /townhall/rooms/{room_id}/sessions` |
| Document templates | **Live** | `GET /townhall/documents/templates`, `POST .../render` |
| Kanban (Agile) | **Live** (in-memory) | `GET/POST /townhall/kanban/...` |
| ITSM / ITIL incidents | **Live** (in-memory) | `GET/POST /townhall/itsm/incidents` |
| TypeScript hub (agents/bots) | **Partial** | `tranc3-ts/src/hubs/townhall/` |
| Persistent DB / Forgejo PR gates | **Planned** | — |

## Framework domains (`config/townhall/frameworks.yaml`)

- **governance** — Magna Carta, governance core  
- **agile** — Agile, Kanban (Scrum planned)  
- **itsm** — ITSM, ITIL 4  
- **project_management** — PRINCE2 7  
- **compliance** — GDPR, UK-GDPR, Zero-Cost, regulation/compliancy frameworks  
- **security** — Security framework (OWASP + Zero Trust)  
- **legal_ip_finance** — Legal, IP, financial oversight  
- **architecture** — Foundation, Universe, App-per-App, ADD, DDD, Blueprint, Design System  
- **documentation** — Policy, procedural, legislation, cookbooks, bibles/guides  

## Rooms

| Room ID | Name | Use |
|---------|------|-----|
| `board-room` | BoardRoom | Executive approvals, PRINCE2 stage gates |
| `war-room` | WarRoom | P0 incidents, deploy failures, adaptive rotation |
| `meeting-room` | MeetingRooms | Standups, governance reviews |

## Templates

Markdown templates under `config/townhall/templates/` — render with variables:

```bash
curl -X POST https://tranc3-backend.fly.dev/townhall/documents/templates/add/render \
  -H "Content-Type: application/json" \
  -d '{"variables":{"system_name":"tranc3-backend","author":"Tristuran","version":"1.0","date":"2026-05-31","context":"Fly CLOUD_ONLY"}}'
```

## Compliance integration

- Fail/warn results emit to **The Observatory** (`observe(..., category=GOVERNANCE)`).  
- Zero-cost deployments should pass `POST /townhall/check` with `{"monthly_cost_usd": 0}`.  
- War Room sessions should be opened for P1 ITSM incidents.

## Related

- `PLATFORM_ENTITIES.md` (PID-TWH)  
- `docs/ZERO_COST_VENDOR_MATRIX.md`  
- `docs/RESEARCH_ADVANCEMENT_2026.md`  
- `tranc3-ts/src/hubs/townhall/TownHallAI.ts` (orchestration layer)
