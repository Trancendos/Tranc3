# Compliance Mapping & Deployment Pipeline

Maps ITIL / SOC2 / GDPR / HIPAA / ISO 27001 controls onto this workbook's CMDB columns and
this platform's real code paths, and documents the deployment pipeline as it actually
runs — through Forgejo (`.forgejo/workflows/`), not GitHub Actions, and onto Docker
Compose + Traefik on `SRV-CITADEL-01`, not Kubernetes.

## Compliance framework mapping

### ITIL

| ITIL practice | Tranc3 implementation |
|---|---|
| Service Portfolio Management | `01_business_services.csv` |
| Service Level Management | `SLA` column across `01_business_services.csv` / `02_service_inventory.csv` |
| Availability Management | `RPOMinutes`/`RTOMinutes` in `02_service_inventory.csv`; `DRRPOMinutes`/`DRRTOMinutes` in `07_environments.csv` |
| Change Management | `ApprovedBy`/`ApprovalDate` in `06_service_deployments.csv` |
| Incident Management | `runbooks.md` (this directory) |
| Access Management | `SRV-INF-001` — Infinity, `workers/infinity-auth/` |
| Event Management | `MonitoringEnabled`/`AlertingEnabled` columns, all files |
| Configuration Management (CMDB) | This entire workbook |

### SOC2 (selected Common Criteria)

| Control | Tranc3 implementation |
|---|---|
| CC1.3 — authorities and reporting lines | `Owner` field (Tier 3 Lead AI) in every CSV |
| CC3.2 — risk identification | `16_vulnerability_scans.csv` |
| CC6.2 — access restriction | `SRV-INF-001` (OAuth2/OIDC) |
| CC6.3 — secrets protection | `SRV-VOID-001` (The Void) |
| CC6.4 — network access controls | `14_firewalls.csv` |
| CC6.8 — secrets rotation | `runbooks.md` § The Void → Secret rotation |
| CC7.1 — real-time monitoring | `MonitoringEnabled`, The Observatory |
| CC7.3/7.4 — incident response & recovery | `runbooks.md` |
| CC9.1 — disaster recovery | `RPO`/`RTO` fields in `07_environments.csv` |

This platform's compliance framework is `compliance/magna-carta/` (git submodule, wired
via `src/compliance/magna_carta.py` and `src/compliance/middleware.py` per `CLAUDE.md`) —
that is the enforcement layer; this CSV workbook is the evidence/CMDB layer SOC2 auditors
expect to see behind it.

### GDPR

| Article | Requirement | Tranc3 implementation |
|---|---|---|
| Art. 5 | Data minimization, storage limitation | `DataClassification` + `DataRetentionDays` in `07_environments.csv` |
| Art. 5 | Integrity/confidentiality | `EncryptionAtRest`/`EncryptionInTransit` columns |
| Art. 25 | Data protection by design | `SecurityScanStatus` in `06_service_deployments.csv` |
| Art. 30 | Records of processing | Not covered by this workbook — `16_vulnerability_scans.csv`/`17_configuration_baseline.csv` are security scan findings, not records of processing activities. A real Art. 30 record would need its own register (data categories, purposes, recipients, retention) |
| Art. 32 | Security measures | Encryption columns + `14_firewalls.csv` |
| Art. 33 | Breach notification | Incident response in `runbooks.md` |

Data handling rules already defined in the source CSV workbook (`DHR-001` Live,
`DHR-002` Masked, `DHR-003` Sanitised) apply per `DataClassification`:

| Classification | Handling rule | Environments |
|---|---|---|
| DC-001 Public | No restrictions | All |
| DC-002 Internal | Employee access only | Masked outside ENV-005/ENV-006 |
| DC-003 Confidential | Restricted access | Masked outside ENV-005/ENV-006 |
| DC-004 Restricted | Encrypted + audit logged | Masked outside ENV-005/ENV-006 |

### HIPAA

