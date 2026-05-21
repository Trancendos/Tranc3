# Tranc3 — Phase 10: CodeQL & Security Remediation

## Phase 10A-10E: Security Fixes [x]
- [x] All phases complete (see git history for details)

## Phase 10F: Validation & Deployment [x]
- [x] All tests pass (961/961), PR #22 created and pushed

## Pre-Deployment Validation [x]
- [x] All local validation complete

---

# PR Review Fixes (from CodeSlick, Sourcery, cubic-dev)

## P1 Fixes — Must Address [ ]
- [ ] SafeHTTPException inherits Exception instead of HTTPException — breaks FastAPI error handling
- [ ] SafeLogger does not sanitize the msg string — log injection vector remains
- [ ] circuit_breaker.py: missed f-string sanitization in CLOSED→OPEN transition
- [ ] esbuild 0.28.0 override outside Vite 7.3.3's expected ^0.27.0 peer range
- [ ] safe_error_detail logs all exceptions as errors — should downgrade 4xx to warning

## P2 Fixes — Should Address [ ]
- [ ] deploy/forgejo/set-org-secrets.sh: --include-service-role flag advertised but not implemented
- [ ] Add end-to-end spawner tests for _resolve_output_base + safe_join with output_dir

## Remaining Infrastructure Items [ ]
- [ ] Merge PR #22 after review
- [ ] Verify deployment on staging environment
- [ ] Deploy to production
