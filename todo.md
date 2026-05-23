# Tranc3 — Naming Convention Repair, ID Registry & Adaptive Architecture

## Phase 1-7: Original Implementation [COMPLETE]
All original phases completed and pushed to PR #46.

## Phase 8: Code Review Fixes (cubic + CodeQL)
- [x] Fix P0: path traversal in smart_storage.py _resolve_path (line 209)
- [x] Fix P0: path traversal in vault_security.py HSM file paths (line 1371)
- [x] Fix P1: ZFS capacity alert condition inversion in prometheus-alerts.yml
- [x] Fix P1: Duplicate AID-DOC-01 in matrix.md, PLATFORM_ENTITIES.md, id_registry.csv
- [x] Fix P1: MinIO default credentials in docker-compose.storage.yml
- [x] Fix P1: pkcs11 NameError in vault_security.py encryption/decryption
- [x] Fix P1: HSM base64 encode/decode mismatch in vault_security.py
- [x] Fix P1: zfs_snapshot_manager.sh — double recursion, /tmp lock file, exit codes
- [x] Fix P1: zfs_replication_manager.sh — unsupported --compress flag, -i/-I mix
- [x] Fix P1: smart_storage.py read() fallback skips providers
- [x] Fix P1: CLOUD_ONLY mode has no usable providers in factory
- [x] Fix P2: YubiHSM 2 price correction in vault_security.md (~$150 → $650)
- [x] Fix P2: Various exit code 0 for errors in shell scripts
- [x] Fix P2: minio_lifecycle_manager.sh — unused capacity thresholds, retention inconsistency
- [x] Fix P2: docker-compose.storage.yml — init script doesn't apply lifecycle
- [x] Fix P2: bandwidth throttling unused in zfs_replication_manager.sh
- [x] Fix P2: tAImra vs tAimra naming in platform.py
- [ ] Commit and push fixes
