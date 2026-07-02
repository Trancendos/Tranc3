# Forensic Assessment — Tranc3 Repository (31 May 2026)

## Executive summary (honest)

| Question | Answer |
|---|---|
| Is production consolidation in `main`? | **No** — `main` is at `9a62767`; consolidation is on `cursor/production-readiness-consolidation-6d5c` at `028f13e+` |
| Can you proceed? | **Yes**, after merging consolidation branch and setting production env vars |
| Is the platform production-ready today? | **Partially** — core APIs work in test mode; full prod needs merge + env + UAT compose validation |
| Is "Sage" a Prime? | **No** — **Syntax-Sage** is Tier 4 Agent β at The Lab; confusion comes from test fixtures / stale docs |

---

## Branch & PR forensic state

### Open PRs (should close after consolidation merge)

| PR | Branch | Verdict |
|---|---|---|
| #84 | `claude/loving-mendel-dPsZ7` | **Superseded** by consolidation merge |
| #85 | Jules LoginPage | **Merged** into consolidation |
| #86 | `merge/aeonmind-into-main` | **Skip** — destructive diff, largely in main via #71 |
| #87 | phase16 | **Merged** into consolidation |
| #88 | phase24 | **Merged** into consolidation |
| #89 | ChatView prompts | **Merged** into consolidation |

### Extra cursor branches (noise)

Multiple `cursor/production-readiness-*` and `cursor/api-startup-readiness-*` branches exist — consolidate to one PR to avoid review fatigue.

---

## Codebase health findings

### Critical (P0)

1. **`main` import gap** — `api.py` imports `src.auth.rbac`, `src.gbrain.pipeline` before PR #84 landed on main.
2. **Entity overrides siloed** — Renames in Admin DB not reflected in worker `/health` JSON.
3. **Secrets required** — `SECRET_KEY`, `JWT_SECRET`, `DATABASE_URL`, `REDIS_URL` hard-fail at startup (correct, but blocks naive deploy).

### High (P1)

4. **No pytest for `/admin/entities`** — rename logic unverified in CI.
5. **Spelling schism** — MacIntyre vs McIntyre across docs/templates.
6. **Guardian title** — Marcus Magnolia vs Anchor: Orb of Orisis in different files.
7. **Lead AI "To be Defined"** — DocUtari still placeholder in canonical table.

### Medium (P2)

8. **sentence-transformers optional** — MCP tool RAG degrades without encoder.
9. **RS256 keys optional** — Falls back to HS256 with warning.
10. **Cloudflare workers** — Legacy edge still in repo; Traefik migration incomplete.

### Low (P3)

11. **Pydantic alias warnings** in GBrain worker tests.
12. **`.security_learning/`** local scan artifacts should not be committed.

---

## Test evidence (consolidation branch)

346 tests passed locally across:

- `test_smoke`, `test_knowledge_brain`, `test_gbrain_worker`
- `test_canonical_routes` (43), `test_compatibility`
- `test_microceph_provider`, `test_oci_adaptive_provider`
- `test_ai_gateway_providers`

`import api` succeeds with test env vars.

---

## Related GitHub org repos (utilization)

| Repo | Utilization |
|---|---|
| `Trancendos/Tranc3` | Primary monorepo — current work |
| `Trancendos/shared-core` | Align with `Dimensional/` + `shared_core/` re-exports |
| `Trancendos/trancendos-ecosystem` | Financial/Alervato — integrate via Arcadian Exchange workers |
| `Trancendos/the-hive`, `the-nexus`, `the-observatory` | Focused services — map to workers 8022, 8004, 8007 |
| `Trancendos/the-workshop` | Forgejo CI — already canonical per CLAUDE.md |
| `Trancendos/the-void` | Vault — migrating to `workers/vault-service` |
| Per-location repos (`the-library`, `the-citadel`, …) | Future split targets when Tranc3 segments ship |

**Honest note:** Most capability already lives in Tranc3 monorepo; satellite repos are organizational boundaries, not required for next production milestone.

---

## Remediation implemented (this session)

- `src/entities/effective.py` — shared effective name resolver
- `PATCH /admin/entities/{pid}/tier` — display tier correction
- `GET /admin/orchestrators` — Tier 1 listing
- Dashboard **Entity Name Registry** UI (Infinity-Admin view)
- Docs: Infinity matrix, SWOT, forensic, master worker, roadmap

---

## Remaining work (truthful)

See `docs/PRODUCTION_ROADMAP.md` for phased plan.
