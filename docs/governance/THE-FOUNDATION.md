# The Foundation — the parent entity above Trancendos

**Version:** 1.0.0
**Date:** 2026-08-01
**Owner:** Platform Owner (Andrew Porter)
**Status:** Framing introduced this document plus a one-line naming-rule pointer in
`CLAUDE.md` (§4); estate-wide propagation into existing governance docs is staged (§5)
— no entity, Location, code path, or other doc changes yet.

---

## 1. What changes, what doesn't

Trancendos is unchanged: still the platform, the product, the domain
(`trancendos.com`), and the home of all 43 named entities catalogued in
`PLATFORM_ENTITIES.md`. Nothing here renames it, replaces it, or shrinks it.

The Foundation is a new concept introduced *above* Trancendos: a parent
governance/ownership entity, the way a holding company sits above an operating
brand.

```
The Foundation      ← parent: governance & ownership umbrella
      │
  Trancendos        ← the platform/product, exactly as documented elsewhere in this repo
      │
  ├── Infinity
  ├── Royal Bank of Arcadia
  ├── The Town Hall
  └── ...(all 43 named entities, unchanged — see PLATFORM_ENTITIES.md)
```

No entity, Location, code path, or naming rule elsewhere in this repo changes as a
result of this document. This is purely additive: a place for cross-cutting
governance to live that isn't tied to the Trancendos brand specifically.

## 2. Why introduce a parent above Trancendos

- **Trancendos is a product/platform name; The Foundation is the entity that owns
  and governs the estate.** That distinction matters the moment there's a second
  product line, a legal entity distinct from the product name, or governance work
  (Magna Carta, compliance, cross-cutting policy) that shouldn't be described as
  belonging to one brand.
- Magna Carta's compliance framework (`compliance/magna-carta/`) already reasons
  about "the estate" in terms broader than any single platform brand — The
  Foundation gives that reasoning an actual name to attach to, instead of an
  implicit one.

## 3. What The Foundation does *not* do (yet)

- It does not replace Trancendos as the primary code name for the platform, in
  code, routes, logs, or documentation — `CLAUDE.md`'s naming rules for the 43
  entities are unaffected.
- It is not a declaration of a new legal entity. This document describes a
  governance/naming concept; incorporating an actual holding company is a
  separate, real-world decision for the Owner to make outside this repo.
- It does not currently own any code, service, or Location distinct from what
  Trancendos already owns. There is no `src/foundation/`, no router, no new
  runtime component introduced by this document.

## 4. Naming rule

Added to `CLAUDE.md`'s naming rules (§0): **"The Foundation" is the parent
governance/ownership entity above Trancendos** — introduced 2026-08-01, described
fully in this document. Use "Trancendos" for the platform/product/domain exactly as
before; use "The Foundation" only when specifically referring to the parent entity
itself (e.g. in governance or ownership contexts), not as a substitute for
"Trancendos" in ordinary platform references.

## 5. Staged rollout

| Stage | Deliverable | Status |
|---|---|---|
| 1 | This document + a one-line pointer in `CLAUDE.md` | ✅ this change |
| 2 | Reference The Foundation in Magna Carta's top-level governance framing where "the estate" is discussed today | staged |
| 3 | Propagate into wiki / architecture docs that describe estate-wide ownership | staged |

Stages 2–3 are not required for anything currently in flight (Matrix Suites,
go-live) and should be picked up opportunistically, not as a blocking rewrite of
150+ existing governance docs.
