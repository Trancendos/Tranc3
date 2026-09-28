# The Trancendos Domain Model

> **What this is.** The owner asked for entities, attributes and associations with permissions
> and routing, structured the way Mendix structures a domain model, and for every Location,
> AI, database and container to be registered in the CMDB with documentation, registry values,
> environment variables, and dependency associations checked. This is that model, the report
> of where the estate does not yet meet it, and why the shape was chosen.
>
> **Code:** `src/domain/` · **Generated:** `docs/architecture/domain-model.{json,sql}`,
> `docs/architecture/conformance.json`
> **Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Set:** 2026-09-11

---

## 1. Why Mendix's shape is the right one here

Mendix models an application as modules, each owning a domain model of entities with typed
attributes and associations, secured by access rules defined **per module role**, **per member**,
constrained by an XPath expression. Three of those decisions are the reason this maps onto
Trancendos rather than merely resembling it:

| Mendix | Trancendos | Why it lands |
|---|---|---|
| Module | **Location** | Each of the 43 already owns its code, its port and its docs pack |
| Module role | **Job Description seat** | 56 seats already exist, with named holders |
| Entity | **CI class** | The CMDB already has classes; they lacked attributes and associations |
| Attribute | CI field | Typed, so it generates a column |
| Association (with an owner) | Dependency, jurisdiction, custody | The arrow settles which side owns the fact |
| Access rule (member-level, additive) | Seat permissions | Column-level, not "read the Location" |
| XPath constraint | **PostgreSQL row-level security predicate** | Multi-tenancy without a WHERE clause anyone can forget |
| Page / microflow | HTTP route, port, path prefix | Routing falls out of the same model |

The payoff is that **one model generates four things that are currently maintained separately**:
the database schema, the permission policies, the route table, and the CMDB's CI classes. Adding
a Location today means remembering to touch all four. With a domain model it means touching one,
and `--check` in CI fails when the generated artifacts stop matching.

Two of Mendix's rules are kept deliberately because each prevents a failure this estate has seen:

- **Associations have an owner.** Without the arrow, "The Ice Box custodies 174 containers" and
  "174 containers are custodied by The Ice Box" become two facts that can disagree.
- **Access is member-level and additive.** Entity-level permissions are what produce "read access
  to the Location" followed by a surprise that it included the credentials column.

## 2. The model

**Five entities** across three modules today — the CMDB's own classes, not the whole platform:

| Entity | Module | Source |
|---|---|---|
| `Location` | The Citadel | `PLATFORM_ENTITIES` |
| `AI` | The Citadel | `PLATFORM_ENTITIES` + personality profiles |
| `RoleSeat` | The Town Hall | `get_seats()` |
| `Container` | The Ice Box | `src/cmdb/containers.py` |
| `Datastore` | The Citadel | `src/cmdb/datastores.py` |

**Seven associations**, of which two matter most:

```
Container ──custodied by──▶ Location   (required — always The Ice Box)
Container ──jurisdiction──▶ Location   (optional — 86 run nobody's code here)
```

They are separate associations generating separate columns. Collapsing them into one
`location_id` would merge the two facts the shared-jurisdiction model exists to keep apart.

**80 routes**, read from Traefik labels and published ports in compose, each carrying the module
that owns it — so "which routes reach the table holding credentials" is a query rather than an
investigation.

## 3. Generated schema and security

`docs/architecture/domain-model.sql` emits:

- **Schema per module** — `the_citadel.location`, `the_ice_box.container`. Not a database per
  module: cross-schema joins work, one backup covers everything, one connection pool. Database
  per Location would recreate the 96-file SQLite problem with a heavier engine.
- **Row-level security, enabled and FORCEd, on every table.** `FORCE` matters: without it the
  table owner bypasses every policy, and applications connect as the owner more often than
  anyone intends.
- **Default deny.** A table with RLS enabled and no policy returns nothing. So an entity nobody
  has written access rules for is unreadable rather than public — the safe direction for a
  generator to be incomplete in.
- **Session settings, scoped `LOCAL`.** Policies read `trancendos.location` and
  `trancendos.role`, set per transaction. `LOCAL` so the setting dies with the transaction
  instead of leaking into the next request that borrows the same pooled connection.

One honest limitation stated in the generated SQL itself: **RLS filters rows, not columns.**
Mendix's member-level access needs PostgreSQL column privileges, so the generator emits the
`GRANT ... (columns)` statements as comments beside each rule rather than pretending the row
policy covered it.

## 4. Conformance — where the estate does not yet meet this

`docs/architecture/conformance.json`, regenerated on every run. Six properties per Location:

| Property | Locations passing (of 43) |
|---|---:|
| Registered in the CMDB | 40 |
| Has a documentation pack | 34 |
| Has a registry value | 43 |
| Environment variables all declared | 8 |
| Dependency associations declared | 40 |
| **Complete on all six** | **6** |

The governing rule: **an unchecked property is reported as unchecked, never as passing.** Two
Locations' environment variables could not be scanned; they are reported as "not checked" and
cannot count as complete.

### The largest finding: `ALLOWED_ORIGINS`

**30 Locations read `ALLOWED_ORIGINS`, and nothing declares it** — not `.env.example`, not any
compose `environment:` block.

Stated precisely, because the precise version is less alarming and more useful than the
headline: the fallback is `http://localhost:3000`, and the parsing explicitly filters out `*`.
So this is **not** an open-CORS vulnerability — it fails closed. What it means is that in
production those 30 services would accept browser requests only from `localhost:3000` and
**reject the real frontend's origin**. A functional outage waiting on first browser traffic,
not a security hole, and worth fixing before it is discovered that way.

### Nine Locations with no documentation pack

ChronosSphere / ArcStream, DevOcity, DocUtari, Section 7, TateKing, TranceFlow, Turing's Hub,
VRAR3D, tAimra.

## 5. What comes next

1. Declare `ALLOWED_ORIGINS` and the other undeclared variables, per Location.
2. Extend the model beyond the five CMDB classes to the Locations' own entities — that is where
   the per-AI and per-Location databases in `DATA-PLATFORM-STRATEGY.md` get their schemas.
3. Generate the route table's auth requirements from the same access rules, so a public route
   onto a sensitive entity fails CI rather than review.
4. Docs packs for the nine Locations without one.

## Sources

- [Data in the Domain Model — Mendix Documentation](https://docs.mendix.com/refguide/domain-model/)
- [Access Rules — Mendix Documentation](https://docs.mendix.com/refguide/access-rules/)
- [Domain Model in the Mendix Metamodel](https://docs.mendix.com/apidocs-mxsdk/mxsdk/domain-model-metamodel/)
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [How to Implement Row-Level Security in PostgreSQL](https://oneuptime.com/blog/post/2026-01-21-postgresql-row-level-security/view)
