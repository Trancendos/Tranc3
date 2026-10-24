# Observatory release evidence contract (review draft)

This is a **fail-closed review specification**, not a release approval.

## Provenance
- Parent PR: #1438, reviewed base SHA `9b1f0981f3691c0c198d4637670fc8689a066e4c`.
- SBOM child PR: #1452, reviewed SHA `d51e4edf8bfe9aa930cad0e06301d136aaa98c02`.
- Branches have diverged (child eight ahead, nine behind); do not assume a clean merge.
- Source SBOMs do not inventory runtime image or OS packages.

## Required machine-verifiable evidence
For each check capture: `head_sha`, `workflow_run_url`, `job_id`, `conclusion`, `started_at`, `completed_at`, `artifact_sha256`, and `scope`. Reject absent, mismatched, pending, stale or skipped evidence. Never reuse a green check from an earlier commit.

1. Native `python3 scripts/build_container_sboms.py --check` passes at the candidate SHA; record the complete list of stale files, including nexus-ws-rs, rate-limit-service-rs and vault-service-rs if still applicable.
2. Native ACTION-BACKLOG and CI-register generators both pass their check modes without modifying tracked files; retain diffs for review.
3. Affected pytest and pre-commit suites pass at the same SHA.
4. Dependency resolver and Production Gate pass without suppressing advisories; reconcile the 11 previously reported vulnerability findings with immutable finding IDs and explicit disposition.
5. Audit v1/v2 tests demonstrate full-chain verification, first-record tamper detection, concurrent append, restart, corruption isolation, and non-destructive backup/restore.
6. Demonstrate a v2-aware rollback and externally anchored checkpoint verification; do not silently rewrite legacy v1 records.
7. Independently verify live service identity, health, authorization, data integrity and deployed image digest before describing a deployment as healthy.

## Promotion rule
Release remains **BLOCKED** until every required check has independently passed at the exact candidate SHA and a human has approved promotion. Missing evidence is not a pass. This document authorizes no merge, deployment, migration, credential change, or destructive operation.

## Remediation isolation
Keep fixes in separate review branches. Require a full compare/diff and review before incorporating child SBOM changes; never auto-merge.
