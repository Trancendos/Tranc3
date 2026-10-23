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

## Decision safety (fail-closed)

`POST /townhall/check` preserves individual policy results (`pass`, `warn`, `fail`,
`unknown`). Its **overall** result is `fail` when a required policy is missing,
not executable, throws, returns an invalid status, or when no policies are evaluated.
A warning remains `warn` only when all the other evaluated policies pass.
Do not treat policy metadata scores as proof that an executable check passed.

Because several registry-only policies have no evaluator, the default all-policy
check may now correctly fail. Callers should explicitly name the implemented,
required policy IDs and must not use an arbitrary narrower set to bypass the
applicable release/approval gate. Governance criteria for releases belong in
the separate evidence-backed PLM gates, not static registry scores.

## Server-owned decision previews (advisory only)

`POST /townhall/decisions/{intent}/preview` resolves mandatory policy IDs on the
server rather than accepting caller-selected policy IDs. Available intents:

| Intent | Mandatory policies | Additional input |
|---|---|---|
| `change` | `zero-cost`, `gdpr` | Declared cost and data handling |
| `release` | `zero-cost`, `gdpr`, `prince2` | As above plus build/test evidence identifiers |

Call with a nested `context` object, for example:

```json
{
  "context": {
    "monthly_cost_usd": 0,
    "personal_data": false,
    "cross_border_transfer": false
  }
}
```

Required fields must be supplied with explicit values. Personal-data processing
additionally requires a non-empty `lawful_basis`; cross-border transfers require
an explicit Boolean `adequacy_decision`. An incomplete or invalid context returns
`overall: fail` and a list of `input_errors` without running policy checks.

**This endpoint does not authorise anything.** Every response includes
`preview_only: true` and `authorization_granted: false`, even if the
preliminary `overall` assessment is `pass`. Supplied values and evidence IDs are untrusted claims, not independently
verified source records or human approvals. The preview ignores user-supplied
`actor`, `policy_ids` and unrelated context fields rather than recording spoofed
identity or copying arbitrary data into compliance logs. `prince2` currently has no executable evaluator, so release
previews fail closed. The persistent PLM stage gates, trusted evidence lookup,
authenticated decision authority and integration with CranBania remain separate
requirements under issue #1450. Never treat a preview response as release
permission.

## Evidence readiness report (advisory, admin only)

`GET /townhall/plm/deliverables/{deliverable_id}/readiness` reads the existing
SQLite-backed PLM deliverable and its current gate criteria; it does not create
new evidence or advance any stage. It requires an authenticated `admin` principal.

The response gives operators bounded diagnostic reason codes for mandatory
criteria: `missing_evidence`, `failed_evidence`, `pending_evidence`,
`invalid_evidence` and `inconsistent_evidence`. It also identifies the
Location responsible for missing evidence, lists recorded evidence IDs (not
raw reference values) and surfaces waivers separately for manual review.

The `state` can be `blocked`, `waiver_review`,
`recorded_evidence_unverified` or `no_current_gate`. **A recorded PASS is
an operator assertion, not independently verified CI, Artifactory or security
evidence.** Even a fully recorded gate never creates an authorisation:
`authorization_granted: false` and `preview_only: true` are unconditional.
At the release stage the response lists the server-owned release policy IDs
as `evaluated: false`; it does not silently convert registry metadata into
compliance.

The snapshot is non-atomic across deliverable and gate reads and is unsuitable
for enforcement. The authoritative `advance` transaction must re-check
latest evidence and approval under its existing SQLite lock. This endpoint
does not provide the independent evidence attestation, authenticated waiver
expiry, transactional outbox or CranBania integration tracked in issue #1450.

## Compliance integration

- Fail/warn results emit to **The Observatory** (`observe(..., category=GOVERNANCE)`).
- Zero-cost deployments should pass `POST /townhall/check` with `{"monthly_cost_usd": 0}`.
- War Room sessions should be opened for P1 ITSM incidents.

## Related

- `PLATFORM_ENTITIES.md` (PID-TWH)
- `docs/ZERO_COST_VENDOR_MATRIX.md`
- `docs/RESEARCH_ADVANCEMENT_2026.md`
- `tranc3-ts/src/hubs/townhall/TownHallAI.ts` (orchestration layer)
