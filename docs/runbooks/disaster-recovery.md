# Disaster Recovery Runbook — Trancendos Platform

**Classification:** UNCLASSIFIED — INTERNAL  
**Owner:** Trancendos Platform Engineering  
**Version:** 1.0.0  
**Last Reviewed:** 2026-06-06  
**Next Review:** 2026-12-06  
**Compliance:** DEF STAN 00-600 REQ-SU-006

---

## RTO / RPO Targets

| Tier | Workers | RPO | RTO |
|------|---------|-----|-----|
| **CRITICAL** | infinity-auth, vault-service, users-service, payments-service, ledger-service | 15 min | 1 h |
| **HIGH** | audit-service, orders-service, notifications, identity-service, infinity-one-service, infinity-admin-service | 1 h | 4 h |
| **STANDARD** | the-grid, config-service, queue-service, sentinel-station, files-service, products-service, email-service, cron-service, monitoring, infinity-ai, workflow-engine-service, search-service, infinity-portal-service, infinity-shards-service | 6 h | 24 h |
| **LOW** | analytics-service, cache-service, rate-limit-service, cdn-service, geo-service, health-aggregator, topology-service | 24 h | 72 h |

---

## Backup Architecture

Each worker's SQLite database is backed up by the **backup-service** (port 8039) using SQLite's built-in hot-backup API (`sqlite3.Connection.backup()`), which is safe under concurrent writes without requiring a WAL checkpoint.

Backup pipeline per file:
```
sqlite3.backup() → gzip compress → AES-GCM encrypt → write <worker>_<ts>_<tier>.db.gz.enc
                                                    → write <worker>_<ts>_<tier>.meta.json
```

Key derivation: HKDF-SHA256 from `TRANC3_DB_MASTER_KEY` (or PBKDF2 from `SECRET_KEY`).  
Backup root: `BACKUP_ROOT` env var (default: `/data/backups`).

**Retention:**
| Tier | Daily | Weekly | Monthly |
|------|-------|--------|---------|
| CRITICAL | 7 | 4 | 6 |
| HIGH | 7 | 4 | 3 |
| STANDARD | 7 | 4 | 2 |
| LOW | 3 | 2 | 1 |

---

## 1. Monitoring Backup Health

### Via REST API (backup-service)
```bash
# Overall health
curl http://localhost:8039/health

# Per-worker RPO status
curl http://localhost:8039/backup/rpo-status

# List all backups
curl http://localhost:8039/backup/list

# List backups for one worker
curl http://localhost:8039/backup/list?worker=infinity-auth
```

### Via CLI
```bash
python scripts/dr_restore.py rpo-status
python scripts/dr_restore.py list
python scripts/dr_restore.py verify
```

---

## 2. Triggering Manual Backups

```bash
# Single worker
curl -X POST http://localhost:8039/backup/run \
  -H "Content-Type: application/json" \
  -d '{"worker": "infinity-auth"}'

# All workers of a tier
curl -X POST http://localhost:8039/backup/run \
  -d '{"tier": "critical"}'

# Full backup of all workers
curl -X POST http://localhost:8039/backup/run-all
```

---

## 3. Disaster Scenarios

### 3.1 Single Worker Database Corrupted or Lost

**Decision threshold:** File missing, PRAGMA integrity_check fails, or worker fails to start.

**Steps:**
```bash
# 1. Stop the affected worker (prevents further writes to corrupt DB)
docker stop tranc3-<worker-name>

# 2. Verify latest backup is clean
python scripts/dr_restore.py verify --worker <worker-name>

# 3. Dry-run restore (no changes — confirms backup is restorable)
python scripts/dr_restore.py restore --worker <worker-name> --dry-run

# 4. Full restore (atomic: renames live DB to .pre-restore.db first)
python scripts/dr_restore.py restore --worker <worker-name>

# 5. Restart worker
docker start tranc3-<worker-name>

# 6. Verify worker health
curl http://localhost:<port>/health
```

**Expected RTO:** < 15 minutes for CRITICAL tier.

---

### 3.2 Complete Host / Volume Loss

**Decision threshold:** All data volumes lost (disk failure, VM destruction).

**Prerequisites:** Backup root (`/data/backups`) must be on a separate volume or replicated to offsite storage (see §6 Offsite Replication).

**Steps:**
```bash
# 1. Provision new host / restore from snapshot
# 2. Restore backup volume to /data/backups

# 3. Restore ALL critical-tier workers first
python scripts/dr_restore.py restore-tier --tier critical

# 4. Start critical workers and verify health
docker compose -f docker-compose.production.yml up -d \
  infinity-auth users-service vault-service payments-service ledger-service

# 5. Run smoke tests
pytest tests/test_smoke.py -v

# 6. Restore high-tier workers
python scripts/dr_restore.py restore-tier --tier high

# 7. Restore remaining tiers
python scripts/dr_restore.py restore-tier --tier standard
python scripts/dr_restore.py restore-tier --tier low

# 8. Bring up full stack
docker compose -f docker-compose.production.yml up -d

# 9. Run full health check
curl http://localhost:8029/health  # health-aggregator
```

