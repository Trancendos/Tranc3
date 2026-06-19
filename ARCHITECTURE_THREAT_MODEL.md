# Tranc3 Architecture Threat Model

**Version:** 1.0  
**Date:** 2025-01  
**Author:** Trancendos Security Engineering  
**Classification:** Internal — Engineering Use  
**Review Cycle:** Quarterly

---

## 1. Executive Summary

This document provides a comprehensive threat model for the Tranc3 self-hosted platform architecture. The platform replaces all third-party paid services (Cloudflare Workers, D1, KV, R2) with zero-cost, self-hosted Python/FastAPI workers backed by SQLite, in-memory state, and local filesystem. The threat model follows STRIDE methodology and identifies risks specific to the self-hosted, zero-cost architecture along with mitigations already in place and those still required.

The primary threat surface shift from Cloudflare-managed infrastructure to self-hosted infrastructure introduces new categories of risk — particularly around network exposure, secret management, and operational responsibility — while eliminating entire classes of Cloudflare-specific supply-chain and vendor-lock-in risks.

---

## 2. Architecture Overview

### 2.1 Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                    PUBLIC INTERNET                       │
│                   (Untrusted Zone)                       │
└─────────────────────┬───────────────────────────────────┘
                      │
              ┌───────▼───────┐
              │    Traefik     │  ← TLS termination, rate limiting
              │  (Reverse Proxy)│  ← WAF rules, IP allowlisting
              └───────┬───────┘
                      │
      ┌───────────────┼───────────────┐
      │      INTERNAL DOCKER NETWORK  │
      │       (Semi-Trusted Zone)     │
      │                               │
      │  ┌──────┐ ┌──────┐ ┌──────┐  │
      │  │P0:WS │ │P0:Auth│ │P1:AI │  │
      │  │:8004 │ │:8005 │ │:8009 │  │
      │  └──────┘ └──────┘ └──────┘  │
      │  ┌──────┐ ┌──────┐ ┌──────┐  │
      │  │P1:Mon│ │P1:Not│ │P1:Usr│  │
      │  │:8007 │ │:8008 │ │:8006 │  │
      │  └──────┘ └──────┘ └──────┘  │
      │  ┌──────┐ ┌──────┐          │
      │  │P2:Grid│ │P2:Pay│  ...    │
      │  │:8010 │ │:8013 │          │
      │  └──────┘ └──────┘          │
      └───────────────────────────────┘
                      │
      ┌───────────────┼───────────────┐
      │       PERSISTENCE LAYER       │
      │       (Trusted Zone)          │
      │                               │
      │  SQLite files  │  Vault       │
      │  Local FS      │  Prometheus  │
      │  IPFS blocks   │  Loki logs   │
      └───────────────────────────────┘
