# The Observatory — SQLite audit backup and restore rehearsal

**Scope:** audit-service SQLite database. **Status:** offline backup utility implemented and unit-tested; no production backup, restore or deployment has been performed.

The audit worker uses SQLite WAL. Do **not** copy only `audit.db` while the service is writing: committed events may still reside in the WAL. Use SQLite's online backup API.

## Create a consistent backup

From a machine with access to the live audit volume and Python 3:

```bash
mkdir -p /secure/observatory-backups
python3 scripts/observatory_sqlite_backup.py \
  --db /data/audit.db \
  --output /secure/observatory-backups/audit-20261024.sqlite
```

The output name must be new. The script refuses to overwrite an existing backup or manifest, uses SQLite's online backup API, checks `PRAGMA integrity_check`, and writes a SHA-256 manifest at `<output>.json`. Backups contain potentially sensitive audit data; store them outside publicly exposed directories with least-privilege access, encryption and tested retention. Do not commit backups or secrets to Git.

## Rehearse a restore (never against the live database)

1. Copy the backup and its JSON manifest into an isolated test directory.
2. Compare the backup file's SHA-256 against the manifest; confirm the manifest identifies the intended snapshot and `sqlite_integrity_check` is `ok`.
3. Open the copied database with SQLite and run `PRAGMA integrity_check`.
4. Start the **v2-aware** audit worker with `DATA_DIR` pointed at the isolated test directory and an appropriate test-only internal secret.
5. Call `GET /verify` on the isolated worker; require `valid=true` and a checked count equal to the manifest's `audit_event_count`.
6. Test a new v2 append, re-run verification and confirm legacy v1 rows remain unchanged. Record the result and retain the original backup.

Example verification commands:

```bash
sha256sum /secure/observatory-backups/audit-20261024.sqlite
python3 - <<'PY'
import sqlite3
with sqlite3.connect('/secure/observatory-backups/audit-20261024.sqlite') as db:
    print(db.execute('PRAGMA integrity_check').fetchone()[0])
    print(db.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0])
PY
```

The manifest's SHA-256 detects accidental backup corruption, but is **not** a signed, independently anchored checkpoint and cannot prove that a privileged attacker did not replace both files. Keep a separate trusted backup index and independent audit chain-tip anchors.

## Failure and rollback

- If backup creation or integrity verification fails, do not promote or overwrite anything. Preserve the source database and report the failure.
- If `GET /verify` fails on the isolated restore, quarantine that snapshot and investigate; do not rewrite the chain automatically.
- Older v1-only worker binaries cannot validate new v2 entries. Rollback must use a verified v2-aware binary or a rehearsed recovery plan; never silently discard post-migration events.
- This runbook does not authorize stopping services, restoring a live volume, changing access controls or merging the release.

Tests: `python -m pytest -q tests/test_observatory_sqlite_backup.py`.

Related: [Audit integrity v2](AUDIT-INTEGRITY-V2.md) · [Release hardening research](RELEASE-HARDENING-RESEARCH-2026-10-23.md).