**Expected RTO:** < 1 hour for critical tier; < 4 hours for full stack.

---

### 3.3 Backup Service Failure

**Decision threshold:** backup-service is down or returning errors.

**Steps:**
```bash
# 1. Check logs
docker logs tranc3-backup-service --tail 50

# 2. Restart
docker restart tranc3-backup-service

# 3. If backup root is full, prune old backups
python scripts/dr_restore.py list | head -20

# 4. Trigger manual backup for all critical workers
curl -X POST http://localhost:8039/backup/run -d '{"tier": "critical"}'

# 5. If backup-service cannot start, run manual backup directly
python -c "
from src.backup.engine import BackupEngine
from src.backup.registry import REGISTRY_BY_TIER, BackupTier
eng = BackupEngine()
for w in REGISTRY_BY_TIER[BackupTier.CRITICAL]:
    r = eng.backup(w)
    print(w.worker, r.success, r.error)
"
```

---

### 3.4 Vault / Secrets Compromise (vault-service)

**Decision threshold:** vault-service DB modified by unauthorised party, or `TRANC3_DB_MASTER_KEY` leaked.

**Steps:**
1. Rotate `TRANC3_DB_MASTER_KEY` — generate new key:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update the key in all worker environments (Fly.io secrets / Docker secrets / `.env.production`).
3. Re-encrypt all backup files with the new key:
   ```bash
   # Re-backup all workers (new key takes effect immediately)
   curl -X POST http://localhost:8039/backup/run-all
   ```
4. Restore vault-service from the last known-good backup:
   ```bash
   python scripts/dr_restore.py restore --worker vault-service
   ```
5. Invalidate all active JWT sessions (forces re-authentication):
   ```bash
   # DELETE all sessions in infinity-auth DB
   sqlite3 /data/auth.db "UPDATE sessions SET is_revoked=1"
   docker restart tranc3-infinity-auth
   ```
6. Rotate all platform secrets stored in the vault.
7. File a security incident in audit-service.

---

### 3.5 Auth Service Recovery (infinity-auth)

**Decision threshold:** All sessions lost, JWT secret rotated, or DB corruption.

**Steps:**
```bash
# 1. Restore latest auth backup
python scripts/dr_restore.py restore --worker infinity-auth

# 2. Restart auth service
docker restart tranc3-infinity-auth

# 3. Verify auth health
curl http://localhost:8005/health

# 4. Test login flow
curl -X POST http://localhost:8005/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}'
```

**Note:** Users with active refresh tokens will need to re-authenticate after restore if the backup predates their last login.

---

## 4. DR Drill Procedure

Run quarterly (or after any major infrastructure change):

```bash
# Full drill — verify all backups + dry-run restore all workers (safe, non-destructive)
python scripts/dr_restore.py dr-drill
```

Expected output: All workers show `✓ PASS` for both verify and restore columns.  
**Target:** 100% pass rate. Alert on any failure.

Also verify the REST API:
```bash
curl -X POST http://localhost:8039/backup/verify
```

**Schedule:** Quarterly automated drill via cron-service:
```json
{
  "name": "dr-drill-quarterly",
  "schedule": "0 2 1 */3 *",
  "url": "http://backup-service:8039/backup/verify",
  "method": "POST"
}
```

---

## 5. Recovery Verification Checklist

After any restore, confirm:

- [ ] Worker starts and `/health` returns `"status": "healthy"`
- [ ] `PRAGMA integrity_check` returns `ok`
- [ ] Row counts are non-zero for primary tables
- [ ] Auth: can log in with a known test account
- [ ] Payments: last transaction record timestamp within expected RPO window
- [ ] Vault: can retrieve a known secret key
- [ ] Run `pytest tests/test_smoke.py -v` — all pass

---

## 6. Offsite Replication (Recommended Enhancement)

The backup-service writes to a local filesystem volume. For true DR against host loss, replicate `/data/backups` to:

| Option | Command | Notes |
|--------|---------|-------|
| IPFS (storage-service) | `ipfs add -r /data/backups` | Already in platform — content-addressed |
| rsync to secondary host | `rsync -az /data/backups user@secondary:/data/backups` | Simple, reliable |
| Fly.io volume snapshot | `fly volumes snapshots create vol_xxx` | For Fly.io-hosted workers |

Configure replication via cron-service with a daily job to push to the storage-service IPFS node.

---

## 7. Contact / Escalation

| Role | Contact |
|------|---------|
| Platform Engineering | Trancendos (victicnor@gmail.com) |
| Security incidents | File via audit-service + notify Platform Engineering |

---

## 8. Related Documents

- `docs/runbooks/zero-downtime-deploy.md` — Rolling deployment procedure
- `compliance/register.yaml` — REQ-SU-006 evidence
- `compliance/waivers.yaml` — WAV-002 (RESOLVED)
- `src/backup/registry.py` — Canonical worker database registry with tier classifications
- `workers/backup-service/worker.py` — Backup daemon source
- `scripts/dr_restore.py` — DR restore CLI