```

### 2.2 Named Services & Ports

| Name | Service | Port | Priority | Trust Level |
|------|---------|------|----------|-------------|
| The Nexus | infinity-ws | 8004 | P0 | Authenticated |
| Infinity | infinity-auth | 8005 | P0 | Privileged |
| — | users-service | 8006 | P1 | Authenticated |
| The Observatory | monitoring | 8007 | P1 | Admin-only |
| — | notifications | 8008 | P1 | Internal |
| — | infinity-ai | 8009 | P1 | Authenticated |
| The Digital Grid | the-grid | 8010 | P2 | Internal |
| — | products-service | 8011 | P2 | Authenticated |
| — | orders-service | 8012 | P2 | Authenticated |
| — | payments-service | 8013 | P2 | Privileged |
| — | files-service | 8014 | P2 | Authenticated |
| — | identity-service | 8015 | P2 | Privileged |
| The Void | infinity-void | — | Infra | Privileged |
| The Workshop | Forgejo CI/CD | — | Infra | Admin-only |
| The Spark | MCP Server | — | Infra | Internal |

### 2.3 Key Architecture Decisions

1. **SQLite over Cloudflare D1** — Each worker owns its own database file; no shared state between workers except through API calls
2. **In-memory rate limiting over Cloudflare KV** — Token-bucket algorithm per-worker; state lost on restart (acceptable trade-off for zero-cost)
3. **Local filesystem over Cloudflare R2** — Files stored on Docker volumes; IPFS for distributed/cached content
4. **Self-hosted Python/FastAPI over Cloudflare Workers** — Full process isolation, no cold starts, no vendor API limits
5. **Forgejo over GitHub Actions** — Complete CI/CD sovereignty, no third-party pipeline execution

---

## 3. STRIDE Analysis

### 3.1 Spoofing

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| S1 | Attacker spoofs JWT token to access authenticated endpoints | High | Medium | HMAC-SHA256 signing with Vault-stored secrets; token expiry (15min access, 7d refresh); token rotation on refresh |
| S2 | WebSocket connection spoofed with stolen token | High | Medium | JWT verification on upgrade handshake; connection-level user binding; max 1000 concurrent connections enforced |
| S3 | Inter-service API call spoofing within Docker network | Medium | Low | Docker network isolation; Traefik internal routing; service mesh circuit breaker with identity verification |
| S4 | Forgejo webhook spoofing from external source | Medium | Low | Webhook secret verification; IP allowlisting for Forgejo; HMAC signature validation |
| S5 | DNS spoofing redirects traffic away from Traefik | High | Low | DNSSEC where available; hardcoded upstream addresses; certificate pinning for inter-service calls |

### 3.2 Tampering

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| T1 | SQLite database file tampered with on disk | High | Low | Filesystem permissions (0600); Docker volume isolation; hash verification on startup |
| T2 | Worker code tampered via supply chain attack in dependencies | High | Medium | pip-audit + Safety in CI; pip hash verification; .pre-commit-config.yaml with bandit/semgrep; Forgejo dependency-audit workflow weekly |
| T3 | Configuration tampering via environment variable injection | Medium | Low | Vault for secrets (not env vars for sensitive data); .env.production.template documents all variables; Docker secrets for production |
| T4 | Log tampering to cover attack traces | Medium | Low | Loki append-only log storage; Promtail ships logs immediately; log integrity checksums in structured output |
| T5 | Docker image tampering in registry | High | Low | Image digest pinning; multi-stage builds with minimal base; security-scan.yml scans images in CI |
| T6 | AI prompt injection leading to data exfiltration | High | Medium | Input sanitization in AI gateway; token budgets per tenant; offline fallback with no data access; response filtering |

### 3.3 Repudiation

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| R1 | User denies performing authenticated action | High | Medium | Audit log for all auth events (login, token refresh, MFA); request ID tracing with W3C TraceContext; structured logging with user_id binding |
| R2 | Admin denies performing privileged operation | High | Low | Separate admin audit trail; Vault audit logs; Forgejo CI/CD audit trail with commit signing |
| R3 | Inter-service call origin cannot be determined | Medium | Medium | Distributed tracing with trace_id propagation; X-Request-Id headers; service mesh logs caller identity |
| R4 | AI response attribution lost | Low | Low | AI gateway logs provider, model, tokens; request_id binding; offline responses flagged as synthetic |

### 3.4 Information Disclosure

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| I1 | SQLite database file read by unauthorized process | High | Low | Docker container isolation; filesystem permissions; no host mount of DB files except through volumes |
| I2 | JWT secret key exposure | Critical | Low | Vault storage with sealed/unseal ceremony; never in environment variables; rotated on compromise |
| I3 | API response leaks sensitive user data | High | Medium | Pydantic response models filter fields; no ORM-style "select *" patterns; explicit field whitelisting |
| I4 | Log output contains secrets or PII | High | Medium | Structured logging with secret redaction; no raw exception dumps in production; Loki access controls |
| I5 | AI prompt contains sensitive data sent to external provider | Critical | Medium | Token budget enforcement; provider selection policy (Ollama first = local); audit log of all AI requests; HuggingFace/OpenRouter only with explicit consent |
| I6 | Traefik TLS misconfiguration exposes traffic | High | Low | Auto-TLS via Let's Encrypt; HSTS headers; cipher suite hardening; security-scan.yml verifies config |
| I7 | Vault unseal keys exposed | Critical | Low | Shamir secret sharing (minimum 3 of 5 keys); keys stored offline; initialization ceremony documented |

### 3.5 Denial of Service

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| D1 | Connection flood on WebSocket (The Nexus) | High | High | max_connections=1000; per-IP connection limits in Traefik; circuit breaker on connection rate |
| D2 | API request flood on any worker | High | Medium | Token-bucket rate limiting per IP/route; Traefik rate-limit middleware; circuit breaker opens under load |
| D3 | SQLite write contention under high load | Medium | Medium | WAL mode for concurrent reads; write serialization per-worker; health check monitoring for latency spikes |
| D4 | AI provider rate limit exhaustion | Medium | Medium | Token budgets per tenant; priority-based failover; offline fallback always available; circuit breaker on provider errors |
| D5 | Docker disk exhaustion from logs/DBs | Medium | Low | Log rotation in Loki; SQLite vacuum schedule; Docker volume size limits; monitoring disk usage alerts |
| D6 | Memory exhaustion from in-memory rate limiting | Low | Low | Bounded data structures; LRU eviction; max_connections caps; container memory limits in docker-compose |

### 3.6 Elevation of Privilege

| ID | Threat | Impact | Likelihood | Mitigation |
|----|--------|--------|------------|------------|
| E1 | SQL injection in worker endpoints | Critical | Low | Parameterized queries throughout; Pydantic input validation; no raw SQL string interpolation |
| E2 | Container escape via misconfigured Docker | Critical | Low | Non-root containers; minimal base images; no privileged mode; Docker capability restrictions |
| E3 | Vault token theft granting access to all secrets | Critical | Low | Short-lived tokens; token TTL enforcement; policy-based access (least privilege); audit logging |
| E4 | Forgejo CI runner compromise | High | Low | Isolated runner containers; no host Docker socket mount; workflow permission restrictions |
| E5 | Zero-trust bypass via forged device posture headers | High | Medium | Device posture validation against known fingerprints; MFA requirement for sensitive routes; risk scoring with floor values |
| E6 | Payments-service privilege escalation | Critical | Low | Isolated network segment; no outbound internet; audit all mutations; separate database from other services |

---

## 4. Architecture-Specific Risk Analysis

### 4.1 Self-Hosted Risk Shift

Moving from Cloudflare-managed infrastructure to self-hosted introduces these fundamental risk shifts:

**Risks Eliminated:**
- Cloudflare outage affecting all services simultaneously
- Cloudflare API changes breaking deployments without notice
- Vendor data access (Cloudflare can read D1 data, KV values, R2 objects)
- Pricing model changes making the architecture unaffordable
- Cloudflare account compromise affecting all services
- Supply chain risk from Cloudflare Workers runtime
- Geographic data sovereignty uncertainty (Cloudflare edge locations)

**Risks Introduced:**
- Full operational responsibility for uptime, patching, and scaling
- No automatic DDoS protection (Cloudflare's network-level filtering is gone)
- Manual TLS certificate management (partially mitigated by Traefik + Let's Encrypt)
- No automatic geographic distribution (single-origin unless IPFS is used)
- Backup/disaster recovery is now our responsibility
- Physical server access security becomes relevant

### 4.2 Zero-Cost Constraint Risks

The zero-cost mandate introduces specific trade-offs:

| Trade-off | Risk | Acceptance Criteria |
|-----------|------|---------------------|
| In-memory rate limiting | State lost on restart → brief uncontrolled window | Acceptable: window is seconds; Traefik provides backup rate limiting |
| SQLite over PostgreSQL | No built-in replication; write serialization | Acceptable: per-worker DBs keep write volume low; WAL mode handles read concurrency |
| Local filesystem over S3/R2 | No geographic redundancy; manual backup needed | Acceptable: IPFS provides content-addressed distribution for critical assets; backup scripts for SQLite |
| No paid monitoring (Datadog, etc.) | Less sophisticated alerting; manual dashboard setup | Acceptable: Prometheus + Grafana + Loki provide equivalent functionality at zero cost |
| No CDN (Cloudflare) | Higher latency for distant users | Acceptable: IPFS gateway provides cached content delivery; Traefik handles compression/caching |
| No managed secrets (AWS SM, etc.) | Vault operational overhead | Acceptable: Vault is industry-standard; Shamir unseal provides strong security |

### 4.3 SQLite Security Considerations

Each worker owns its own SQLite database. This micro-database-per-service pattern has security implications:

1. **No cross-service SQL injection** — A compromised products-service cannot read users-service data via SQL because there is no shared database connection
2. **Backup complexity** — Each worker's DB must be backed up independently; a missed backup means data loss for that service only
3. **No foreign key integrity across services** — A user_id reference in orders-service is not enforced by the database; application-level validation required
4. **File permission model** — SQLite security depends on OS filesystem permissions; Docker volumes provide isolation
5. **WAL mode** — Write-Ahead Logging enables concurrent reads but requires careful checkpoint management

---

## 5. Threat Scenarios

### 5.1 External Attacker — API Compromise

**Scenario:** Attacker discovers and exploits a vulnerability in an API endpoint.

**Attack Path:**
1. Attacker identifies running services via port scanning (Traefik only exposes 80/443)
2. Attacker attempts API endpoints: authentication bypass, injection, parameter manipulation
3. If auth bypassed, attacker accesses user data or performs actions as that user

**Mitigations in Place:**
- Traefik as sole external entry point (no direct worker access)
- JWT authentication on all non-public endpoints
- Pydantic input validation on all request bodies
- Parameterized SQL queries throughout
- Rate limiting on all endpoints
- Zero-trust middleware evaluating device posture + risk score
- Circuit breaker prevents cascading failures from brute-force attempts

**Residual Risk:** Traefik misconfiguration could expose worker ports directly. Mitigated by Docker network design (workers only listen on internal network).

### 5.2 Insider Threat — Privileged User Misuse

**Scenario:** A developer with production access exfiltrates data or introduces backdoors.

**Attack Path:**
1. Developer uses Vault token to access secrets
2. Developer deploys modified worker code via Forgejo
3. Modified code exfiltrates data to external endpoint

**Mitigations in Place:**
- Forgejo requires code review (branch protection) for production deploys
- Vault audit logs record all secret access
- Worker containers have no outbound internet access (except specific AI providers)
- AI gateway logs all external API calls
- Prometheus alerts on unusual outbound traffic patterns

**Residual Risk:** Developer with Forgejo admin access could bypass review requirements. Mitigated by principle of least privilege and admin access auditing.

### 5.3 Supply Chain — Dependency Compromise

**Scenario:** A popular Python package is compromised and introduces malicious code.

**Attack Path:**
1. Malicious package published to PyPI
2. Workers install package during Docker build
3. Malicious code executes at runtime, exfiltrating data or establishing backdoor

**Mitigations in Place:**
- pip-audit + Safety run in Forgejo CI (dependency-audit.yml)
- Weekly automated scans catch newly disclosed vulnerabilities
- .pre-commit-config.yaml runs bandit + semgrep on every commit
- Minimal dependency policy — workers use only essential packages (fastapi, uvicorn, httpx, pydantic, sqlite3)
- Docker multi-stage builds reduce attack surface

**Residual Risk:** Zero-day vulnerabilities in dependencies may not be caught until disclosure. Mitigated by minimal dependency surface and prompt updating when advisories are published.

### 5.4 Infrastructure — Server Compromise

**Scenario:** The host server is compromised via an unrelated vulnerability.

**Attack Path:**
1. Attacker gains shell access to host
2. Attacker reads Docker volumes containing SQLite databases
3. Attacker modifies worker code or injects environment variables

**Mitigations in Place:**
- Docker containers run as non-root users
- Filesystem permissions on SQLite files (0600)
- Vault stores encryption keys separately from data
- Forgejo stores code separately from running deployments
- Monitoring detects unusual process activity

**Residual Risk:** Host compromise gives attacker significant access. This is the highest-impact residual risk. Mitigated by hardening the host OS, SSH key-only authentication, and regular patching.

---

## 6. Security Controls Matrix

### 6.1 Preventive Controls

| Control | Implementation | Coverage |
|---------|---------------|----------|
| Authentication | JWT + OAuth2 + TOTP MFA | All authenticated endpoints |
| Authorization | Zero-trust middleware with risk scoring | Route-level access control |
| Input validation | Pydantic v2 models on all endpoints | Request bodies, query params, path params |
| SQL injection prevention | Parameterized queries only | All SQLite interactions |
| TLS encryption | Traefik + Let's Encrypt | All external traffic |
| Network isolation | Docker internal network | Inter-service communication |
| Secret management | Vault with Shamir unseal | JWT secrets, API keys, DB credentials |
| Container security | Non-root, minimal images, no privileged mode | All workers |
| Dependency auditing | pip-audit, Safety, npm audit (Forgejo CI) | All dependencies weekly |
| Pre-commit hooks | bandit, semgrep, gitleaks, detect-secrets | Every commit locally |
| Code review | Forgejo branch protection | All production changes |

### 6.2 Detective Controls

| Control | Implementation | Coverage |
|---------|---------------|----------|
| Security scanning | Forgejo security-scan.yml (SAST, secret detection) | Every PR |
| Vulnerability monitoring | dependency-audit.yml (weekly) | All dependencies |
| Health monitoring | Prometheus + Grafana dashboards | All services |
| Log aggregation | Loki + Promtail | All worker logs |
| Distributed tracing | W3C TraceContext propagation | Cross-service requests |
| Audit logging | Structured JSON logs with user_id, trace_id | All authenticated actions |
| Anomaly detection | Alert rules in monitoring worker | Metric thresholds |

### 6.3 Corrective Controls

| Control | Implementation | Coverage |
|---------|---------------|----------|
| Circuit breaker | ServiceMesh with closed/open/half-open states | All inter-service calls |
| Failover | AI gateway priority-based provider switching | AI API availability |
| Rate limiting | Token-bucket per IP/route | All external endpoints |
| Token rotation | JWT refresh token rotation on every refresh | Authentication sessions |
| Backup recovery | SQLite file backup scripts | All worker databases |
| Incident response | Alerting via notifications worker | Critical security events |

---

## 7. Risk Register

| ID | Risk | Severity | Probability | Score | Status | Owner |
|----|------|----------|-------------|-------|--------|-------|
| RR01 | No automatic DDoS protection | High | Medium | 12 | Accepted | Platform |
| RR02 | Single-origin hosting (no geo-distribution) | Medium | Low | 4 | Mitigated (IPFS) | Platform |
| RR03 | SQLite data loss on disk failure | High | Low | 6 | Mitigated (backups) | SRE |
| RR04 | Vault unseal key loss | Critical | Low | 9 | Mitigated (Shamir 3/5) | Security |
| RR05 | Dependency zero-day exploit | High | Medium | 12 | Mitigated (audit + minimal deps) | Security |
| RR06 | AI prompt injection / data leak | High | Medium | 12 | Mitigated (budgets + local-first) | AI Team |
| RR07 | Container escape | Critical | Low | 9 | Mitigated (non-root + hardening) | Platform |
| RR08 | Insider threat with production access | High | Low | 6 | Mitigated (audit logs + review) | Security |
| RR09 | TLS certificate expiry | Medium | Low | 4 | Mitigated (auto-renew via Traefik) | Platform |
| RR10 | Log storage exhaustion | Low | Medium | 4 | Mitigated (rotation + alerts) | SRE |
| RR11 | Forgejo CI compromise | High | Low | 6 | Mitigated (isolated runners) | Security |
| RR12 | Cross-service data inconsistency | Medium | Medium | 8 | Accepted (eventual consistency) | Architecture |
| RR13 | Nanoservice POSIX shm via hostIPC | Medium | Low | 4 | Accepted (documented) | Platform — see `docs/HOSTIPC_RISK_ACCEPTANCE.md` |

---

## 8. Security Architecture Recommendations

### 8.1 Immediate (Before Production Launch)

1. **Deploy Traefik WAF middleware** — Add OWASP Core Rule Set for request filtering
2. **Enable Vault transit encryption** — Encrypt SQLite data at rest using Vault's transit engine
3. **Implement backup automation** — Cron + script to snapshot all SQLite files to encrypted archive
4. **Configure Docker network policies** — Restrict inter-service communication to required paths only
5. **Set up alerting for critical services** — Prometheus alerting rules for P0 services (auth, ws)

### 8.2 Short-Term (First Quarter)

1. **Implement IPFS pinning service** — Critical files pinned across multiple nodes for availability
2. **Add geographic blocking** — Zero-trust middleware country allowlist/denylist configuration
3. **Deploy Honeypot endpoints** — Fake API routes that trigger alerts when accessed
4. **Implement request signing** — HMAC signatures on inter-service API calls
5. **Create incident response runbook** — Step-by-step procedures for each threat scenario

### 8.3 Long-Term (Ongoing)

1. **Penetration testing** — Quarterly external pen test of production infrastructure
2. **Chaos engineering** — Deliberate failure injection to test circuit breakers and failover
3. **Compliance audit** — SOC 2 Type I readiness assessment
4. **Threat intelligence feed** — Subscribe to CVE notifications for all direct dependencies
5. **Architecture review** — Quarterly review of this threat model against evolving threats

---

## 9. Validation & Testing

### 9.1 Automated Security Testing

| Test | Tool | Frequency | Location |
|------|------|-----------|----------|
| SAST | Semgrep | Every PR | .forgejo/workflows/security-scan.yml |
| Secret detection | Gitleaks + detect-secrets | Every commit | .pre-commit-config.yaml |
| Dependency audit | pip-audit + Safety | Weekly + on PR | .forgejo/workflows/dependency-audit.yml |
| Python security lint | Bandit | Every commit | .pre-commit-config.yaml |
| Typo detection | Typos | Every commit | .pre-commit-config.yaml |
| Container scanning | (To be added) | Weekly | Future: .forgejo/workflows/container-scan.yml |

### 9.2 Manual Security Testing

| Test | Frequency | Owner |
|------|-----------|-------|
| Architecture threat model review | Quarterly | Security + Architecture |
| Penetration testing | Semi-annually | External |
| Incident response drill | Semi-annually | SRE + Security |
| Vault unseal ceremony test | Annually | Security |
| Backup restoration test | Monthly | SRE |

---

## 10. Conclusion

The Tranc3 self-hosted architecture represents a deliberate trade-off: exchanging the convenience and built-in security of managed Cloudflare services for full sovereignty, zero cost, and complete control over data and infrastructure. The threat landscape shifts from vendor-dependent risks to operational responsibility risks.

The mitigations documented here — zero-trust authentication, circuit breakers, service mesh isolation, Vault secret management, comprehensive CI/CD security scanning, and distributed observability — provide a robust security posture appropriate for the platform's current stage. As the platform scales, the recommendations in Section 8 should be progressively implemented, with particular urgency on items in Section 8.1 (before production launch).

The zero-cost constraint is not a security weakness — it is a design discipline that forces minimal dependency surfaces, local-first data handling, and explicit trust boundaries. These constraints, paradoxically, produce a more auditable and defensible security posture than architectures that rely on opaque managed services.

---

_This document is maintained in the Tranc3 repository and should be updated whenever the architecture changes materially. All changes require review by at least one team member with security expertise._
