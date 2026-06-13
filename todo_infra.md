# Tranc3 Infrastructure Build — Task Tracker

## 1. Fix Rust Compilation Errors [COMPLETE ✓]
- [x] Fix main.rs: hyper 1.x Body type (`Full<Bytes>` instead of `Bytes`), `hyper::body::to_bytes` → `BodyExt::collect`
- [x] Fix hsm.rs: PkcsPssParams, `info.label()`, Slot by value, AuthPin, Ulong, Pkcs11Error 2-field, derive_kek_context
- [x] Fix storage.rs: `sha256_hex` type, moved `placement.rule_name`, unused `host`
- [x] Fix adaptive.rs: unused vars/imports
- [x] Fix crush.rs: unused imports
- [x] `cargo check` → 0 errors, 45 warnings (dead_code only)

## 2. Recreate Missing Python Files
- [x] oci_adaptive_provider.py (~1,173 lines)
- [x] microceph_provider.py (~1,586 lines)

## 3. Phase 8 Documentation
- [ ] Update docs/matrix.md with PID/AID/SID/NID entities
- [ ] Update src/config/id_registry.json with new entities

## 4. Final Verification & GitHub Push
- [ ] Terraform syntax review (terraform validate)
- [ ] Create feature branch `infra/phase8-adaptive-storage`
- [ ] Stage all new files and commit
- [ ] Push branch + open PR to main
- [ ] Summary of all deliverables
