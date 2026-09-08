# Platform Hardening and Documentation Audit

**Assessment date:** 2026-09-08
**Scope:** production Compose, CI/CD controls, security automation, repository documentation, and the version-controlled GitHub Wiki source.

## Executive Summary

Tranc3 already has meaningful health monitoring, a self-repair bridge, service-registry checks, and CI guardrails. The highest-value work is therefore not another autonomous controller. It is making existing controls safe, observable, and hard to bypass: eliminate unsafe production defaults, catch deploy-time Compose defects before deployment, and require documentation review when documented sources change.

The resulting model is modular and zero-incremental-cost: local Python checks run inside the existing topology job and existing self-hosted tooling. No new hosted service, token, scheduled GitHub workflow, external AI call, or automatic production mutation is introduced.

## Evidence and Findings

| Area | Finding | Risk | Disposition |
|---|---|---|---|
| Compose networking | `woodpecker-server` and `nexus-ws-rs` both claimed host port `8100`. | Deployment failure or unexpected service exposure. | Fixed: both use internal exposure and existing Traefik routes. |
| Deployment generator | Newly required `MINIO_ROOT_USER` and `MATTERMOST_DB_PASSWORD` were not emitted by the production environment generator. | Production Gate failed before Compose rendering. | Fixed: the generator now creates both values and the existing coverage check verifies all 55 required variables. |
| Control plane | Vault, observability, registry, messaging, storage, and proxy administration ports were published on all interfaces. | Administrative-plane attack surface. | Fixed: control-plane bindings use loopback; Traefik keeps public HTTP(S). |
| Secrets | Production credentials used empty or known fallback values. | Secret bypass or accidental insecure deployment. | Fixed: critical values are now required interpolation variables. |
| Image updates | Watchtower held Docker socket access and was configured for frequent rolling updates. | Unreviewed image change and restart risk. | Fixed: maintenance profile only, scheduled monitor-only mode, no restarts. |
| Image provenance | Some images are tag-pinned but not digest-pinned. | Supply-chain drift. | Retained as explicit advisory backlog; migrate service by service after compatibility review. |
| Documentation | The deployment runbook duplicated stale Compose images, port mappings, and a small infrastructure count. | Misleading operational guidance. | Fixed: Compose is declared authoritative and the static table is historical context only. |
| API knowledge | A runtime API reference and a Wiki v2 design specification shared the same title, while the runtime document named an archived entry point. | Readers could deploy or test against obsolete APIs. | Fixed: current implementation sources are named and the Wiki page is explicitly historical. |
| Wiki publication | Repository docs and the live Wiki could diverge if both were edited. | Conflicting guidance. | Controlled: `wiki-content/` remains the reviewed canonical source and the live Wiki is one-way publication. |
| Document lifecycle | The first documentation catalog named owner roles but did not connect repository Markdown to a verified runtime Location or prevent automatic runtime publication. | False accountability claims and unreviewed knowledge publication. | Fixed: lifecycle mapping is explicit; runtime articles are draft-first and require a durable Town Hall approval record before publication. |
| Test isolation | `tests/test_backup_service.py` changed `SECRET_KEY` at collection time and leaked it to later modules. | Order-dependent Pytest failure in the canonical CI gate. | Fixed: backup crypto setup is an autouse fixture that restores the prior environment. |
| API route discovery | The `api` package executed `api.py` in an unregistered module, allowing more than one root application instance to be constructed during a long test process. | A route-mount assertion could inspect an inconsistent instance. | Fixed: the loader now uses a lock and a registered module singleton, failing cleanly if root-app loading fails. |

## Implemented Controls

### Deployment contract audit

`scripts/compose_contract_audit.py` is a static, fail-closed check for deterministic conditions Docker Compose cannot safely infer:

- overlapping host-port bindings;
- public control-plane ports outside the explicit Traefik HTTP(S) exception; and
- insecure secret fallbacks or critical empty secrets.

It reports non-digest-pinned images as advisory findings rather than suppressing them or blocking unrelated work. This provides an auditable migration list without pretending tag drift is fixed. The existing topology CI job runs the check after installing PyYAML; it adds no runner or scheduled workflow.

