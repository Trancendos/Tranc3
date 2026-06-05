# Trancendos Platform — Naming Conventions

Version: 1.0.0  
Applies to: all services, workers, containers, modules, and CF Workers in this repository.

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
- "The Guardian (Anchor: Orb of Orisis)" — full title required in entity contexts

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
- Container name convention compliance
- Port conflicts
- Registry completeness
- docker-compose services not in registry
- Registry entries with no docker-compose service (if status is active/building)
