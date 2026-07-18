# Access Control Governance

> **What this is.** An honest accounting of who — and what — can currently do what on this
> platform, across the six access-subject types that actually exist here: Users, AIs, Agents, Bots,
> Data (by classification), and Locations (apps/services). Like `COST-AND-REVENUE-GOVERNANCE.md`,
> this document separates a **fixed policy** (the rollout plan below) from **live, mutable state**
> (which services actually have what) — the latter lives in
> `docs/architecture/ea-workbook/19_access_control_review.csv`, not in this file.

**Code:** `Dimensional/infinity/rbac.py` (`RBACEngine`, `Permission`, `InfinityRole`),
`Dimensional/infinity/abac.py` (`ABACEngine`, `Policy`, `PolicyEffect`),
`Dimensional/infinity/nomenclature.py` (`InfinityRole`, `Tier`, `Pillar`),
`src/auth/zero_trust.py` (`ZeroTrustMiddleware` — device posture/MFA/geo, human-user focused),
`src/roles/registry.py` (`RoleRegistry` — which AI holds which Location's Job Description; an
organisational assignment record, not an access-control mechanism).
**Owner:** Infinity (The Guardian, Anchor: Orb of Orisis) · **Version:** 1.0.0 · **Created:** 2026-07-18

---

## 1. Scope and an explicit limit

This document is a **finding and a rollout plan**, not a claim that access control is solved. It
does not invent a new permission system — `Dimensional/infinity/rbac.py` and
`Dimensional/infinity/abac.py` already provide one, well-designed, covering exactly the axes this
review was asked to check:

- **RBAC** (`InfinityRole`): `ADMIN` / `PRIME` / `AI` / `AGENT` / `BOT` / `USER` / `SERVICE` — a
  tier-aware role hierarchy that maps directly onto this platform's own Tier 0–5 taxonomy
  (`PLATFORM_ENTITIES.md`) and onto the "Users, AIs, Agents, Bots" axis this review was asked about.
- **ABAC** (`Dimensional/infinity/abac.py`): policies conditioned on subject attributes (tier,
  pillar, role), **resource attributes (classification, owner, pillar, sensitivity)** — the "Data"
  axis — and **environment attributes (network location, threat level, time)** — the "Locations"
  axis.

The gap is not design, it's **coverage**: almost none of the platform's 92 documented services
actually use it. That gap, and a prioritised plan to close it, is what this document is for.

## 2. What was actually checked (this session, 2026-07-18)

A grep-based classification across all 85 `workers/*` directories with a real entry file
(`worker.py` or `main.py`), checking for four signals: `RBACEngine`/`ABACEngine` usage, JWT-based
auth (`JWT_SECRET`, `AuthGatewayMiddleware`, `pyjwt`), a shared `INTERNAL_SECRET` header check, or
neither. The initial grep pass had two false negatives — `files-service` and `tranc3-ai` both have
real auth checks under different variable names (`INTERNAL_SERVICE_TOKEN`, a delegated
`verify_auth()` Bearer check) that the literal-string grep missed — caught and corrected before
this document was finalised, not left inaccurate. See `19_access_control_review.csv` Notes for both.

| Tier | Count | What it means |
|---|---|---|
| **RBAC/ABAC** (full tier-aware role + attribute policy engine) | 5 | `infinity-admin-service`, `infinity-one-service`, `infinity-portal-service`, `sentinel-station-service`, `gateway-service` (undeployed) — the Infinity security family this session's earlier pass fixed the *build* for. |
| **JWT-only** (validates a token, no role/attribute differentiation) | 3 | `api-gateway`, `infinity-auth` (the OAuth provider itself), `infinity-ws` |
| **Bearer/delegated-auth** (delegates to infinity-auth, returns role info, but that role isn't fed into RBACEngine) | 1 | `tranc3-ai` |
| **INTERNAL_SECRET-only or equivalent** (one shared secret/token gates all internal callers equally — no distinction between a human user, an AI, an agent, or a bot) | 63 | The large majority of the platform, including `files-service` (corrected from the initial pass). |
| **No auth mechanism detected at all** | 13 | `artifactory-service`, `blender-worker`, `dspy-service`, `ffmpeg-worker`, `haystack-service`, `infinity-shards-service`, `litellm-service`, `llamaindex-service`, `mlflow-service`, `optional-services-health`, `triposr-worker`, `turings-hub-service`, and (until fixed this session) `backup-service`. |

**The finding that needed acting on soonest, and was fixed this session:** cross-referencing the
"no auth" tier against this workbook's own `DataClassification` column found exactly one `DC-003`
(Confidential) service with zero access control — **`backup-service` (SRV-BACKUP-001)**. Fixed by
adding the same `INTERNAL_SECRET` middleware check already used elsewhere on the platform (e.g.
`hive-service`), verified with a clean-room import test. `infinity-shards-service` (`DC-003`) is
also zero-auth and *not yet fixed* — it's the odd one out among its Infinity-family siblings (all 4
of which have full RBAC/ABAC) and should get the same treatment, not just the baseline. Everything
else in the "no auth" tier is `DC-002` (Internal) — a real gap, lower urgency.

