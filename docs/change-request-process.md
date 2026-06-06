# Change Request Process

> **Document ID:** CR-PROC-001  
> **DEF STAN ref:** REQ-CM-006 (DEF STAN 00-044 Configuration Management)  
> **Owner:** The Town Hall / The Citadel  
> **Version:** 1.0  
> **Date:** 2026-06-06  

---

## 1. Overview

All changes to the Trancendos platform — code, configuration, infrastructure,
and documentation — follow a formal Change Request (CR) process enforced
through Forgejo (The Workshop) pull requests and CI gates.

This process is aligned with:
- **DEF STAN 00-044** — Configuration Management
- **ITIL Change Management** — Normal, Standard, Emergency change types
- **PRINCE2** — Change authority and impact assessment

---

## 2. Change Categories

| Category | Definition | Approval Required | CI Gate |
|---|---|---|---|
| **Standard** | Pre-approved, low-risk, well-understood (e.g. dependency update) | Auto-approved | Required |
| **Normal** | Planned change requiring review (most feature/bugfix PRs) | 1 reviewer | Required |
| **Significant** | Architectural change, new service, security change | 2 reviewers + compliance check | Required |
| **Emergency** | Production incident hotfix | 1 reviewer (post-deployment review within 24h) | Required |

---

## 3. Change Request Workflow

```
Developer opens PR on Forgejo (The Workshop)
    │
    ▼
Automated CI gates run (compliance-gate, production-gate, security-scan)
    │
    ├── FAIL → Developer fixes issues, re-pushes
    │
    ▼
Code review (1–2 reviewers depending on category)
    │
    ▼
Compliance gate check:
    - Lighthouse a11y ≥ 90 (web changes)
    - DEFSTAN compliance score ≥ 70%
    - All tests pass
    │
    ▼
Merge to main (squash merge preferred)
    │
    ▼
Automatic deployment (deploy-fly.yml or deploy-self-hosted.yml)
    │
    ▼
Post-deploy verification (health checks, compliance check)
```

---

## 4. Change Request Template

When opening a PR for a **Significant** or **Emergency** change, include
this template in the PR description:

```markdown
## Change Request

**CR Category:** Normal | Significant | Emergency
**Change ID:** CR-YYYY-NNN (auto-assigned by Forgejo)
**Requested by:** @username
**Target environment:** Development | Staging | Production

### Description
(What is changing and why)

### Impact Assessment
- Services affected:
- Data affected:
- Rollback plan:
- Estimated downtime: None / <5min / >5min

### Testing Evidence
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] DEFSTAN compliance gate passes
- [ ] Lighthouse a11y score ≥ 90 (if web changes)

### Sign-off
- [ ] Developer self-review
- [ ] Peer review: @reviewer1
- [ ] (Significant only) Second review: @reviewer2
```

---

## 5. Emergency Change Procedure

For production incidents requiring immediate deployment:

1. Create PR with `[EMERGENCY]` prefix in title
2. Obtain approval from any single senior reviewer
3. Deploy immediately
4. Within 24 hours: create formal post-incident review issue
5. Within 72 hours: complete retrospective and update runbooks

Emergency changes bypass the normal review SLA but **never** bypass CI gates.

---

## 6. Configuration Item Register

The configuration item (CI) register is maintained in:
- **Code:** Forgejo repository `trancendos/tranc3` (this repo)
- **Infrastructure:** `docker-compose.production.yml` + Traefik config
- **Secrets:** The Void (`cloudflare/infinity-void/` → migrating to `workers/vault-service/`)
- **Platform entities:** `PLATFORM_ENTITIES.md` + `src/entities/platform.py`
- **Compliance register:** `compliance/register.yaml`

---

## 7. Change Advisory Board (CAB)

The CAB convenes asynchronously via Forgejo for Significant changes.
Members:
- **The Citadel** — DevOps and infrastructure
- **The Workshop** — CI/CD and tooling
- **Cryptex** — Security review (when applicable)
- **The Observatory** — Audit and compliance

CAB approval is recorded as a PR approval from the designated reviewer accounts.
