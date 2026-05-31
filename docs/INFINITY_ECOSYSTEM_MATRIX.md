# Infinity Ecosystem Architecture Matrix

**Source of truth for explaining the Infinity system to humans and other AIs.**

Copy this table and precede with: *"Treat the following as absolute source of truth for component naming, function, and modular separation."*

---

## System nodes

| System node | Architectural role | Core functionality | Conceptual visualization |
|---|---|---|---|
| **Infinity-Portal** | Authentication gateway | Entry point: credential verification, edge security before ecosystem access | Front door / airlock |
| **Infinity-Gate** | RBAC routing matrix | Post-login controller: evaluates roles and presents navigation (Admin vs User vs DevOps) | Grand foyer — choose path by clearance |
| **Infinity-One** | IAM profile hub | User preferences, global settings, subscription state, access management | Google/Microsoft account dashboard |
| **Infinity** | Central orchestration hub | Primary dashboard after routing; aggregates services, widgets, shards | Greek/Roman temple floating in space |
| **Infinity-Bridge** | Data pipeline & event bus | State sync, secure transfer between microservices | Neural pathways between islands |
| **Infinity-Admin** | Global control plane | Admin OS: config, entity names, primes, audit, compliance | Mission Control |
| **Infinity-Shards** | Contextual nanoservices | Task-specific agents (Gem-like); plug-in without hub bloat | Faceted crystals orbiting the temple |
| **Infinity-Core** | Foundational bundle | Shared infrastructure binding all Infinity modules | Engine room / gravitational center |

---

## Routing protocol (onion layers)

| Layer | Node | Function |
|---|---|---|
| 1 | Infinity-Portal | Authentication & verification |
| 2 | Infinity-Gate | RBAC evaluation & intent |
| 3 | Infinity | Hub / arrival point |
| 4 | Locations | Distinct apps/repos (Arcadia, The Citadel, …) |

**Rule:** All journeys originate from, pass through, and return to **Infinity**. No lateral movement between Locations without passing through Infinity.

---

## User journey matrix

| Persona | Path | Logic |
|---|---|---|
| Standard user | Portal → Gate → Infinity → **Arcadia** | User permissions only; no infra/admin nodes |
| DevOps | Portal → Gate → Infinity → **The Citadel** | Engineering/infrastructure command center |
| Global admin | Portal → Gate → Infinity → **Infinity-Admin** → [any Location] | Master clearance; anchor remains Admin |

---

## Tier hierarchy (Trancendos convention)

| Tier | Name | Examples | Infinity designation |
|---|---|---|---|
| 0 | Human | End user | — |
| 1 | Orchestrator | Cornelius MacIntyre, The Queen, tAImra (off by default) | Trance-One |
| 2 | Prime | Dorris Fontaine, The Guardian, Voxx, … | T2ance |
| 3 | AI (Lead AI) | Norman Hawkins, Tyler Towncroft, Zimik, … | Tranc3 |
| 4 | Agent | Pathfinder, Synapse, Syntax-Sage, … | Infinity-Agent |
| 5 | Bot / Service Worker | Ping-Bot, Neuron-1-Bot, … | Infinity-Bot |

**Dimensional** = Shared-Core cross-cutting systems (not a tier).

**SentinelStation** = Traffic routing bus (event channels).

**Underverse** = Nanoflow services per application.

---

## Worker ports (Infinity stack)

| Port | Service |
|---|---|
| 8040 | Gateway |
| 8041 | Sentinel Station |
| 8042 | Infinity-Portal |
| 8043 | Infinity-One |
| 8044 | Infinity-Admin |
| 8005 | Infinity-Auth |

---

## Common naming mistakes

| Mislabel | Correct tier | Canonical name |
|---|---|---|
| "Sage" as Prime | Tier 4 Agent | **Syntax-Sage** at The Lab (PID-LAB), Agent β |
| "The Nexus" as Lead AI name | Tier 3 | **Nexus-Prime** (Lead AI); location is **The Nexus** |
| MacIntyre vs McIntyre | — | Canonical in `platform.py`: **MacIntyre** |

Edit display names in **Infinity-Admin → Entity Name Registry** (dashboard :8044 or API `/admin/entities`).
