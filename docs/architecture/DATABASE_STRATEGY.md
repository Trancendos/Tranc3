# Hybrid Database Strategy

**Status**: Guidance for v0.9.0 and beyond

---

## 1. Current Reality (as of latest main)

- Most of the 29 workers still use **per-worker SQLite** (zero-cost isolation, replaced Cloudflare D1).
- High-volume messaging/queues are moving / have moved to **NATS JetStream**.
- Shared state (users, identity, some config) already has a **PostgreSQL** path via SQLAlchemy + `psycopg2-binary`.
- Some optional services spin up their own Postgres instances.

SQLite has **not** been fully removed — and that is intentional for many isolated workers.

---

## 2. Target Hybrid Model

| Data Type                    | Recommended Store          | Reason |
|-----------------------------|----------------------------|--------|
| Isolated worker state       | SQLite (per worker)        | Simple, zero-cost, true isolation |
| High-volume queues / messaging | NATS JetStream          | Throughput + durability |
| Shared user / identity / config | PostgreSQL             | Consistency + concurrent access |
| Audit / analytics logs      | PostgreSQL or dedicated    | Queryability + retention |
| Secrets                     | Infinity Void (current)    | Already strong |

---

## 3. Migration Approach (No Big-Bang)

1. Document this hybrid strategy clearly (this file).
2. Make **PostgreSQL the recommended default** for any new shared state.
3. Provide Alembic migration helpers for existing shared tables.
4. Leave per-worker SQLite unchanged unless a specific worker becomes a contention point.
5. Finish removing any remaining high-volume SQLite queue usage.
6. Publish clear configuration examples for:
   - Pure SQLite (local/dev)
   - Hybrid (production)

---

## 4. Practical Next Steps for v0.9.0

- [ ] Write migration scripts for any currently shared SQLite tables that should move to Postgres.
- [ ] Ensure `DATABASE_URL` is the single source of truth for shared state.
- [ ] Add a short section to the Deployment Runbook explaining when to use SQLite vs Postgres vs NATS.
- [ ] Verify that high-volume paths no longer depend on SQLite queues.
