# Observatory audit integrity: v2 transition (PID-OBS)

**Status:** Implemented on a review branch; deployment and full worker integration tests still required.

## Problem and remediation

The historical v1 event hash covers only prev_hash, event_id, timestamp, service,
action, actor, resource and outcome. Changes to persisted severity or details
would not change that hash. The health spot-check also skipped its first/only
sampled row.

Version 2 hashes a canonical, domain-separated JSON envelope including severity
and details, in addition to all v1 fields. New records have hash_version=2.
Older databases gain a NOT NULL hash_version column with default 1 through an
idempotent startup migration; **old events are not rewritten**. Verification
selects the proper version for each record. Unknown versions fail verification.
New inserts write the final hash atomically in the SQLite transaction, starting
with BEGIN IMMEDIATE so parallel worker processes cannot select the same chain
tip under normal SQLite locking.

The health endpoint retains HTTP 200 even for a corrupted chain, but reports
status=degraded and chain_valid=false. External monitoring MUST alert on that
field, not just HTTP status. The full GET /verify checks the entire chain.

## Verification required before production

```bash
pytest -q tests/test_audit_integrity_v2.py tests/test_observatory_audit_service_v2.py
pytest -q tests/test_workers_p3.py -k AuditService
python -m compileall -q workers/audit-service
```

Additionally run the worker container with the sharedcore and observability
named build contexts; test sequential and multi-process writes, restart,
database migration, backups, and cross-service consumers in staging.

## Automated read-only integrity probe

A standard-library CLI under `scripts/observatory_integrity_probe.py` is
provided for scheduled execution by cron, systemd, or a local supervisor.

```bash
python scripts/observatory_integrity_probe.py --url http://127.0.0.1:8025
```

Use the actual verified port/listener, not an assumed mapping: the legacy
Python module documents 8017, while its Dockerfile currently serves 8025.
Exit codes are 0=healthy, 1=integrity failure, 2=unavailable. JSON output
contains no raw event payloads or authentication tokens. A configured
`INTERNAL_SECRET` can be passed through the process environment; remote
connections carrying it must use HTTPS.

Operators can schedule the command after deployment validation. No schedule,
secret, notification channel or live server is configured by this PR. The
probe emits actionable signals but never deletes or repairs forensic records.

## Security and limitations

- **Tamper-evident, not immutable:** a privileged database actor could rewrite
  all events and recompute hashes, or truncate the tail. Sign and anchor
  chain-tip hashes independently outside the database to detect whole-history
  replacement or rollback.
- **Old records remain v1:** existing v1 entries are NOT retroactively protected
  against severity/details modifications.
- The current audit worker exposes sensitive read routes without an explicit
  per-route auth check; determine consumers and enforce authentication before
  exposure outside a private service network.
- **Rollback caution:** old worker builds do not understand hash_version=2 and
  will report new v2 entries as invalid. Do not deploy without a tested forward-
  compatible rollback build and a backup/restore procedure preserving all
  written events.
- Do not log token values or event payloads to public CI/issue threads.
- Never use a hash mismatch as authority to delete or automatically repair audit
  data. Preserve evidence and require operator approval.

## Release gate

1. Verified schema migration on a copy of an existing v1 database.
2. Green targeted tests and existing audit integration suite.
3. Controlled multi-process load test with consistent genesis-to-tip verification.
4. Alerts for degraded health; operator runbook and independent anchor plan.
5. Explicit change approval for production rollout, with rollback evidence.

Source task: https://github.com/Trancendos/Tranc3/issues/1434
