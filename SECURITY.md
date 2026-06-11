# Tranc3 Security Policy

## Supported Versions

| Version | Supported | Security Status |
|---------|-----------|-----------------|
| 0.1.x   | ✅ Active | Current development |
| < 0.1   | ❌ End-of-life | Not supported |

## Security Architecture

Tranc3 follows a **security-by-default, zero-trust** model aligned with OWASP standards and the Trancendos Magna Carta Digital Rights Framework.

### Core Security Principles
- **Exact dependency pinning** — all packages pinned to specific versions
- **Non-root containers** — Docker runs as unprivileged `tranc3` user
- **No privilege escalation** — `no-new-privileges:true` in all containers
- **Resource limits** — CPU/memory caps prevent resource exhaustion
- **Read-only filesystems** — container filesystems are read-only where possible
- **Automated scanning** — pip-audit, Safety, Bandit, npm audit, Trivy in CI/CD
- **SBOM generation** — CycloneDX SBOMs generated for every build

## Reporting a Vulnerability

### How to Report
- **GitHub Security Advisories:** [Report a vulnerability](https://github.com/Trancendos/Tranc3/security/advisories/new)
- **Email:** security@trancendos.ai (PGP key available on request)

### What to Include
1. Description of the vulnerability
2. Affected component and version
3. Steps to reproduce
4. Potential impact assessment
5. Suggested fix (if available)

### Response Timeline
| Time | Action |
|------|--------|
| 24 hours | Acknowledge receipt |
| 72 hours | Initial assessment and severity rating |
| 7 days | Remediation plan communicated |
| 30 days | Patch released (critical/high) |
| 90 days | Patch released (medium/low) |

### Severity Classification
| Severity | CVSS Score | Response |
|----------|-----------|----------|
| Critical | 9.0-10.0 | Immediate patch, emergency release |
| High | 7.0-8.9 | Priority patch within 7 days |
| Medium | 4.0-6.9 | Scheduled patch within 30 days |
| Low | 0.1-3.9 | Next release cycle |

## Automated Security Controls

### CI/CD Pipeline
- **CodeQL Analysis** — Static analysis for Python and JavaScript/TypeScript
- **pip-audit** — Python dependency vulnerability scanning
- **npm audit** — Node.js dependency vulnerability scanning
- **Bandit** — Python security linting
- **Safety** — Dependency vulnerability database checking
- **Trivy** — Container and filesystem vulnerability scanning
- **Dependabot** — Automated dependency updates (weekly)
- **Pre-commit hooks** — Local security checks before commit

### Supply Chain Security
- **Exact version pinning** — No `>=` or `~=` in requirements
- **Lock files** — All dependencies locked with hashes where possible
- **SBOM generation** — CycloneDX format for compliance
- **Dependency review** — License and vulnerability checks on PRs

## Vulnerability Remediation Status

### Resolved (2025-07)
See `docs/CVE_REMEDIATION_REPORT.md` for the complete list of 66 resolved CVEs.

### Key Patches Applied
| Package | From | To | CVEs Resolved |
|---------|------|----|---------------|
| torch | >=2.2.0 | 2.12.0 | CVE-2024-48063, CVE-2025-32434, CVE-2025-3730, CVE-2025-2953 |
| langchain | (new) | 1.3.1 | CVE-2024-7042, CVE-2024-7774, CVE-2024-58340, +5 more |
| transformers | (new) | 5.8.1 | CVE-2024-11394, CVE-2024-11393, CVE-2024-11392, +12 more |
| aiohttp | (new) | 3.13.5 | 20 CVEs resolved |
| cryptography | (new) | 48.0.0 | CVE-2026-26007, CVE-2024-12797, +2 more |
| undici | (new) | 7.15.0 | CVE-2026-1525, CVE-2026-22036, +3 more |

### Static Analysis Remediation Utilities (2026-06)

CodeQL/Trivy findings for SSRF, path traversal, log injection, DOM XSS, and container privilege are addressed with shared helpers in `Dimensional/` and `shared_core/`:

| Module | Purpose | Key APIs |
|--------|---------|----------|
| `url_validation.py` | Block SSRF to private/reserved hosts | `validate_url`, `validate_webhook_url`, `validate_workflow_id`, `validate_ip_address` |
| `path_validation.py` | Prevent directory traversal | `validate_path`, `safe_join`, `sanitize_filename` |
| `sanitize.py` | Strip control chars from log fields | `sanitize_for_log`, `sanitize_dict_for_log`, `SafeLogger` |

Workers and Admin OS routes import these modules at trust boundaries (gateway proxy, CDN/storage/ffmpeg paths, notification logging). The Infinity Admin dashboard escapes dynamic HTML via `esc()` in `dashboard/admin-os.js` and `dashboard/app.js`.

### Dependabot Remediation (2026-06)

| Alert | Package | Severity | Action | Status |
|-------|---------|----------|--------|--------|
| #30 | protobuf (Rust) | Moderate | `prometheus` 0.13 → 0.14; lockfile now pins protobuf 3.7.2 (GHSA-2gh3-rmm4-6rq5) | Fixed |
| #31 | go-redis | Low | Removed unused `github.com/redis/go-redis/v9` from `dnf_orchestrator`; fixed invalid `uuid v1.21.0` → v1.6.0 | Fixed |
| #41, #42 | chromadb | Critical | Removed from `requirements-ai.txt` (no upstream patch for GHSA-f4j7-r4q5-qw2c); optional manual install only | Mitigated |
| #45 | torch | Low | PYSEC-2025-194 (`torch.jit.script`); **not used** in codebase; pinned `torch==2.12.0` (latest) | Risk accepted |
| #1 | Supabase service_role JWT | Critical | Hardcoded key removed in `2375429`; script uses env vars only — **rotate key in Supabase** | Fixed (rotate) |

**ChromaDB compensating controls (until a patched release):**
- Not a declared dependency — install manually only when needed for local dev.
- Use embedded `chromadb.PersistentClient` / `chromadb.Client` only (`src/nanoservices/vector_plan_cache/vector_plan_cache.py`).
- Never set `trust_remote_code=true` on Chroma collections.
- Do not expose the Chroma HTTP server to untrusted networks.

**PyTorch JIT (alert #45):** `torch.jit.script` / `torch.jit.trace` are never called; see `SECURITY-ASSESSMENT.md`.

**CI/CD:** All scanning runs through Forgejo (The Workshop) — `.forgejo/workflows/security-scan.yml` and `dependency-audit.yml`. GitHub Actions runs CodeQL and Trivy for the Security tab.

## Compliance Alignment

- **OWASP Top 10 (2021)** — All categories addressed
- **GDPR / UK-GDPR** — Data protection measures in place
- **Magna Carta Digital Rights** — Constitutional compliance
- **CycloneDX SBOM** — Software Bill of Materials for supply chain transparency
