# Permissions & Access Matrix

> **What this is.** "Permissions Matrix" from the brainstorm maps to three distinct, already-real
> systems that answer three different questions: *who currently holds a Location's functional
> role* (Role Registry), *which Locations has a given user actually consented into* (Access
> Registry), and *is this specific request trustworthy right now* (Zero Trust IAM). None of the
> three is a superset of the others — this doc is the map showing how they fit together.

**Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Last verified:** 2026-07-30

---

## 1. Role Registry — who holds the Job Description

`src/roles/registry.py`'s `RoleRegistry` — already documented in `CLAUDE.md`'s "Location Functions
& Job Descriptions" section and `docs/governance/LOCATION-FUNCTIONS.md`. Tracks which AI currently
holds the functional Job Description for each of the 43 Locations, distinct from the static
`lead_ai` field. Every reassignment is recorded in `role_assignment_history`, and a successful
(re)assignment emits a best-effort event into the AI Relationship Matrix's Activity Feed (see
`AI-RELATIONSHIP-MATRIX.md` §6). Exposed at `/roles`.

**Question answered:** *"Who is currently the CFO of Royal Bank of Arcadia?"*

## 2. Access Registry — who has consented into which Location

`src/access/registry.py`'s `AccessRegistry` — a real, SQLite-backed, per-user subscription/consent
registry. Key mechanics:

- Not every user has every Location's functionality on by default; a Location only activates for a
  user once they've explicitly subscribed.
- Locations with enhanced compliance obligations (financial, health, legal-adjacent) require
  explicit agreement to that Location's Terms & Conditions / Acceptable Use Policy at a specific,
  trackable version (`CURRENT_TERMS_VERSION`).
- Bumping `CURRENT_TERMS_VERSION` does **not** silently carry over existing subscribers — each must
  re-consent (`StaleTermsVersionError`) before the Location reactivates, matching
  `docs/governance/ACCEPTABLE-USE-POLICY.md`'s own version header, which must stay in sync.
- Every subscribe/unsubscribe is a `SubscriptionEvent`, giving an auditable consent trail matching
  the Role Registry's and Relations Registry's audit-history conventions.

**Question answered:** *"Has this user actually agreed to Royal Bank of Arcadia's current Terms,
and when?"*

## 3. Zero Trust IAM — is this request trustworthy right now

`src/auth/zero_trust.py` — ported from `@trancendos/iam-middleware/zeroTrust` (infinity-adminOS),
self-hosted, zero-cost (replaces a Cloudflare Zero Trust dependency). Real mechanics:

- `DevicePostureStatus` (healthy/unhealthy/unknown) extracted from request headers into a
  `ZeroTrustContext`.
- `AccessPolicy` decision: `ALLOW` / `DENY` / `MFA_REQUIRED`.
- Geographic access policies, risk scoring, and network-based access control layered on top of
  device posture and MFA state.

**Question answered:** *"Given this request's device, location, and MFA state right now, should it
be allowed, denied, or challenged?"*

## 4. How the three relate

```text
Zero Trust IAM   — per-request trust decision (every request, stateless)
Access Registry  — per-user, per-Location consent gate (checked once per Location activation)
Role Registry    — per-Location, who currently holds the functional role
```

This is a conceptual funnel, not today's actual enforcement: the three systems are independent and
composable, not a literal three-step gate a request passes through. **Role Registry's own read
routes (`GET /roles/...`) are unauthenticated today** — anyone can query who holds a given Job
Description with no Access Registry subscription or Zero Trust check involved at all; only the
mutating `assign`/`unassign` routes require an authenticated admin (`src/roles/routes.py`). Being
"subscribed" via the Access Registry is not what grants read access to the Role Registry — the two
systems don't currently interact. No single request touches all three checks in the same code path
today — each is invoked independently where relevant, not as one unified middleware chain. Wiring
them into one composed check (Zero Trust → Access → Role, in that order, on every mutating Location
request) is the natural next step if a single "permission decision" API is ever wanted; not built
today.

## 5. Cross-references

- `docs/governance/LOCATION-FUNCTIONS.md` — Role Registry in full.
- `docs/governance/ACCEPTABLE-USE-POLICY.md` — the Terms version the Access Registry gates against.
- `docs/governance/AI-RELATIONSHIP-MATRIX.md` §6 — the Role Registry → Relations Feed integration.
