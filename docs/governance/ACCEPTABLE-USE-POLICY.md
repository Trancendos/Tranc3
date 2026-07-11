# Trancendos Platform — Acceptable Use Policy & Location Subscription Terms

| Field | Value |
|---|---|
| **Version** | `1.0` — must match `CURRENT_TERMS_VERSION` in `src/access/registry.py` |
| **Effective date** | 2026-07-11 |
| **Applies to** | Every user subscribing to any of the platform's 43 named Locations via `POST /access/{location}/subscribe` |

> **Truthfulness:** this is the platform's own internal policy document, enforced by
> `src/access/registry.py`'s `CURRENT_TERMS_VERSION` check — not external legal advice. If real
> legal/compliance review of this text is required for a given jurisdiction or Location, that
> review happens outside this repo; this document and the code that enforces it must stay in sync
> with whatever version is actually approved.

## 1. Why subscription exists

Location functionality is **opt-in, not default-on**. A user's account does not automatically
have access to every one of the 43 Locations' services the moment it's created — each Location
must be individually subscribed to via `POST /access/{location}/subscribe`, with explicit
acceptance of this policy at its current version (`terms_version`).

This exists so that:

- Locations carrying heightened compliance obligations (financial functionality at Royal Bank of
  Arcadia / Arcadian Exchange, health/wellbeing-adjacent functionality at Tranquility/I-Mind/
  Resonate, security-tooling at Cryptex/The Ice Box/The Warp Tunnel, etc.) only activate for a
  user once they've affirmatively agreed to the terms governing that use — not implicitly, by
  merely having an account.
- If this policy changes (a new version is published and `CURRENT_TERMS_VERSION` is bumped),
  existing subscriptions are **not** silently carried forward under the new terms — every
  previously-subscribed user must re-consent (`terms_version` in their next `subscribe` call must
  match the new `CURRENT_TERMS_VERSION`, or the call is rejected with `422`).
- There's an auditable record of who agreed to what, and when — every subscribe/unsubscribe
  action is recorded in `location_subscriptions` (never deleted, only marked `revoked`), matching
  this platform's audit-trail conventions (the Role Registry's `role_assignment_history`, the
  Relations Registry's `activity_events`).

## 2. What subscribing means

Subscribing to a Location means the user agrees to:

1. Use that Location's functionality only for its stated purpose (per `PLATFORM_ENTITIES`'s
   `primary_function` for that Location).
2. Not attempt to circumvent rate limits, authentication, or other technical controls on that
   Location's services.
3. Accept that Location-specific functionality may itself carry additional, more specific terms
   (e.g. financial functionality may require additional KYC/AML-style steps outside this
   registry's scope) — subscribing here is a platform-level gate, not a substitute for any
   Location-specific compliance flow that may exist independently.
4. Have their subscription revoked (`unsubscribe`) at any time, by themselves or an administrator,
   which immediately deactivates that Location's functionality for their account.

## 3. Admin bypass

Callers with `role == "admin"` are **not** required to subscribe — `require_location_subscription`
(`src/access/routes.py`) exempts them. Administrators operate the platform; they do not
self-service-consent into it the way an end user does. This mirrors the Role and Relations
Registries' own "admin can always act" convention.

## 4. Live API (`/access`, mounted in `api.py`)

| Method | Route | Purpose | Auth |
|---|---|---|---|
| GET | `/access/me` | List the caller's own active subscriptions | any authenticated user |
| GET | `/access/{location}` | Get the caller's own subscription status for one Location | any authenticated user |
| POST | `/access/{location}/subscribe` | Subscribe — body `{"accepted_terms": true, "terms_version": "1.0"}` | any authenticated user (self only) |
| DELETE | `/access/{location}/subscribe` | Unsubscribe (self only) | any authenticated user (self only) |
| GET | `/access/{location}/subscribers` | List every subscriber to a Location (compliance/audit) | **admin role required** |

`POST`/`DELETE` are self-service by design — a user consents to (or withdraws from) a Location's
terms on their own behalf, not an admin's. `GET /subscribers` is admin-only since it exposes other
users' subscription data.

Like the Role and Relations Registries, single-Location routes use FastAPI's `:path` converter
internally so "ChronosSphere / ArcStream" (the one canonical Location with a literal `/`) resolves
correctly; the more specific `/subscribers` and `/subscribe` routes are registered ahead of the
bare `/{location}` route for the same reason documented in those modules.

## 5. Using the gate in a router

Any router gating Location-scoped functionality should depend on
`require_location_subscription(location)`:

```python
from src.access.routes import require_location_subscription

@router.post("/some-location-scoped-endpoint")
def do_thing(current_user: dict = Depends(require_location_subscription("The Lab"))):
    ...
```

Unsubscribed non-admin callers get `402` (used here for "consent required," not billing) with a
message pointing at the `subscribe` endpoint.

**Rollout status:** the registry, dependency, and self-service API are built and tested. Wiring
`require_location_subscription` into each of the 43 Locations' own worker/router endpoints is a
follow-up task — this pass establishes the reusable mechanism, not a full platform-wide rollout.
Prioritize the Locations named in §1 (financial, health/wellbeing, security) first when that
rollout happens.

## 6. Changing this policy

To publish a new version:

1. Update this document's **Version** field and rewrite the affected sections.
2. Bump `CURRENT_TERMS_VERSION` in `src/access/registry.py` to match.
3. Every user's next `subscribe` call for any Location must cite the new version — old
   subscriptions remain `active` (so existing access isn't silently revoked by the bump alone) but
   any *new* subscribe attempt with the old version is rejected, and operators should communicate
   the change and prompt existing subscribers to re-consent through whatever front-end surfaces
   this flow.