`src/auth/zero_trust.py`'s device-posture/MFA/geo middleware is wired into `api.py` (the monolith)
only — no standalone worker uses it. It is oriented at human users specifically (device IDs,
browsers, geography) and is a reasonable complement to RBAC/ABAC for that axis, not a replacement.

`src/roles/registry.py` answers a different question entirely ("which AI currently holds Location
X's Job Description") and should not be confused with access control — it is an org-chart record,
not a permission check.

## 3. Rollout plan — building on the existing engine, not a new one

1. **Immediate (Confidential-data, zero-auth services):** `backup-service` — DONE this session
   (`INTERNAL_SECRET` middleware baseline added and verified). `files-service` turned out to already
   have an equivalent check (§2 correction). `infinity-shards-service` remains the one real
   DC-003/zero-auth gap left — it should get full RBAC/ABAC to match its Infinity-family siblings,
   not just the baseline, since the code and the pattern to copy already both exist five doors down.
   Not done in this pass, tracked as an open item (§5).
2. **Near-term:** extend the 5-service Infinity-family RBAC/ABAC pattern to the remaining 6
   `DC-003`/`DC-004` services already on `INTERNAL_SECRET`-only (`infinity-bridge-service`,
   `imind`, `resonate`, `taimra`, `tranquility`, `ledger-service`, `payments-service`, `users-service`
   — see `19_access_control_review.csv` for the full cross-reference), since these already handle
   the platform's most sensitive data classifications.
3. **Medium-term:** roll RBAC (at minimum) out to the 62-service `INTERNAL_SECRET`-only tier, using
   `InfinityRole`'s existing `USER`/`AI`/`AGENT`/`BOT`/`SERVICE` roles — no new role taxonomy needed.
4. **Ongoing:** every *new* service should default to importing `Dimensional.infinity.rbac`/`abac`
   from day one, the same way `config/zero_cost/providers.yaml` compliance is expected by default —
   this is a code-review convention to adopt, not a mechanism this document can enforce by itself.
5. **Human decision required:** whether device-posture/MFA (`zero_trust.py`) should extend beyond
   `api.py` to standalone workers is a real product/UX tradeoff (it's built for browser sessions,
   not service-to-service calls) — flagged, not decided here.

## 4. Data / Location dimensions — already covered by ABAC's design, not yet by its usage

`Dimensional/infinity/abac.py`'s `resource_conditions` (classification, owner, pillar, sensitivity)
and `environment_conditions` (network location, threat level, time) already model exactly the
"Data" and "Locations" axes this review was asked about — see `Policy` in that file for the
declarative syntax. No new policy language is needed; what's needed is services actually
instantiating `ABACEngine` and defining policies for their own resources, which is the same
coverage gap as §2, not a design gap.

## 5. Open items

- `infinity-shards-service` (`DC-003`, zero auth) needs full RBAC/ABAC, not just an
  `INTERNAL_SECRET` baseline — the remaining real gap from this review's headline finding.
- `tranc3-ai`'s `verify_auth()` has a dev-mode bypass (`if not AUTH_URL and ENVIRONMENT !=
  "production": return {"userId": "dev", "role": "admin"}`) — worth confirming `ENVIRONMENT` is
  reliably set to `production` in the real deploy config, since a misconfigured env var here would
  silently grant admin to any caller.
- The 63-service `INTERNAL_SECRET`-only tier and the remaining 12-service no-auth tier need the
  same code-verification rigor this session applied to build/import correctness (clean-room tests,
  not just a grep signal) before any rollout — this document's classification is a first pass, not
  a final audit, and already had two false negatives caught and fixed once (§2).
- No load-bearing test exists yet asserting `RBACEngine`/`ABACEngine` behave correctly under
  concurrent/adversarial input — worth a dedicated pass before wider rollout.
- `19_access_control_review.csv` currently itemises the 23 services with a distinct signal (RBAC/
  ABAC, JWT-only, Bearer/delegated, or zero-auth); the 63 `INTERNAL_SECRET`-only services are
  counted but not itemised per-row yet, to avoid a rushed, potentially inaccurate service-ID join —
  a follow-up pass should complete that.
