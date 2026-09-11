# Data Platform Strategy

> **What this is.** The owner is adding databases per AI and per Location, and has been
> advised to move away from SQLite. This is the research behind that advice, the measured
> state of the estate it applies to, and a strategy that can be executed a store at a time
> rather than as one migration nobody will start.
>
> **Code:** `src/cmdb/datastores.py` (discovery), `scripts/build_ci_register.py` (CI registration)
> **Owner:** Platform Owner Trancendos · **Version:** 1.0.0 · **Set:** 2026-09-11

---

## 1. The measured estate

Not an estimate. `src/cmdb/datastores.py` walks the repository and finds every module that
opens a datastore:

| Engine | Production stores | Notes |
|---|---:|---|
| SQLite | 96 | file-backed, one file per store |
| Redis | 35 | reached over a URL |
| PostgreSQL | 7 | reached over a URL |
| DuckDB | 6 | embedded OLAP, already in the analytics worker |
| **Total** | **144** | plus 69 more that only tests open |

Of those 144: **123 are file-backed**, and **only 30 resolve to an owning Location** — 114 have
no owner in the CMDB at all.

Two further measurements matter more than the totals:

- **`workers/backup-service/worker.py` speaks SQLite and nothing else.** Its own docstring says
  so: "sqlite3 hot-backup API". The estate also runs a MySQL instance (`misp-db`) and 7
  PostgreSQL stores. There is no code path that could back either up. This is issue #1146 and
  it is the highest-consequence item in `RELEASE-READINESS.md`.
- **Only 13 of 96 SQLite stores are opened by more than one module.** That is the number that
  says this is *not* yet a concurrency crisis — and the number that will change the moment
  per-AI and per-Location databases arrive, because those are shared by definition.

## 2. Why the advice is right — and where it is not

The case against a 96-file SQLite fleet is not that SQLite is a poor database. It is excellent,
and this estate uses it correctly in many places. The case is about what changes when the fleet
grows the way the owner described.

**Where SQLite genuinely stops working here:**

1. **One writer.** WAL (77 modules enable it) permits many readers and exactly one writer. A
   per-Location database serving a Location's Agents, Bots and its Lead AI has concurrent
   writers by construction. The failure mode is `database is locked` under load — intermittent,
   load-dependent, and therefore discovered in production.
2. **No cross-store query.** The CMDB has to answer "which Locations depend on a container
   whose SBOM contains this package". That is one join across Locations, AIs, containers and
   components. Across 96 files it is not a query; it is a program.
3. **Backup is per-file and the engine is single-dialect.** 144 stores, one backup
   implementation, and it speaks one of the four engines present.
4. **Schema drift.** 96 schemas, no migration framework between them. Alembic covers the main
   application database only.
5. **The file is inside the container.** A file-backed store in a container's writable layer
   dies with the container unless a volume is mounted and mounted correctly. That is a
   per-service configuration detail, repeated 123 times.

**Where the advice does not apply, and a blanket migration would make things worse:**

- Single-process caches and ephemeral state (`cache.db`, rate-limit buckets). Moving these to a
  networked engine adds a network hop and a new failure mode to something whose whole purpose
  is to be fast and disposable.
- DuckDB in the analytics worker. It is an embedded OLAP engine and the right tool for the job
  it does; it is not "SQLite that needs replacing".
- Anything a test opens. The 69 fixture stores should stay SQLite forever — `tmp_path / "x.db"`
  is the correct pattern for a test.

**So the strategy is a classification, not a sweep.** Section 5 gives the rule.

## 3. The engine choice

### PostgreSQL as the system of record

One engine covering what would otherwise be five, through extensions that share the same
tables, the same transactions and the same backup:

| Need | Extension | Replaces |
|---|---|---|
| Relational | core | 96 SQLite files |
| Vector / embeddings | `pgvector` | Pinecone, the in-memory vector store, part of FAISS usage |
| Time-series (metrics) | `TimescaleDB` | per-worker metrics tables |
| Graph (the CMDB itself) | `Apache AGE` | hand-rolled adjacency in `blast_radius.py` |
| Scheduled jobs | `pg_cron` | parts of ChronosSphere's polling |
| Horizontal scale, later | `Citus` | nothing yet — kept as an option, not a plan |

The graph row is the one to notice. A CMDB is a graph: CIs and their relationships. The estate
already computes blast radius over a hand-built edge list in `src/cmdb/blast_radius.py`. With
the CI register now emitting 318 CIs with jurisdiction and custodian edges, that graph stops
being small, and a graph query language becomes the difference between an answer and a script.

**Licence:** PostgreSQL Licence (permissive, OSI-approved). pgvector PostgreSQL Licence,
TimescaleDB Apache 2 for the open edition, Apache AGE Apache 2, pg_cron PostgreSQL Licence.
No paid tier is required for any of it, which is the platform's standing constraint.

