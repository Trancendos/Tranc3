# Repository-Derived CMDB: Automated Datastore and Container Discovery

> **PR:** [feat: derive the datastore and container CMDB, with container SBOMs (split 5/5 of #1207)](https://github.com/Trancendos/Tranc3/pull/1249) [[1]](https://github.com/Trancendos/Tranc3/pull/1249)
>
> **What is in this document.** How datastores and containers are automatically discovered from the repository and registered as Configuration Items, how their SBOMs are generated, and how the currency checks that keep the register honest work. For the container jurisdiction policy and the SBOM semantics, see [`docs/governance/CONTAINER-JURISDICTION.md`](https://github.com/Trancendos/Tranc3/pull/1249).

## Overview

The CMDB's datastore and container Configuration Items are **derived by walking the repository, not typed into a register.** That is the only way they stay true.

A hand-maintained CMDB describes the estate on the day someone last remembered to update it. Adding `sqlite3.connect("data/new.db")` to a worker is a one-line change that nobody thinks to carry into a separate register — and it is exactly the kind of change that must not go missing from one. The same applies to new services in `docker-compose.production.yml`: the file is updated, the service runs, and the CMDB remains silent [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

This approach covers two CI classes:

| CI class | Discovery method | Output |
|---|---|---|
| `Datastore` | Walk `*.py` for engine usage patterns | `docs/architecture/ci-register.json` |
| `Container` | Parse `docker-compose.production.yml` | `docs/architecture/ci-register.json` + `docs/architecture/sbom/*.cdx.json` |

**Measured: 144 datastores registered, 174 containers** [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Contrast with the EA workbook

`docs/architecture/ea-workbook/` is a 19-file CSV CMDB describing the business-services layer: service inventory, applications, APIs, deployments, environments, and hosting. It is manually maintained and intentionally scoped — every row is seeded from real anchor services and CI validates structural integrity only; it does not verify that a row's claims still match the code .

The derived CMDB described in this document is complementary, not a replacement: the EA workbook answers "what business services does this platform run and who owns them at the service level"; the derived register answers "what datastores and containers are running in the estate right now, as observable from the repository." The two are joined via the `jurisdiction` field, which maps each CI back to a Location in [`PLATFORM_ENTITIES`](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/src/entities/platform.py).

For the governance context on automated observation and why sensors that cannot see must say so, see [`docs/governance/IMMUNE-SYSTEM.md`](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/docs/governance/IMMUNE-SYSTEM.md) and `docs/governance/OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md`.

## Derived Datastores

**Source:** [`src/cmdb/datastores.py`](https://github.com/Trancendos/Tranc3/pull/1249) · **Output:** `docs/architecture/ci-register.json` (datastore CIs)

### How discovery works

`datastores.discover()` walks every `*.py` file in the repository (skipping `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, and `archive`) and applies a set of engine-detection patterns to each file's text [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

**Engine detection patterns** (`ENGINE_PATTERNS`):

| Engine | Detected by |
|---|---|
| `postgresql` | `psycopg`, `postgresql://`, `asyncpg` |
| `mysql` | `pymysql`, `mysql://`, `mysqlclient`, `aiomysql` |
| `duckdb` | `duckdb` |
| `redis` | `redis.`, `redis(s)://`, `aioredis` |
| `sqlite` | `sqlite3.connect`, `sqlite:///` |

Patterns are ordered: a file that imports both `sqlite3` and `psycopg` is recorded once per store path, not once per import [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Locator identification

For **file-backed stores** (SQLite, DuckDB), the discovery extracts path literals matching `*.db`, `*.sqlite`, `*.sqlite3`, or `*.duckdb`. The locator chosen is the most specific literal observed across all evidence files — longest string wins, then lexicographic — so `/data/ai_governance.db` beats `ai_governance.db`. Without this rule the winner was decided by `Path.rglob` traversal order, causing the same tree to produce different registers on different filesystems and `--check` to report STALE when nothing had changed [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

For **networked stores** (PostgreSQL, MySQL, Redis), connection strings are environment variables resolved at runtime, so the locator is recorded as `env://ENGINE_URL` (e.g. `env://POSTGRESQL_URL`). Each module that opens a networked store becomes its own CI when name collisions exist, to prevent two distinct Redis clients from merging onto a single CI [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Location ownership

Each evidence file path is resolved to a Location via `PLATFORM_ENTITIES` [[2]](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/src/entities/platform.py): the entry whose `worker_path` is the longest prefix of the file's repo-relative path wins. When multiple Locations open the same store, `jurisdiction` is set to the alphabetically-first claimant, and all claimants are recorded in a `jurisdictions` list on the CI. This keeps the `jurisdiction` field stable across runs — the previous "first claimant wins" rule meant the owner changed based on which file `rglob` reached first [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Test fixture exclusion

A datastore is marked `test_only` when every file in its evidence list lives under `tests/` or a `/tests/` path segment. Test-fixture databases are real SQLite usage and real noise in a migration plan, so they are **counted separately** rather than silently dropped: the register records `datastores_excluded_as_test_fixtures` so a reader can account for the difference without reading the code. **71 datastores** are currently excluded as test-only [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Measured results

**144 datastores registered** as production Configuration Items [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Configuration Item fields

| Field | Description |
|---|---|
| `ci_id` | Stable identifier: `CI-DS-<engine>-<name>[-<qualifier>]` |
| `ci_class` | `"Datastore"` |
| `name` | Basename of the database file, or `engine@module` for networked stores |
| `engine` | `postgresql`, `mysql`, `duckdb`, `redis`, or `sqlite` |
| `locator` | Most-specific observed path literal, or `env://ENGINE_URL` |
| `file_backed` | `true` for file-based stores; `false` for networked |
| `jurisdiction` | Owning Location, or `_unrouted_` if none resolves |
| `test_only` | `true` when all evidence is under `tests/` |
| `evidence` | Sorted list of source files that open this store |
| `evidence_count` | Count of evidence files |

When a store is observed under multiple locators or by multiple Locations, the additional `locators` and `jurisdictions` fields are included so the merge is visible at a glance [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

## Derived Containers

**Source:** [`src/cmdb/containers.py`](https://github.com/Trancendos/Tranc3/pull/1249) · **Output:** `docs/architecture/ci-register.json` (container CIs)

### How discovery works

`containers.discover()` parses `docker-compose.production.yml` and returns one `Container` record per service. The services are iterated in sorted order so the register is deterministic [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Container provenance

Each container is classified as one of two provenance types:

- **`built`** — the service has a `build:` directive in compose; we control the Dockerfile and therefore the image contents.
- **`pulled`** — the service uses a pre-built third-party image via `image:`; we do not choose what goes in it.

This distinction matters for SBOMs: a pulled image with no requirements manifest cannot be inventoried from source alone — an image SBOM is the only way to know its contents [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Dockerfile analysis

For built containers, the Dockerfile is read to extract:

- **Base images** — every `FROM` directive (`_FROM_RE`). The full chain is recorded (multi-stage builds included).
- **Final `USER` directive** — used to determine `runs_as` and `runs_as_root`. A container with no `USER` directive runs as root, and this is recorded as a containment fact rather than omitted. Currently **1 built container** runs as root [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

**Critical fix:** `dockerfile:` directives in compose are resolved **relative to `context:`**, not to the repository root. The prior code treated them as repo-relative, which meant a service like:

```yaml
build:
  context: ./workers/analytics-service
  dockerfile: Dockerfile
```

would read the *root* `Dockerfile` instead of `workers/analytics-service/Dockerfile`. Before this fix, 74 of 88 built containers carried a bare `dockerfile: Dockerfile` filename, and 87 of 88 reported the same base image. The three Rust services (`nexus-ws-rs`, `vault-service-rs`, `rate-limit-service-rs`) were showing Python base images and 76 Python packages each. `_resolve_dockerfile()` corrects this [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Location ownership

Location is resolved in two steps, using the Dockerfile's directory as the primary anchor (since most services build with `context: .`):

1. **Path-based:** match the Dockerfile's parent directory against `PLATFORM_ENTITIES` `worker_path` entries. The longest prefix match wins.
2. **Port-based:** if no path match is found, walk the container's declared ports and call `get_entity_for_port()`. Catches workers whose directory name and declared path disagree.

Path matching takes precedence: a port can be reassigned without moving code, so a directory match is the stronger claim [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Measured results

**174 containers registered** — 88 built from our Dockerfiles, 86 pulled third-party images [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Shared jurisdiction model

Per the owner's requirement (documented in [`docs/governance/CONTAINER-JURISDICTION.md`](https://github.com/Trancendos/Tranc3/pull/1249)), every container CI carries **two** ownership fields, never merged:

| Field | Meaning | Can be unknown? |
|---|---|---|
| `jurisdiction` | The Location whose code runs in this container — accountable for **what it does** | Yes → `_unrouted_` |
| `custodian` | **The Ice Box**, always — accountable for **that it runs safely**: isolation, resource limits, sandbox and VM stability | **No** |

The asymmetry is deliberate. 86 of the estate's containers are third-party images running nobody's code here, so their `jurisdiction` is genuinely `_unrouted_`. Their containment is not unknown. Merging the two fields into a single owner would produce an estate where 86 containers read as unmanaged [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

**Currently:** 46 containers have a resolved jurisdiction; 128 are `_unrouted_` [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Configuration Item fields

| Field | Description |
|---|---|
| `ci_id` | `CI-CT-<service-name>` |
| `ci_class` | `"Container"` |
| `name` | Service name from compose |
| `container_name` | `container_name:` from compose |
| `image` | Image tag (pulled) or `"built-from-source"` |
| `provenance` | `"built"` or `"pulled"` |
| `base_images` | List of `FROM` stages |
| `build_context` | Compose `context:` path |
| `dockerfile` | Resolved Dockerfile path (relative to repo root) |
| `jurisdiction` | Owning Location, or `_unrouted_` |
| `custodian` | Always `"The Ice Box"` |
| `runs_as` | Final `USER` directive value, or `"root (no USER directive)"` |
| `runs_as_root` | `true` when built and USER is absent/root/0 |
| `ports` | Declared port mappings |
| `volumes` | Declared volume mounts |
| `networks` | Declared networks |
| `requirements` | Requirement manifests shipping with this container |
| `sbom_ref` | Path to this container's SBOM (`docs/architecture/sbom/<name>.cdx.json`) |
| `sbom_present` | Whether the SBOM file currently exists on disk |

### Partial checkout protection

`CannotEnumerateContainers` is raised — rather than returning an empty or truncated list — in three cases [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

1. **PyYAML not installed** — the compose file cannot be parsed.
2. **`docker-compose.production.yml` absent** — no container inventory can be taken.
3. **Declared submodules not checked out** — `.gitmodules` lists paths that are empty directories. Without the submodule contents, the register regenerates shorter and reports that shorter version as authoritative.

The third case was found in practice: the CI job checked out with `fetch-depth: 0` and no submodule recursion, so The Town Hall (`workers/cranbania`) and Magna Carta (`compliance/magna-carta`) were missing. `build_ci_register.py` regenerated one line shorter, dropping `workers/cranbania/package.json` from CranBania's evidence list, and `--check` reported STALE in CI while passing on every developer machine that had the submodules checked out. The fix adds `submodules: recursive` to the topology job's checkout step [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

This is an instance of the principle documented in [`docs/governance/IMMUNE-SYSTEM.md`](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/docs/governance/IMMUNE-SYSTEM.md#L34-L55): a sensor that cannot see reports exactly what a clean estate reports — which is the defect, not the outcome.

## Container SBOMs

**Source:** [`scripts/build_container_sboms.py`](https://github.com/Trancendos/Tranc3/pull/1249) · **Output:** `docs/architecture/sbom/*.cdx.json` (174 files)

### Format choice

SBOMs are emitted in **CycloneDX 1.6** format. CycloneDX is the format used here because it is security-oriented and can describe services — not just libraries — which matches the shape of this platform's Locations [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Source SBOMs vs image SBOMs

Two kinds of SBOM exist, and conflating them produces an inventory that looks complete and is not [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

| | Source SBOM | Image SBOM |
|---|---|---|
| Generated from | Dependency manifests in the repository (`requirements.txt`, `package.json`, `Cargo.lock`) | A built image, using `syft` or `trivy` |
| Sees | Declared application dependencies | OS packages, system libraries, base-layer contents, everything from every `RUN` |
| Answers CVE questions | Partially — only declared app deps | Properly — full image contents |
| What it misses | Base-image OS packages, transitive resolution, system libraries | Nothing at the image level |

`build_container_sboms.py` currently emits **source SBOMs**, and stamps every document with two properties that make this explicit [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```json
{
  "name": "trancendos:sbom-scope",
  "value": "source"
},
{
  "name": "trancendos:sbom-scope-note",
  "value": "Declared application dependencies only. Base-image OS packages, system libraries and transitively resolved versions are NOT included. Generate an image SBOM with syft or trivy for those."
}
```

**Measured: 0 image SBOMs exist today.** Every SBOM in `docs/architecture/sbom/` is source-scoped [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

The `--strict` flag refuses to emit source SBOMs at all — for use once image SBOMs from a CI pipeline are available. This prevents a regression where the source-SBOM generation silently continues after the transition [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Why both an SBOM and a Configuration Item are needed

Per [`docs/governance/CONTAINER-JURISDICTION.md`](https://github.com/Trancendos/Tranc3/pull/1249), an SBOM alone is insufficient:

| | SBOM | Configuration Item |
|---|---|---|
| Answers | What components are in this thing | What is this thing, who answers for it, what does it connect to |
| Has an owner | No | Yes |
| Has a lifecycle state | No | Yes |
| Has relationships | Component→component only | Depends-on, runs-on, custodied-by |
| Changes are governed | No | Yes |
| Good at | "Is CVE-2026-x in my estate?" | "Who do I call, and what breaks if I stop it?" |

The model uses both, joined: the container is registered as a CI, and its SBOM is referenced from that CI via the `sbom_ref` field. Marking containers only as SBOMs would produce an estate that can answer a CVE question and cannot answer an ownership question [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### What each SBOM contains

For **built containers**, the SBOM is populated from requirement manifests found in the Dockerfile's directory (see [Technical Details](#technical-details)):

- `requirements*.txt` → parsed as PEP 508 Python packages (`pkg:pypi/<name>@<version>`)
- `package.json` → recorded as a manifest reference
- `Cargo.lock` → parsed into `pkg:cargo/<name>@<version>` components (for the three Rust services: `nexus-ws-rs`, `vault-service-rs`, `rate-limit-service-rs`)

Unpinned dependencies are recorded with a `trancendos:pinned = false` property rather than omitted — an unpinned dependency means the image contents differ between builds, which is exactly what an inventory should surface [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

For **pulled containers** with no manifest, the SBOM carries a `trancendos:no-manifest` property explaining that an image SBOM is the only way to know the container's contents [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Deterministic output

Serial numbers are content-hashed (`SHA-256` of the `ci_id`), so regenerating an unchanged container produces no diff and `--check` remains meaningful [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Generated artifacts

174 CycloneDX documents under `docs/architecture/sbom/`, one per container service [[1]](https://github.com/Trancendos/Tranc3/pull/1249). Examples:

- `docs/architecture/sbom/analytics-service.cdx.json` — built, 7 Python components: fastapi, starlette, uvicorn, pydantic, duckdb, polars, pandas
- `docs/architecture/sbom/airflow.cdx.json` — pulled, 0 components (no manifest; image SBOM is the only way to know its contents)
- `docs/architecture/sbom/artifactory-service.cdx.json` — built, 4 Python components: fastapi, uvicorn, httpx, pydantic

## The CI Register

**Source:** [`scripts/build_ci_register.py`](https://github.com/Trancendos/Tranc3/pull/1249) · **Output:** `docs/architecture/ci-register.json`

### What it generates

`build_ci_register.py` calls `datastores.discover()` and `containers.discover()` and writes a single JSON register covering the full estate [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```
docs/architecture/ci-register.json
├── generated_from
├── custodian_of_all_containers
├── counts
│   ├── datastores_registered
│   ├── datastores_excluded_as_test_fixtures
│   ├── containers_registered
│   ├── containers_built_here
│   ├── containers_pulled
│   ├── containers_with_sbom
│   ├── datastores_unrouted
│   └── containers_unrouted
└── configuration_items   # all Datastore and Container CIs
```

Test-fixture datastores are excluded from `configuration_items` but counted in `datastores_excluded_as_test_fixtures`. This transparency allows a reader to account for the difference between the total discovered stores and the registered ones without reading the code [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Usage

```bash
# Write the register (normal run)
python3 scripts/build_ci_register.py

# Fail if the committed register is stale
python3 scripts/build_ci_register.py --check

# Show unrouted and un-SBOM'd gaps only
python3 scripts/build_ci_register.py --gaps
```

### Currency checks in CI

The `--check` flag is wired into `.github/workflows/ci.yml` as `CI register is current`. It fails if the committed register differs from what the scripts would generate today [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```yaml
- name: CI register is current
  run: python scripts/build_ci_register.py --check
```

When staleness is detected, the check prints a **unified diff** of exactly what changed — not just the word `STALE`. This is deliberate: a stale-register message without a diff sent multiple rounds of debugging guessing at what a CI runner saw that a developer machine did not. The diff makes the gap visible [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Both checks were probed before being trusted

A currency check that cannot detect staleness is the defect this estate keeps finding [[1]](https://github.com/Trancendos/Tranc3/pull/1249). Each check was made to fail before it was trusted:

| Check | Perturbation | Result |
|---|---|---|
| `build_ci_register.py --check` | Drop one CI from the register | rc=1; restore → rc=0 |
| `build_container_sboms.py --check` | Drop 1 of 7 components from `analytics-service.cdx.json` | rc=1; restore → rc=0 |

Both artifacts were **genuinely stale** when ported from PR #1207 to current main, and the checks caught this on their first real run:

- `datastores_excluded_as_test_fixtures` had moved from 69 → 71
- Three SBOMs no longer matched their manifests: `analytics-service` (its worker was rewritten by PR #1242), `llamaindex-service`, and `tranc3-backend`

Both were regenerated with the repo's own tooling before this PR merged [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### What happens when enumeration fails

`build_ci_register.py` does not catch `CannotEnumerateContainers` and degrade to an empty container list. With PyYAML absent, the old behaviour wrote a register reporting "containers with no SBOM: 0" and exited 0 — an appearance of perfect coverage produced by a run that had enumerated nothing. The exception is allowed to propagate, so "could not measure" is distinguishable from "measured, and it is fine" [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

## Governance and Rationale

### Written basis: CONTAINER-JURISDICTION.md

[`docs/governance/CONTAINER-JURISDICTION.md`](https://github.com/Trancendos/Tranc3/pull/1249) is the authoritative policy document for container jurisdiction, the SBOM model, and the scanning roadmap. It was introduced alongside this PR and settles three owner questions:

1. **The SBOM question** — what "marking containers as SBOMs" means and why a CI is also needed
2. **The shared jurisdiction model** — `jurisdiction` (what the container does) vs `custodian` (that it runs safely), and why they are always separate fields
3. **What is measured today** — honest accounting of 174 containers, 0 image SBOMs, 1 built image running as root

### The Ice Box as management centre

`workers/ice-box-service/` exposes `/scan`, `/quarantine`, and `/stats` endpoints and is designated as the management centre for sandboxes, VMs, and containers across Docker, Podman, and Kubernetes [[1]](https://github.com/Trancendos/Tranc3/pull/1249). Today the Ice Box quarantines artifacts; it does not yet know that 174 containers exist. The CI register is step 1 of closing that gap.

### Build order for container scanning maturity

The path from the current inventory to full runtime security coverage, in dependency order [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

| Step | Description | Status |
|---|---|---|
| 1. Inventory | The Ice Box reads the container CIs via the register | ✅ Done — register exists |
| 2. Image SBOMs | `syft` against each built image in CI, replacing source SBOMs | ⬜ Next |
| 3. Runtime scanning | `trivy`/`grype` against images and running containers; findings land on the container CI, giving each vulnerability an owner and a custodian immediately | ⬜ Depends on step 2 |
| 4. Runtime posture | Containment facts The Ice Box is custodian of: runs-as-root, privileged, host mounts, capability sets, missing resource limits | ⬜ Requires runtime, not just compose |
| 5. Podman and Kubernetes | Same CI shape for pods and Podman containers; `runtime` becomes an attribute on the existing `Container` CI class | ⬜ Future |

Steps 3–5 correspond to Action 2 of the owner's five Actions, and `docs/governance/CONTAINER-JURISDICTION.md` records where that Action lands: in The Ice Box, the Location already designated for sandbox isolation, rather than a new one [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Relationship to other governance documents

| Document | Relationship |
|---|---|
| `docs/governance/OBSERVABILITY-AND-AUTOMATION-GOVERNANCE.md` | The EA-workbook-backed CMDB (business services layer, manually maintained); this derived register is the datastore/container complement |
| `docs/architecture/ea-workbook/README.md` | CSV CMDB for business services; structural integrity validated by CI but content not verified against code |
| [`docs/governance/IMMUNE-SYSTEM.md`](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/docs/governance/IMMUNE-SYSTEM.md) | Sensor model: defines that a sensor which cannot see must report that it could not see, not report a clean result — the principle encoded in `CannotEnumerateContainers` |

### The honest measurement philosophy

Throughout this system, partial results are labeled as partial and enumeration failures raise exceptions rather than returning empty lists:

- **`datastores_excluded_as_test_fixtures`** is counted and exposed in the register header, not silently dropped
- **`trancendos:sbom-scope = source`** is stamped on every SBOM, with an explicit note about what it did not look at
- **`CannotEnumerateContainers`** is raised when PyYAML is missing, the compose file is absent, or submodules are not checked out — preventing "could not measure" from reading as "measured and found nothing"
- **`--check` prints a diff**, not just a verdict, so the cause of staleness is visible without cloning and guessing

This follows the principle in [`docs/governance/IMMUNE-SYSTEM.md`](https://github.com/Trancendos/Tranc3/blob/05885b06850bbdb569a922e385314734430ddd1b/docs/governance/IMMUNE-SYSTEM.md#L34-L55): a sensor that cannot see reports exactly what a clean estate reports, which is the defect, not the outcome.

## Usage for Developers

### Adding a new datastore

No action required beyond writing the code. When you add `sqlite3.connect("data/mystore.db")` or any supported engine usage to a Python file, it will be **automatically discovered** on the next `build_ci_register.py` run [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

To check what would be registered:

```bash
python3 scripts/build_ci_register.py
```

To verify the committed register reflects your change:

```bash
python3 scripts/build_ci_register.py --check
```

**Ensure Location ownership resolves:** if your worker's path is not yet in `PLATFORM_ENTITIES` (`src/entities/platform.py`), its jurisdiction will be `_unrouted_`. Add the Location's `worker_path` entry so the datastore is attributed correctly [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Adding a new container service

1. **Add the service to `docker-compose.production.yml`** — define the `build:` or `image:` stanza, ports, volumes, and networks as usual.

2. **Generate its SBOM:**

   ```bash
   python3 scripts/build_container_sboms.py
   ```

   This writes `docs/architecture/sbom/<service-name>.cdx.json`. For a built service, include a `requirements*.txt`, `package.json`, or `Cargo.lock` in the Dockerfile's directory.

3. **Regenerate the CI register:**

   ```bash
   python3 scripts/build_ci_register.py
   ```

   This writes `docs/architecture/ci-register.json` with the new container CI included.

4. **Commit both artifacts** — CI will verify they match on every subsequent push.

### What CI checks on every push

Two checks run in the topology job of `.github/workflows/ci.yml` [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```yaml
- name: CI register is current
  run: python scripts/build_ci_register.py --check

- name: Container SBOMs are current
  run: python scripts/build_container_sboms.py --check
```

If either check fails, the output shows a unified diff of exactly what changed. Regenerate with the scripts above to fix it.

> **Note on the CI checkout:** the topology job checks out with `submodules: recursive`. Without this, the two submodule Locations — The Town Hall (`workers/cranbania`) and Magna Carta (`compliance/magna-carta`) — are missing from the tree, the register regenerates one line shorter, and `--check` reports STALE in CI while passing locally [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Checking gaps

To see which datastores and containers lack a resolved Location (and therefore have `_unrouted_` jurisdiction):

```bash
python3 scripts/build_ci_register.py --gaps
```

To see SBOM coverage and missing manifests:

```bash
python3 scripts/build_container_sboms.py --report
```

Both commands output the counts without modifying any files.

## Technical Details

This section documents the precision rules in [`src/cmdb/containers.py`](https://github.com/Trancendos/Tranc3/pull/1249) and [`src/cmdb/datastores.py`](https://github.com/Trancendos/Tranc3/pull/1249) that keep the register deterministic and correct across different environments.

### Dockerfile path resolution

Compose resolves `dockerfile:` directives **relative to `context:`**, not relative to the repository root. `_resolve_dockerfile()` in `src/cmdb/containers.py` applies this rule [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```python
def _resolve_dockerfile(build_context: str, dockerfile: str) -> str:
    """Repo-relative path to a service's Dockerfile.

    Compose resolves `dockerfile:` against `context:`, not against the
    repository root.
    """
```

**Why this matters:** The estate's most common compose shape is:

```yaml
build:
  context: ./workers/analytics-service
  dockerfile: Dockerfile
```

Before this fix, `dockerfile: Dockerfile` was read as `./Dockerfile` (the root Dockerfile). Every such service reported the root's base image and root's `requirements*.txt`. Measured before the fix: 74 of 88 built containers carried bare `dockerfile:` filenames, all 74 were attributed root manifests, and 87 of 88 reported the same base image. The container half of the CMDB was describing one image 87 times [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Requirement manifest attribution

`_requirements_near()` searches for manifests in the **Dockerfile's directory**, not the build context [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```python
# The Dockerfile's own directory, not the build context. Nearly every service
# here builds with `context: .` (the repo root), so using the context listed
# every root-level requirements file as though it shipped inside each of the
# 88 images.
candidates = [str(Path(dockerfile).parent)] if dockerfile else []
```

Manifests detected: `requirements*.txt`, `package.json`, `Cargo.lock`. The Cargo.lock support ensures Rust services (`nexus-ws-rs`, `vault-service-rs`, `rate-limit-service-rs`) report their crate dependencies as `pkg:cargo/<name>@<version>` components, not Python packages [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Locator stability

`Datastore.record_locator()` chooses the **most specific** literal across all evidence files — the longest string, then lexicographic — so the selected locator is stable regardless of `Path.rglob` traversal order [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```python
def record_locator(self, literal: str) -> None:
    self.locators.add(literal)
    self.locator = max(sorted(self.locators), key=len)
```

### Location stability

`Datastore.record_location()` resolves `jurisdiction` to the **alphabetically first** Location among all claimants [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```python
def record_location(self, name: str) -> None:
    self.locations.add(name)
    self.location = sorted(self.locations)[0]
```

The previous "first claimant wins" rule meant `studio.db` — opened by both Sashas Photo Studio and The Studio — changed jurisdiction between two runs of the same generator based on `rglob` order.

### CI sort order

`datastores.discover()` returns stores sorted by `ci_id`, and `containers.discover()` iterates compose services in sorted order. Both ensure the register is byte-identical across runs on different filesystems [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Evidence tracking

Every source file that opens a datastore, and every compose service definition, is recorded in the `evidence` field of the CI. For datastores, the evidence list is sorted. This is how the register proves it is derived rather than asserted: a reader can trace every CI back to the files that generated it [[1]](https://github.com/Trancendos/Tranc3/pull/1249).

### Deterministic SBOM serial numbers

`build_container_sboms.py` uses `SHA-256(ci_id)[:32]` as the CycloneDX `serialNumber` [[1]](https://github.com/Trancendos/Tranc3/pull/1249):

```python
"serialNumber": "urn:uuid:" + hashlib.sha256(container.ci_id.encode()).hexdigest()[:32],
```

This means regenerating an unchanged container produces an identical document, so `--check` only reports STALE when the manifest contents or container definition have actually changed.
