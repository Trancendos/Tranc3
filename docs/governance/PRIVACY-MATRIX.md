# Privacy Matrix

> **What this is.** "Privacy Matrix" from the brainstorm maps to one real, tested, tagged
> (`REQ-PRI-001`) GDPR Data Subject Request workflow that had no governance doc pointing to it —
> found only by grepping the codebase, not by any existing cross-reference. This doc exists so that
> gap doesn't persist.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. What's real: the DSR workflow

`src/privacy/dsr_workflow.py` — Automated GDPR Data Subject Request (DSR) handling, tagged
`REQ-PRI-001`. Covers all six GDPR request types as a real `DSRType` enum: **access** (SAR),
**erasure** (right to be forgotten), **rectification**, **portability**, **restriction**,
**objection**.

Each `DSRRequest` tracks:

- `status` — `received` → `identity_verified` → `in_progress` → `completed` / `rejected` /
  `escalated`.
- `due_at` — computed from creation using `SLA_DAYS = 30`, tracked as this workflow's **internal**
  response-time target. **Correction:** GDPR Art. 12(3) itself requires a response within **one
  calendar month** of receipt (not a fixed 30-day count — a month can be 28–31 days), with a
  possible extension of up to two further months for complex/numerous requests, conditional on
  notifying the data subject of the delay and the reason within the original one-month window.
  `SLA_DAYS = 30` is a reasonable internal proxy for "one month," but the code has no representation
  of the extension path or the required subject notification — both real legal states that this
  workflow doesn't model today.
- `sla_risk` — a real computed property: `BREACH` (overdue), `HIGH` (≤7 days left), `MEDIUM` (≤14
  days), `LOW` (otherwise) — not just a stored field, derived live from `days_remaining` against the
  internal 30-day target above, not the GDPR deadline directly.
- A full `audit_log` per request.

Backed by SQLite (`./data/dsr_workflow.db`), matching the platform's zero-cost self-hosted
convention used by the Role/Access/Relations registries.

## 2. What's real: the one integration point

`src/audit/automated_auditor.py`'s scheduled auditor calls `get_workflow().sla_report()` and raises
an `AuditFinding` whenever `breached > 0` — i.e., the only thing currently *consuming* the DSR
workflow's state is the compliance auditor's SLA-breach check. This is a real, working integration,
not aspirational.

## 3. The honest gap: no operator-facing surface

`DSRWorkflow` is **not mounted as an HTTP router anywhere** — grepping the entire `src/` and
`workers/` trees for `dsr_workflow`/`DSRWorkflow` usage turns up exactly two files: the module
itself and the one `automated_auditor.py` read. There is no `/privacy/dsr` (or similar) route, no
UI, and no way for an operator to actually create, update, or resolve a DSR through the running
platform today — only the SLA-breach alerting works. A data subject emailing a rights request would
currently need someone to manually construct a `DSRRequest` in a Python shell; there's no intake
path.

This is a real capability with a real gap, not a fabricated system — the distinction matters
because "Privacy Matrix: not built" would be as wrong as claiming it's fully operational. It's
**half-built**: the engine and SLA math are real and tested; the intake/operator surface isn't.

## 4. Path forward, if prioritized

Not committed work:

1. Mount a `/privacy/dsr` router exposing create/list/update/resolve endpoints over the existing
   `DSRWorkflow` class — no new business logic needed, just an HTTP surface over what already
   exists.
2. Add an intake path (a public form or authenticated endpoint) so a real data subject request can
   actually enter the system without operator intervention.
3. Feed `DSRRequest` audit_log entries into `src/relations/registry.py`'s Activity Feed, following
   the same best-effort pattern the Role Registry already uses (`AI-RELATIONSHIP-MATRIX.md` §6),
   so a completed erasure request shows up in the platform's general activity trail.

## 5. Cross-references

- `docs/compliance/COMPLIANCE-BLUEPRINT.md` — the regulatory-framework layer this workflow serves.
- `docs/governance/DATA-TRANSFER-MATRIX.md` — the cross-border data question this workflow doesn't
  currently address (DSR handling is about subject rights, not about where data physically sits).
- `src/audit/automated_auditor.py` — the one real consumer of `DSRWorkflow.sla_report()`.