### The rest of the tier

| Role | Choice | Licence | Why |
|---|---|---|---|
| Cache / queue | **Valkey** | BSD-3 | Redis moved to RSAL/SSPL in March 2024; since 8.0 it is tri-licensed and AGPLv3 is available, but Valkey is the Linux Foundation fork that stayed BSD. For a platform whose posture is zero-cost and no licence surprises, BSD is the lower-risk answer, and it is drop-in for the 35 existing Redis stores. |
| Embedded OLAP | **DuckDB** | MIT | Already in use. Keep. |
| Object / blob | **MinIO** / IPFS | AGPL 3 / MIT | Already in the stack. |
| Search | **OpenSearch** | Apache 2 | Elasticsearch returned to AGPL in 2024; OpenSearch remains Apache 2. Meilisearch (MIT) is already wired and is sufficient at this scale. |

**Explicitly not chosen:** MongoDB. Its SSPL is not an OSI-approved open source licence, and a
platform with a zero-cost, self-hosted mandate should not take a licence whose terms turn on how
the software is offered.

## 4. Multi-tenancy: how per-AI and per-Location databases are laid out

The owner's expansion is the reason this matters. Three options, and the one chosen:

| Option | Shape | Verdict |
|---|---|---|
| One database per Location/AI | 90+ Postgres databases | Rejected. Recreates the 96-file problem with a heavier engine: no cross-entity query, 90 backup targets, 90 connection pools. |
| One schema per Location/AI | `the_spark.*`, `cornelius.*` in one database | **Chosen.** Cross-schema joins work, one backup, one pool, and permissions are per-schema so a Location cannot read another's rows. |
| Shared tables with a tenant column | `location_id` on every table | Rejected as the default. Row-level security is real but one missed predicate leaks across Locations, and this estate's own history is of controls that exist but do not act. |

The schema name derives from the CI identifier, so the CMDB and the database agree by
construction rather than by convention.

## 5. Migration: the classification rule

Every one of the 144 stores gets one of four dispositions. No store moves because of a general
policy; each moves because it matches a rule.

| Disposition | Rule | Count today |
|---|---|---|
| **Migrate** | System of record: data whose loss matters, or that another Location needs to query | the registries, audit, role, routing and CMDB stores |
| **Keep (embedded)** | Analytical, single-process, rebuildable from source data | DuckDB (6) |
| **Keep (ephemeral)** | Cache, rate-limit, session state; loss is recoverable by recomputation | `cache.db` and kin |
| **Delete** | Superseded or orphaned — a `.db` nothing opens any more | to be determined per store |

The disposition is recorded on the CI, not in this document, so it is queryable and cannot drift
from the store it describes.

**Order of work**, each step independently valuable:

1. Stand up PostgreSQL with pgvector, TimescaleDB and AGE in `docker-compose.production.yml`.
   Nothing migrates yet.
2. Extend `workers/backup-service` to speak PostgreSQL and MySQL. **This is issue #1146 and it
   is worth doing before any migration**, because migrating data into an engine the backup
   service cannot back up moves the risk rather than reducing it.
3. Classify all 144 stores onto the CI register.
4. Migrate the system-of-record stores, one Location at a time, dual-writing until the read
   path is switched.
5. Route the 114 unrouted stores through the Town Hall, as the Backlog Routing Register already
   requires for unowned work.

## 6. What is already built

- `src/cmdb/datastores.py` — discovers all 144 stores and maps each to a CI.
- `scripts/build_ci_register.py` — writes `docs/architecture/ci-register.json`.
- The counts in §1 are regenerated on every run, so this document's premises can be re-measured
  rather than believed.

## Sources

- [Redis vs Valkey in 2026: What the License Fork Actually Changed](https://dev.to/synsun/redis-vs-valkey-in-2026-what-the-license-fork-actually-changed-1kni)
- [The Redis License Timeline: BSD to SSPL to AGPL (2024-2026)](https://redisvsmemcached.com/redis-license-timeline/)
- [When the OSS is alive but the license isn't: Sentry, MongoDB, Elasticsearch, Redis](https://dev.to/osalt/when-the-oss-is-alive-but-the-license-isnt-sentry-mongodb-elasticsearch-redis-may-2026-3ec6)
- [Open Source Databases (2026): PostgreSQL, MySQL, ClickHouse, Cassandra & Beyond](https://www.jusdb.com/blog/open-source-databases-the-complete-guide)
- [The PostgreSQL Extensions Ecosystem in 2026](https://www.javacodegeeks.com/2026/03/the-postgresql-extensions-ecosystemin-2026.html)
- [15 PostgreSQL Extensions You Should Know in 2026](https://medium.com/@philmcc/15-postgresql-extensions-you-should-know-in-2026-6bdcf8872e49)
