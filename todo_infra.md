# Tranc3 Infrastructure Build — Task Tracker

## 1. Fix Rust Compilation Errors [COMPLETE ✓]
- [x] Fix main.rs: hyper 1.x Body type (`Full<Bytes>` instead of `Bytes`), `hyper::body::to_bytes` → `BodyExt::collect`
- [x] Fix hsm.rs: PkcsPssParams struct literal, `info.label()` returns `&str`, Slot by value not deref, AuthPin takes String, `Ulong::from(x as u64)`, Pkcs11Error 2-field, derive_kek_context return type
- [x] Fix storage.rs: `sha256_hex` type, moved `placement.rule_name`, unused `host`
- [x] Fix adaptive.rs: unused vars/imports
- [x] Fix crush.rs: unused imports
- [x] `cargo check` → 0 errors, 45 warnings (dead_code only — expected)

## 2. Recreate Missing Python Files [COMPLETE ✓]
- [x] oci_adaptive_provider.py (1,173 lines) — OCI adaptive storage with circuit-breakers, quota tracking, keepalive
- [x] microceph_provider.py (1,586 lines) — MicroCeph single-node with CRUSH, OSD, RGW, pool manager

## 3. Phase 16 Documentation [COMPLETE ✓]
- [x] docs/matrix.md — Phase 16 section with component table, CRUSH topology, entity taxonomy, quota limits
- [x] src/config/id_registry.json — v2.1.0 with SID/NID/PID/AID infra registries + CRUSH map config

## 4. Terraform Validation [COMPLETE ✓]
- [x] `terraform validate` → SUCCESS (0 errors)
- [x] Fixed: missing gateway variables, oci_vault→oci_kms_vault, lifecycle compartment_id, vault secret key_id, shell var escaping in cloud-init templates

## 5. GitHub Push & PR [COMPLETE ✓]
- [x] Branch: `infra/phase16-adaptive-storage`
- [x] Commit: feat(infra/phase16) with full description
- [x] PR #55 opened: https://github.com/Trancendos/Tranc3/pull/55
