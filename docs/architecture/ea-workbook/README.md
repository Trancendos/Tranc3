# EA / CMDB Workbook

A 17-file CSV configuration-management-database (CMDB) layer describing Trancendos's
operational estate: business services → technical services → applications → APIs →
deployments, down through environments, hosting, servers, databases, storage, DNS,
load balancers, firewalls, dependencies, vulnerability findings, and configuration
drift.

**Scope note:** every row is seeded from 6 real anchor services (see below), out of the
90+ services listed in `CLAUDE.md`'s worker map. This is intentionally a depth-first
anchor set, not a full inventory — treat any row for a service not in the anchor table
as illustrative/unverified until it's added and checked against real code the same way
the anchor rows were. CI validates only structural CSV integrity
(`scripts/validate_ea_workbook.py`, wired into `.forgejo/workflows/ci.yml` and
`.pre-commit-config.yaml`) — it does not verify that a row's claims still match the code.

`scripts/register_ea_workbook_services.py` reads `02_service_inventory.csv`'s
`HealthCheckPath`/`HealthCheckInterval` columns and registers each anchor service with
`health-aggregator`'s dynamic registry (`POST /services`), so this data actually drives
live monitoring instead of only being read by humans. It now runs automatically from
`.forgejo/workflows/deploy-self-hosted.yml`'s `verify-and-register-self-hosted` job
(alongside `scripts/post_deploy_verify.py`), both as best-effort/`--soft` steps.

`Trancendos_Master_Service_Matrix.xlsx` (this directory) is a companion workbook mirroring
the same 8 components (the 6 CSV anchors plus Traefik and health-aggregator) in a
service/route/endpoint/dependency/security/deployment matrix format, plus a broad
structural scan of all 94 real `workers/*` directories and a real, non-fictional
Improvement Roadmap of gaps found while building it. Regenerate it with
`python scripts/build_master_service_matrix.py` after updating the facts baked into that
script — it is not hand-edited directly.

## Why this exists

`PLATFORM_ENTITIES.md` and `docs/architecture/master-schema.md` answer *who owns what*
(the 43 named locations, their Lead AIs, and the Tier 1–5 `PID-/AID-/SID-/NID-` identity
taxonomy). This workbook answers a different question — *what infrastructure actually
runs, how it's wired, and what's out of compliance* — the operational gaps called out in
the platform architecture review: no server inventory, no DB topology, no deployment
runbooks, no SLA/dependency mapping, no vulnerability tracking.

**This workbook does not mint new AI/agent identities.** `Owner` columns reference the
Tier 3 Lead AI names already canonical in `PLATFORM_ENTITIES.md` / `CLAUDE.md`. Entity IDs
in this workbook (`SRV-`, `APP-`, `DB-`, `STO-`, …) are infrastructure/CMDB keys — a
different axis from the `PID-/AID-/SID-/NID-` AI-tier IDs and never overlap with them.

## Grounding — seeded from real services, not placeholders

Rows are seeded from six services already live or partial in this repo, per `CLAUDE.md`:

| Anchor | Location | Owner (Tier 3) | Code path | Port |
|---|---|---|---|---|
| SPARK | The Spark (MCP tool registry) | Norman Hawkins | `src/mcp/` | mounted on tranc3-backend :8000 |
| GRID | The Digital Grid (workflow engine) | Tyler Towncroft | `src/workflow/`, `workers/workflow-engine-service/` | 8034 |
| INF | Infinity (OAuth2/SSO) | The Guardian (Anchor: Orb of Orisis) | `workers/infinity-auth/` | 8005 |
| VOID | The Void (secrets vault) | Prometheus | `workers/vault-service/` | 8038 |
| WORKSHOP | The Workshop (Forgejo CI/CD) | Larry Lowhammer | `deploy/forgejo/` | 3456 |
| OBS | The Observatory (audit/monitoring) | Norman Hawkins | `src/observability/`, `workers/observatory/` | 8065 |

