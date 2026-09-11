# Trancendos Platform — Naming Conventions

Version: 1.1.0
Applies to: all services, workers, containers, modules, and CF Workers in this repository.

---

## 0. Platform vs model-base naming (the "Trancendos ≠ Tranc3" rule)

The **platform** is **Trancendos** — the GitHub org, the domain (`trancendos.com`), and the
product identity. **Tranc3** is one of the three AI **model bases** defined by the
Trancendos Models Matrix (`docs/governance/TRANCENDOS-MODELS-MATRIX.md`):

| Model base | Tier | Role |
|---|---|---|
| Trance-One | 1 | Sovereign / Orchestrator |
| T2ance | 2 | Primes |
| Tranc3 | 3 | Lead AI / AI base (default) |

Consequences:

- **New platform-level names use "Trancendos"**, never "Tranc3" (the Fly bots app is
  already `trancendos-bots` for this reason; the frontend Pages project is
  `trancendos-frontend`).
- **`tranc3-*` names are correct only where the thing genuinely serves the Tier-3
  engine**: `Tranc3Engine`, `tranc3-backend` (hosts the engine), `tranc3-ai` (edge proxy
  to it). These are model-scoped, not platform-scoped, and do not need renaming.
- The main repository being named `Tranc3` is **historical**: it predates the models
  matrix. A rename to a platform-scoped name (e.g. `Trancendos/trancendos-platform`) is
  an owner decision — GitHub redirects old clone/submodule URLs after a rename, so the
  blast radius is the ~51 files that self-reference `Trancendos/Tranc3` plus external
  integrations (Codecov, CodeQL, Mergify, Cloudflare Pages Git hook), which re-bind on
  first use or need a one-time re-link. Until that decision, docs must not describe the
  *platform* as "Tranc3".

---

## 1. Reference IDs (PLM-style)

Every component in the platform estate has an immutable TRC reference ID.

```
TRC-{PRIORITY}-{3-digit sequence}
```

| Segment | Values | Meaning |
|---|---|---|
| `TRC` | fixed | Trancendos |
| `PRIORITY` | P0–P3, INF | Component priority tier or infrastructure |
| `3-digit seq` | 001–999 | Unique sequential number within the tier |

Examples: `TRC-P0-001` (The Spark), `TRC-P1-014` (The HIVE), `TRC-INF-003` (Prometheus)

- References are **immutable** — once assigned they never change, even if the service is renamed or deprecated.
- New components get the next available number in their tier.
- Find all refs in `config/estate/registry.yaml`.

---

## 2. Docker Container Names

```
tranc3-{short-id}
```

- Always prefixed with `tranc3-` (the platform identifier)
- `short-id` = kebab-case identifier from `config/estate/registry.yaml`
- No numeric suffixes (that's what replicas/scaling is for)
- No `-worker`, `-service`, or `-app` suffixes (redundant)

| Short ID | Container name |
|---|---|
| `nexus` | `tranc3-nexus` |
| `infinity-auth` | `tranc3-infinity-auth` |
| `turings-hub` | `tranc3-turings-hub` |
| `observatory` | `tranc3-observatory` |

**Exception**: Infrastructure components (Traefik, Prometheus, Grafana, etc.) use `tranc3-{tool-name}` to distinguish from upstream tool defaults.

---

## 3. Docker Compose Service Names

```
{short-id}-service  (for workers with a -service directory)
{short-id}          (for other services)
```

The `docker_service` field in registry.yaml is the definitive name.

- Service names follow the directory name in `workers/`
- Example: `workers/infinity-portal-service/` → service name: `infinity-portal-service`
- Example: `workers/monitoring/` → service name: `monitoring`

---

## 4. Worker Directory Names

```
workers/{short-id}-service/     (preferred for new workers)
workers/{short-id}/             (allowed for top-level services)
```

- All new workers go in `workers/` as their own directory
- Directory name must match the `docker_service` field in registry.yaml
- Each worker directory must contain a `Dockerfile` and `main.py`

---

## 5. Python Module Names (src/)

```
src/{short_id_snake}/
```

- Snake_case version of the short ID
- Examples: `src/bio_neural/`, `src/warp_radio/`, `src/ai_gateway/`
- Every module directory must have an `__init__.py` that exports public symbols

---

## 6. Cloudflare Worker Names

```
tranc3-{short-id}      (new pattern, preferred)
infinity-{function}    (legacy pattern — do not create new)
trancendos-{function}  (legacy pattern — do not create new)
```

New CF Workers should use `tranc3-{short-id}`. Legacy workers keep their existing names until migrated.

---

## 7. Entity Names (canonical)

Canonical entity names are defined in `PLATFORM_ENTITIES.md` and `src/entities/platform.py`. They are **proper nouns** — always capitalised as shown.

Special cases:
- "The Digital Grid" — always with a space (ignore the known typo in the entity table)
- "Sashas Photo Studio" — no apostrophe
- "tAimra" (location) vs "tAImra" (Lead AI) — different capitalisation, both correct
- "The Guardian (Marcus Magnolia)" — full title required in entity contexts; `lead_ai` remains
  Infinity's primary/canonical AI, with a second additional lead AI, "The Orb of Orisis"

---

## 8. API Route Prefixes

```
/api/v{N}/{short-id}/
```

- All API routes versioned with `/api/v1/` (or later versions)
- Service-specific routes prefixed with service short-id
- Example: `/api/v1/spark/tools`, `/api/v1/hive/queue`

---

## 9. Environment Variable Prefixes

```
TRANC3_{SERVICE_UPPER}_{KEY}
```

- Platform-wide: `TRANC3_` prefix
- Service-specific: `TRANC3_{SHORT_ID_UPPER}_{KEY}`
- Example: `TRANC3_AUTH_JWT_SECRET`, `TRANC3_HIVE_QUEUE_URL`

---

## 10. Validation

Run `python scripts/estate_lint.py` to check the estate for:
- Registry container names matching the container compose actually creates
- Container name convention compliance, reported against the compose file
- Port conflicts
- Registry completeness
- docker-compose services not in registry
- Registry entries with no docker-compose service (if status is active/building)

Run `python scripts/check_estate_registry_alignment.py` to check every record's
`port`, `worker_path`, `docker_service` and `docker_container` against
`docker-compose.production.yml`, and every `# ── Name (Port N) ──` banner in that
file against the service beneath it. Both run in CI and both block.

**Why these are separate checks.** `docker_container` is a *mirror* of a
deployment fact, so the only enforceable rule for it is that it mirrors
correctly; the `tranc3-` convention is a judgement about the name itself and
belongs where the name is set, in compose. Applying the convention to the mirror
is what let the CMDB pass while disagreeing with the estate: 45 records held the
name the convention wants, compose created a different one, and nothing compared
the two. Fifteen more recorded a live, Traefik-routed Location as having no
deployment at all. A record consulted during an incident named a container that
does not exist on the host.

A field that legitimately cannot mirror compose — The Spark and Infinity Gate
have no port of their own, being in-process and embedded respectively — is
listed in that script's `ACCEPTED_DIVERGENCES` with a written reason, keyed by
`(ref, field)` so exempting one field never exempts the rest of the record.