### Safe self-healing boundary

Existing runtime monitors remain the appropriate place for reversible health actions. The deployment layer now follows a narrower policy:

- automatically observe and diagnose safe conditions;
- restart or update nothing solely because a monitor sees a newer image;
- fail immediately for deterministic contract, secret, and routing defects; and
- require a reviewed deployment for image, schema, identity, network, or data changes.

This separates repairable transient faults from configuration defects. It is self-healing where the system can prove the operation is reversible, not self-masking.

### Living documentation federation

`config/docs/living_documents.yaml` assigns a canonical document, owner, Diataxis kind, and source-change signals to each high-value topic. `scripts/documentation_health.py` then verifies:

- each registered path exists and each canonical document has one owner contract;
- every version-controlled Wiki page is listed in `_Sidebar.md`;
- a changed mapped source is accompanied by review of its canonical document; and
- the generated `docs/DOCUMENTATION_CATALOG.md` remains current.

This is a federated knowledge model, not federated machine learning. Teams retain ownership of domain knowledge; a deterministic local verifier protects shared navigation and source-of-truth boundaries. It deliberately does not auto-generate or auto-publish operational guidance.

`docs/DOCUMENT_LIFECYCLE.md` now distinguishes repository custody from runtime knowledge intake. The Workshop is accountable for source-control custody, The Library for knowledge stewardship, The Town Hall records runtime publication approval, and The Observatory receives post-publication events. Static repository and Wiki documents are not claimed to arrive in DocUtari, The Library, or The Basement because no verified integration currently performs that delivery. The catalog validates those Location names against the platform entity registry rather than accepting arbitrary labels.

The initial forensic scan covered 271 Markdown pages across `docs/` and
`wiki-content/`. It found no exact-content duplicates and no high-containment
duplicate candidates. One duplicate title exposed a real source-of-truth
collision between the runtime API reference and a historical v2 design page;
the labels and implementation boundary are now explicit.

## SWOT

| Strengths | Weaknesses |
|---|---|
| Mature in-repository health, topology, and governance controls; self-hosted execution paths; version-controlled Wiki source. | Large Compose surface, legacy direct worker port exposure, stale historical inventory, and some mutable image tags. |
| Opportunities | Threats |
| Route workers through Traefik in small verified batches; pin images by digest with signed provenance; expand source-to-document contracts gradually. | A broad automatic updater, blanket secret defaults, or automated documentation rewriting would make outages and bad guidance harder to attribute. |

## Prioritised Follow-up

1. **P1: Route direct worker host ports through Traefik in service-family batches.** Add health checks and remove each direct port only after an authenticated route and smoke test exist.
2. **P1: Replace image tags with reviewed digests.** Record the source image, digest, rollback tag, and service owner in the deployment change; do not bulk-pin untested images.
3. **P2: Expand the living-document registry only for stable ownership boundaries.** Start with deployment, CI/CD, and wiki publication; add service contracts as their source-of-truth paths are confirmed.
4. **P2: Use the existing scheduled CI health workflow for periodic audits.** Keep it consolidated and report-only; avoid new schedules until a concrete failure signal justifies them.
5. **P3: Reconcile the external security-alert backlog by evidence.** Inventory alerts with package, reachability, fix version, and owner first; automatically update only low-risk lockfile changes and never bulk-dismiss alerts.

## Research Basis

- [Docker Compose services reference](https://docs.docker.com/reference/compose-file/services/) informs port and service-contract semantics.
- [Docker Compose trust model](https://docs.docker.com/compose/trust-model/) supports keeping image update and deployment decisions reviewable.
- [GitHub dependency caching guidance](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) informs bounded cache use rather than unbounded retry loops.
- [Diataxis documentation framework](https://diataxis.fr/) provides the tutorial, how-to, reference, and explanation taxonomy used by the catalog.
- [GitHub wiki documentation](https://docs.github.com/en/communities/documenting-your-project-with-wikis/about-wikis) supports treating the repository source as the reviewable publication authority.
