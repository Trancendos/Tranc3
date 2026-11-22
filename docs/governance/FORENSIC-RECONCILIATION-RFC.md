# Forensic reconciliation v0.2 — governance RFC

> **DRAFT / NOT APPROVED FOR DEPLOYMENT OR AUTO-PROMOTION.** This is a documentation and contract proposal. It does not claim a completed Drive forensic audit or verified implementation status.

## Purpose

Reconcile the 43 canonical Trancendos Locations, roles, AI identities, agents, bots, nano-workers, power-ups, job descriptions, templates and historical source material against current code and governance evidence. Prioritise provenance and source authority over freshness of upload timestamps.

## Source authority and ownership

1. Use `PLATFORM_ENTITIES.md` and `src/entities/platform.py` for platform entity identity and naming.
2. Use the live `CLAUDE.md` service table and deployment artefacts to assess implementation and operational status. An entity being listed is not proof of a running service.
3. Treat the five distinct multi-AI Locations (TateKing, Arcadian Exchange, Infinity, The Lab and The Chaos Party) as multi-persona structures, not a shared single entity; verify their separate `agent_teams` in `src/entities/platform.py` before changing IDs.
4. Use `src/roles/registry.py` for operational role assignments and `src/townhall/routing.py` for governed work ownership. Changes must be audited and supersede old routing decisions rather than silently replacing history.
5. Confirm actual source SHA and runtime checks before accepting any inherited assertion.

## Service ownership

| Service | Sole accountable function | Excluded function |
|---|---|---|
| Observatory | Capture provider discovery and evidence provenance | Canonical editorial decisions |
| Library | Curate approved knowledge and citations | Change raw documents |
| DocUtari | Draft, review and version location documentation | Modify runtime CMDB records |
| CMDB | Typed configuration, dependency and entity relationships (subject to ADR) | Claim deployments without evidence |
| Town Hall | Resolve architecture conflicts and authorise promotions | Run arbitrary automated agents |
| Ice Box | Quarantine and inspect unknown content | Declare a binary trusted |
| Cryptex | Verify cryptographic provenance and trust controls | Author code |
| Artifactory | Promote validated artefacts against approved gates | Ignore policy failures |
| Lab | Implement fixes and tooling | Approve its own production changes |
| Chaos Party | Execute reproducible quality/security/fault tests | Issue deployment authority |

## Evidence handling

Each evidence item requires a stable source reference, provider ID or repo commit, path/section, created/modified/uploaded/authored dates **as distinct fields**, checksum algorithm and value **only when observed**, classification, license, and review status.

- Do not treat a filename match as an ownership decision or duplicate-content proof.
- Do not infer authored dates from last-modified or upload timestamps.
- Do not ingest prompts, secrets, personal information, archive binaries or credentials into public CI reports.
- A SHA-256 derived from a provider locator is an **evidence identity**, not the content hash of the file.
- Archive listing without extraction is not a vulnerability scan or malware clearance.
- Source prompts and retrieved documents are untrusted data; never grant them tool authority.

## Acceptance and consent boundary

Classification proposals may be generated without mutation. No source edits, cross-location moves, model downloads, duplicate deletion, publication, repository merge, deployment or permission changes occur without a concrete action preview, exact target/source digest, independent time-limited approval and an action receipt. High-risk changes must be approved individually, never through bulk select-all.

Documentation readiness is not operational readiness. Use stages:
`documented_only` → `source_present` → `build_passed` → `integration_passed` → `security_passed` → `live_verified` → `production_approved`.

## Initial implementation and its limits

A companion standard-library Python prototype (v0.2, delivered as a separate local handoff archive) provides:
- resumable read-only Google Drive folder enumeration and GitHub metadata enumeration;
- conservative candidate-location and entity-category classification;
- review-queue generation with unresolved IDs and provenance gaps;
- static ZIP central-directory checks without execution/extraction;
- fail-closed approval-receipt matching and content-free freshness validation.

Its first isolated fixture run passed **18 targeted tests**. Those tests do not establish security clearance, current repository correctness or complete recursive Google Drive coverage.

### Required follow-on evidence

- Recursively scan the remaining Incoming subfolder estate with pagination and secured checkpoints.
- Inspect source-archive bytes in a restricted environment and calculate actual SHA-256 values.
- Verify 100 accessible repositories' file trees, license status, secrets risk, dependency and code health against commit SHA; archived repositories require a successor map.
- Resolve all canonical ID conflicts through Town Hall and update `src/entities/platform.py` only after review and test evidence.
- Generate location-level documentation diffs using exact source citations, not copied unsupported claims.
- Add fresh end-to-end verification receipts before any production-ready assertion.

**Approval status:** draft only. No canonical document, service or repository has been merged or deployed by this RFC.
