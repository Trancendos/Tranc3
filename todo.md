# Tranc3 — Naming Convention Repair, ID Registry & Adaptive Architecture

## Phase 1: Naming Convention Audit & Repair [COMPLETE]
- [x] Audit PLATFORM_ENTITIES.md for all naming inconsistencies
- [x] Audit src/entities/platform.py for matching issues
- [x] Fix tAImra → tAimra casing inconsistency (location vs Lead AI)
- [x] Fix "The Digital Grid" vs "The DigitalGrid" inconsistency
- [x] Standardize bot naming: all Title-Case-Bot format
- [x] Resolve duplicate names across pillars (Wireframe, The Weaver, The Director)
- [x] Decouple AI names from location names (The Nexus AI ≠ The Nexus location)
- [x] Fix Guardian full title consistency (Marcus Magnolia vs Orb of Orisis)
- [x] Ensure consistent capitalization and hyphenation across all entities

## Phase 2: Universal ID Taxonomy Implementation [COMPLETE]
- [x] Design 3-letter abbreviation system for all 43 locations
- [x] Assign PID-XXX IDs for all locations/applications
- [x] Assign AID-XXX-NN IDs for all Tier 3 Lead AIs + Tier 2 Primes + Tier 1 Sovereign
- [x] Assign SID-XXX-NN IDs for all Tier 4 Agents
- [x] Assign NID-XXX-NN IDs for all Tier 5 Bots
- [x] Resolve collisions with contextual suffixes
- [x] Create master ID registry JSON (src/config/id_registry.json)
- [x] Create master ID registry CSV for spreadsheet use

## Phase 3: Repaired Matrix Documentation [COMPLETE]
- [x] Create docs/matrix.md with full repaired pillar-by-pillar tables
- [x] Update PLATFORM_ENTITIES.md with repaired names and IDs
- [x] Add ID fields to src/entities/platform.py dataclass
- [x] Update src/entities/__init__.py exports

## Phase 4: Adaptive Smart ZFS Storage Providers [COMPLETE]
- [x] Implement SmartStorageProvider with environment-aware switching
- [x] Implement ZFS provider (snapshots, replication, compression)
- [x] Implement HybridProvider (local cache + cloud fallback)
- [x] Implement MinIO local S3-compatible provider
- [x] Implement Ceph distributed storage provider
- [x] Add auto-detection logic (NAS → Hybrid → Cloud)
- [x] Add zero-cost capacity monitoring and proactive tiering
- [x] Create ZFS snapshot scripts
- [x] Create ZFS replication scripts with compression
- [x] Create MinIO lifecycle policy scripts
- [x] Update docker-compose.yml with MinIO + monitoring stack

## Phase 5: Vault Security Implementation [COMPLETE]
- [x] Implement VaultSecretLoader with memory zeroization
- [x] Implement PKCS#11 HSM integration module
- [x] Implement append-only audit ledger for vault access
- [x] Research and document YubiHSM 2 integration
- [x] Research and document SoftHSM2 development fallback
- [x] Create vault security documentation

## Phase 6: Cross-Repo Intelligence & Research [COMPLETE]
- [x] Survey Trancendos repos for reusable code and patterns
- [x] Research latest ZFS strategies, HSM tools, and storage tech
- [x] Research frontier vault security implementations
- [x] Document findings in RESEARCH_FINDINGS update

## Phase 7: Git Commit & Push [PENDING]
- [ ] Create feature branch for all changes
- [ ] Commit all changes with descriptive messages
- [ ] Push to GitHub
- [ ] Create Pull Request
