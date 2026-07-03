# Deployment Documentation Index

Tranc3's deployment docs are split across `docs/`, `deploy/`, and `docs/runbooks/`
by audience and scope — this page is the single entry point that says which one
to read for a given need. It doesn't replace any of them; each stays the
authoritative source for its own scope.

## Which doc do I want?

| I want to... | Read |
|---|---|
| Set up local development (clone, run, first commit) | [`docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — *Quick Start (Local Development)* |
| Understand the zero-cost provider strategy (OCI, Cloudflare free tier) | [`docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — *Oracle Cloud Infrastructure*, *Cloudflare Workers* |
| See the full production service inventory (all workers, ports, images) | [`docs/DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md) — *Service Inventory*, *Port Reference* |
| Deploy/operate the production stack (pre-deploy, verification, backup, shutdown) | [`docs/DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md) |
| Run a single "one command" local stack quickly | [`deploy/LIVE_DEPLOY.md`](../deploy/LIVE_DEPLOY.md) |
| Cut DNS over from Cloudflare Workers to the self-hosted Citadel | [`deploy/DNS_CUTOVER.md`](../deploy/DNS_CUTOVER.md) *(the only DNS cutover doc — see note below)* |
| Deploy on Windows | [`docs/WINDOWS_DEPLOY.md`](WINDOWS_DEPLOY.md) |
| Roll out a zero-downtime deploy for a specific service | [`docs/runbooks/zero-downtime-deploy.md`](runbooks/zero-downtime-deploy.md) |
| Run disaster recovery | [`docs/runbooks/disaster-recovery.md`](runbooks/disaster-recovery.md) |
| Debug the API backend specifically | [`docs/runbooks/api-backend.md`](runbooks/api-backend.md) |
| Provision infra with Terraform | [`deploy/terraform/PROVISIONING.md`](../deploy/terraform/PROVISIONING.md) |
| Restore/rotate the Vault | [`docs/vault_security.md`](vault_security.md), [`deploy/vault/VAULT_RUNBOOK.md`](../deploy/vault/VAULT_RUNBOOK.md) |

## Known overlap (deliberate, not duplication)

`docs/DEPLOYMENT_GUIDE.md` and `docs/DEPLOYMENT_RUNBOOK.md` both have sections
named *Prerequisites* and *Troubleshooting* — this is intentional, not drift:
the Guide's prerequisites are for local dev (Python, Docker, a laptop); the
Runbook's are for operating the production Citadel stack (SSH access, Terraform
state, on-call escalation). Each troubleshooting section is scoped to its own
audience. If you're not sure which applies, start with the table above.

`deploy/runbook.md`'s *Kubernetes Deployment* section is **not a supported
path** — it references manifest files that don't exist in this repo and
describes a paid managed-cluster setup that contradicts the platform's
zero-cost, self-hosted Docker Compose architecture. Left in place with a
warning rather than deleted, since it may reflect a future/optional track.

## Resolved duplication (this pass)

- `deploy/traefik/DNS_CUTOVER.md` was a stale, shorter duplicate of
  `deploy/DNS_CUTOVER.md` (older port scheme, referenced `make deploy-live`
  instead of the current `provision-citadel.sh`/terraform flow). Removed; the
  one wiki reference to it now points at the canonical doc.
- `docs/runbooks/README.md`'s index listed 5 runbooks
  (infinity-auth/infinity-ws/infinity-portal/ai-gateway/database) that were
  never written — broken links — and omitted `disaster-recovery.md`, which
  exists. Corrected.
