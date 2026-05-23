# Tranc3 - Phase 9: CodeRabbit Fixes + Zero-Cost Cloud Research

## Phase 9A: CodeRabbit + Additional Review Fixes (COMPLETE)
- [x] Fix vault_security.py `__Del__` returning `self`
- [x] Fix platform.py: Guardian canonical naming + Unicode dashes + unused abbrev
- [x] Fix apply_repairs.py: tAImra casing + Guardian title preservation
- [x] Fix naming_repairs.py: LEAD_AI_REPAIRS + GUARDIAN_REPAIR
- [x] Fix generate_id_registry.py: tAImra + Guardian + f-string
- [x] Fix generate_docs.py: tAImra + Guardian + Unicode + f-strings
- [x] Fix PLATFORM_ENTITIES.md: Guardian + tAimra naming
- [x] Fix docs/matrix.md: Guardian canonical naming
- [x] Fix prometheus.yml: Add tranc3-redis scrape job
- [x] Fix docker-compose.storage.yml: Healthcheck port 8010->8000
- [x] Fix smart_storage.py: Invalid SystemMode ValueError handling
- [x] Fix zfs_snapshot_manager.sh: set -e short-circuit + capacity_aware_prune
- [x] Fix zfs_replication_manager.sh: compression before target + mc pipe alias
- [x] Fix minio_lifecycle_manager.sh: default credential rejection + cold retention drift
- [x] Fix docs/vault_security.md: Language identifiers for fenced code blocks
- [x] Fix docs/vault_security.md: Split zero-cost baseline from optional paid hardening
- [x] Fix docs/RESEARCH_FINDINGS.md: Mark optional/paid items
- [x] Regenerate id_registry.json + id_registry.csv from fixed scripts
- [x] Commit and push Phase 9A fixes

## Phase 9B: Zero-Cost Cloud Provider Research & Integration
- [x] Research Oracle Cloud free tier offerings
- [x] Research Google Cloud free tier offerings
- [x] Research Microsoft Azure free tier offerings
- [x] Research AWS free tier offerings
- [x] Research HashiCorp free/open-source offerings
- [x] Document findings in ZERO_COST_CLOUD_PROVIDERS.md
- [x] Implement new zero-cost providers in smart_storage.py
  - [x] Extend StorageTier enum: GCP=5, AZURE=6, AWS=7
  - [x] Implement GCPStorageProvider class (5GB free GCS)
  - [x] Implement AzureCosmosProvider class (25GB free Cosmos DB)
  - [x] Implement AWSDynamoProvider class (25GB free DynamoDB)
  - [x] Update SmartStorageOrchestrator for new providers
  - [x] Update create_smart_storage factory for new providers
  - [x] Update module docstring (priority chain, OCI 20GB fix)
  - [x] Fix all B904 ruff errors (raise from None) + I001 import sorting
- [x] Update docker-compose.storage.yml with new provider configs
- [x] Update prometheus alerts for new providers
- [x] Update .env.example with new provider environment variables
- [ ] Commit and push Phase 9B