Infrastructure follows the **zero-cost self-hosted architecture** (`CLAUDE.md` §Architecture):
Docker Compose + Traefik + SQLite + local/IPFS storage — no AWS ARNs, no S3, no RDS. The
production Docker host is modelled as server `SRV-CITADEL-01`, matching **The Citadel**
(Trancendos's DevOps fortress entity). Security scan rows use the tools already wired into
this repo's pre-commit hooks and `.forgejo/workflows/security-scan.yml`: bandit, pip-audit,
safety, semgrep, gitleaks, and Trivy for container images.

## Companion documents

Three docs alongside the CSVs turn the CMDB from a static inventory into something
operationally usable:

| Doc | Covers |
|---|---|
| `runbooks.md` | Health-check, restart, scaling, rollback, and selected recovery procedures for the anchor services — written for this platform's actual Docker Compose + Traefik + Forgejo stack, not Kubernetes/AWS. Defers to `deploy/forgejo/RUNBOOK.md` for The Workshop, which already has a dedicated, more detailed runbook. |
| `api-spec-template.md` | Reusable OpenAPI 3.1 skeleton plus a worked example (`API-SPARK-001`) kept in sync with `05_apis.csv`, and the API versioning strategy. |
| `compliance-and-pipeline.md` | ITIL/SOC2/GDPR/HIPAA/ISO 27001 control mapping onto this workbook's columns, and the deployment pipeline as it actually runs through `.forgejo/workflows/` and `docker compose`, including rollback and approval procedure. |

## Files

| # | File | Purpose |
|---|---|---|
| 01 | `01_business_services.csv` | Business capability → owner, SLA, criticality |
| 02 | `02_service_inventory.csv` | Technical services: health checks, RPO/RTO, scaling |
| 03 | `03_application_catalogue.csv` | Deployable applications, runtimes, images |
| 05 | `05_apis.csv` | API endpoints: auth, rate limits, versioning, deprecation |
| 06 | `06_service_deployments.csv` | Deployment history: commit, pipeline run, rollback |
| 07 | `07_environments.csv` | Environment tiers: DR, backup, network zone, compliance |
| 08 | `08_hosting_models.csv` | Hosting abstraction lookup (Cloud/Hybrid/Self-hosted) |
| 09 | `09_servers.csv` | Physical/VM/container-host inventory |
| 10 | `10_databases.csv` | Database instances, replication, encryption |
| 11 | `11_storage.csv` | Block/object/file storage assets |
| 12 | `12_dns.csv` / `12b_dns_records.csv` | DNS zones, and their resource records (split into two files — one row-shape each — rather than the two sub-tables the source spec embeds in one block) |
| 13 | `13_load_balancers.csv` | Reverse proxy / LB configuration (Traefik) |
| 14 | `14_firewalls.csv` | Firewall rule inventory |
| 15 | `15_dependencies.csv` | Service/app/infra dependency graph incl. circuit breakers |
| 16 | `16_vulnerability_scans.csv` | Vulnerability findings, CVE/CVSS, remediation status |
| 17 | `17_configuration_baseline.csv` | Config drift vs. hardening baseline |

File 04 (a duplicate reference copy of File 01 in the source spec) is omitted here as
redundant.

## Lookup tables (shared codes)

**Status (STS-XXX):** 001 Planned · 002 Building · 003 Deploying · 004 Active · 005 Live · 006 Failed · 007 Retired
**Criticality (CRT-XXX):** 001 Critical · 002 High · 003 Medium · 004 Low
**Data Classification (DC-XXX):** 001 Public · 002 Internal · 003 Confidential · 004 Restricted
**Environment Tier (TIER-XXX):** 001 Local · 002 Development · 003 UAT · 004 Staging · 005 Production · 006 Disaster Recovery
**Hosting Model (HST-XXX):** 001 Cloud Only · 002 Hybrid · 003 Self Hosted *(primary model for this platform)*
**Remediation Status (REM-XXX):** 001 Open · 002 InProgress · 003 AwaitingValidation · 004 Fixed · 005 Accepted · 006 FalsePositive · 007 Deferred
**Vulnerability Severity (VSEV-XXX):** 001 Critical · 002 High · 003 Medium · 004 Low · 005 Info
**Drift Level (DRFT-XXX):** 001 None · 002 Minor · 003 Moderate · 004 Major · 005 Critical
**Dependency Strength (DEPSTR-XXX):** 001 Hard (Required) · 002 Soft (Optional) · 003 Conditional

Each CSV here uses a **core column subset** of the originating 17-file workbook spec —
the identifying, ownership, SLA, health-check, dependency, and status columns that
matter for day-one use. Free-text JSON-blob columns from the source spec (e.g. deployment
`HealthCheckDetails`, `PerformanceBaseline`, `SecurityScanDetails` as embedded JSON strings)
were dropped from this seed to keep the CSVs trivially parseable without quoting; add them
back with proper CSV quoting if/when this becomes a live, tool-populated CMDB rather than a
hand-seeded reference. Data types and validation rules for every column follow the
originating spec's conventions (Code/Text/Integer/Boolean/List with `;`-separated multi-values,
`STS-`/`CRT-`/`DC-` style lookup codes, etc.).

## Validation rules that apply across files

- Every `Owner` column must be a valid Tier 3 Lead AI name from `PLATFORM_ENTITIES.md`.
- `RPO` (Recovery Point Objective, max acceptable data loss) and `RTO` (Recovery Time Objective, max acceptable downtime) are independent targets set per service criticality — neither is required to be greater than the other. Both should tighten with higher service criticality — note `CriticalityCode` is inverted (CRT-001 is the *highest* criticality), so CRT-001 services should carry the **lowest** RPO/RTO minutes.
- `SLA` must be **>= 99.0%** for any row with `CriticalityCode = CRT-001` (Critical).
- Cross-references (`DependsOnServices`, `ServiceID`, `ApplicationID`, etc.) must resolve to a row in the referenced file.
- `HostingModel` should be `HST-003` (Self Hosted) unless a service has an explicit, documented reason to run elsewhere (e.g. Fly.io during the Cloudflare Workers → self-hosted migration).

## Next steps to make this a live CMDB rather than a static seed

1. Extend the six anchor services to the remaining ~85 workers in the `docker-compose.production.yml` port table.
2. Either keep this as versioned CSV under `docs/architecture/`, or load it into a queryable store (e.g. a `cmdb` schema in Postgres/SQLite under `src/database/`) with the same columns as tables.
3. Wire `16_vulnerability_scans.csv` and `17_configuration_baseline.csv` to be generated automatically from `.forgejo/workflows/security-scan.yml` / `dependency-audit.yml` output rather than hand-maintained.
