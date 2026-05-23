# Tranc3 - Phase 9: CodeRabbit Fixes + Zero-Cost Cloud Research

## Phase 9A: CodeRabbit + Additional Review Fixes (IN PROGRESS)
- [x] Fix vault_security.py `__del__` returning `self`
- [x] Fix platform.py: Guardian canonical naming + Unicode dashes + unused abbrev
- [x] Fix apply_repairs.py: tAImra casing + Guardian title preservation
- [x] Fix naming_repairs.py: LEAD_AI_REPAIRS + GUARDIAN_REPAIR
- [x] Fix generate_id_registry.py: tAImra + Guardian + f-string
- [x] Fix generate_docs.py: tAImra + Guardian + Unicode + f-strings
- [x] Fix PLATFORM_ENTITIES.md: Guardian + tAImra naming
- [x] Fix docs/matrix.md: Guardian canonical naming
- [x] Fix prometheus.yml: Add tranc3-redis scrape job
- [x] Fix docker-compose.storage.yml: Healthcheck port 8010->8000
- [x] Fix smart_storage.py: Invalid SystemMode ValueError handling
- [x] Fix zfs_snapshot_manager.sh: set -e short-circuit + capacity_aware_prune
- [x] Fix zfs_replication_manager.sh: compression before target + mc pipe alias
- [x] Fix minio_lifecycle_manager.sh: default credential rejection + cold retention drift
- [x] Fix docs/vault_security.md: Language identifiers for fenced code blocks
- [ ] Fix docs/vault_security.md: Split zero-cost baseline from optional paid hardening
- [ ] Fix docs/RESEARCH_FINDINGS.md: Mark optional/paid items
- [ ] Regenerate id_registry.json + id_registry.csv from fixed scripts
- [ ] Commit and push Phase 9A fixes

## Phase 9B: Zero-Cost Cloud Provider Research & Integration
- [x] Research Oracle Cloud free tier offerings (completed in prior session)
- [ ] Research Google Cloud free tier offerings
- [ ] Research Microsoft Azure free tier offerings
- [ ] Research AWS free tier offerings
- [ ] Research HashiCorp free/open-source offerings
- [ ] Document findings in ZERO_COST_CLOUD_PROVIDERS.md
- [ ] Implement new zero-cost providers in smart_storage.py
- [ ] Update docker-compose.storage.yml with new provider configs
- [ ] Update prometheus alerts for new providers
- [ ] Commit and push Phase 9B