Applies to Tranquility (`src/tranquility/`) and any service handling wellbeing/biometric
data. Setting `ComplianceFrameworks` to include `HIPAA` and having `EncryptionAtRest`/
`EncryptionInTransit` = `TRUE` on the relevant CSV rows is evidence for the technical
safeguard, but it does not by itself establish the required administrative safeguards
(risk analysis, workforce training, sanction policy) or physical safeguards (facility
access controls) — those need their own documentation outside this CMDB workbook before
a HIPAA claim can be made for real. Note `DB-OBS-001` and `STO-OBS-001` currently have no
real persistence (see `10_databases.csv`, `11_storage.csv`, `runbooks.md` § The Observatory),
so any `HIPAA` framework tag on either row is aspirational until persistence exists.

### ISO 27001

| Domain | Tranc3 implementation |
|---|---|
| A.7 Asset Management | This CMDB workbook |
| A.8 Access Control | `SRV-INF-001` |
| A.9 Cryptography | `Encryption*` columns throughout |
| A.12 Communications | `05_apis.csv` + `api-spec-template.md` |
| A.16 Business continuity | `RPO`/`RTO` in `07_environments.csv` |
| A.17 Compliance | The Observatory (`SRV-OBS-001`) |

---

## Deployment pipeline (as it actually runs)

The upstream reference pipeline this section is adapted from used GitHub Actions,
Kubernetes (`kubectl set image`, blue-green services), and AWS. **None of that applies
here.** This platform's actual pipeline, per `CLAUDE.md`, `.forgejo/workflows/`, and
`docker-compose.production.yml`:

```
Source Code (Forgejo, trancendos.com/the-workshop)
     |
[TRIGGER] push to main (path-filtered, see deploy-fly.yml / deploy-self-hosted.yml)
     v
STAGE 1: VALIDATION
  - ruff + mypy (make lint)
  - pytest (make test / make test-fast)
  - bandit, semgrep, gitleaks, detect-secrets, safety (.pre-commit-config.yaml,
    .forgejo/workflows/security-scan.yml)
     v [success]
STAGE 2: BUILD
  - docker build (Dockerfile per service/worker)
  - trivy image scan
  - push to self-hosted registry (The Artifactory / Zot, port 8047)
     v [success]
STAGE 3: DEPLOY
  - .forgejo/workflows/deploy-fly.yml -> flyctl deploy --remote-only for
    tranc3-backend, tranc3-bots (Fly.io, legacy)
  - .forgejo/workflows/deploy-self-hosted.yml -> triggers on workers/** changes but
    only runs flyctl deploy for trancendos-backend/trancendos-bots, despite the
    workflow's name — it does NOT run `docker compose ... up` for any workers/*
    service. Getting a workers/* change onto SRV-CITADEL-01 is currently a separate,
    unautomated step: someone runs
    `docker compose -f docker-compose.production.yml up -d --build <service>`
    manually on the host (or via a future Ansible/host-level job) — CI does not do
    this today.
     v [success]
STAGE 4: VERIFY
  - the pipeline checks a fixed backend health endpoint, not each service's own
    declared HealthCheckPath from 02_service_inventory.csv per-service
  - watch docker compose logs / flyctl logs for the new deployment
     v [success]
STAGE 5: POST-DEPLOYMENT
  - record a new row in 06_service_deployments.csv (CommitHash, ArtifactVersion,
    PipelineRunID, ApprovedBy)
  - audit log entry via The Observatory
```

Concurrency is only handled for `deploy-fly.yml`, which serializes production deploys
per-branch via its `concurrency:` block. `deploy-self-hosted.yml` has no equivalent
block today, so two pushes to `main` can still race on that path — this is a real gap,
not yet a solved problem across the whole pipeline.

### Rollback

No blue-green/canary infrastructure exists on this platform (single host, Docker
Compose). Rollback is a redeploy of the previous commit/tag:

```bash
git -C /opt/tranc3 checkout <PREVIOUS_COMMIT_SHA>
docker compose -f docker-compose.production.yml up -d --build <service>
```

Record the rollback in `06_service_deployments.csv` via `RollbackDeploymentID` and
`RollbackAuthorized` on the failed deployment's row, and `PreviousDeploymentID` on the
new one — this is exactly what those columns are for.

### Approval

Change Management (ITIL) and CC8.1 (SOC2) both expect a documented approver. Use the
`ApprovedBy` / `ApprovalDate` columns in `06_service_deployments.csv` — populate them
from whichever Tier 3 AI or Tier 2 Prime actually reviewed the change before it reached
`main`, rather than leaving them blank.
