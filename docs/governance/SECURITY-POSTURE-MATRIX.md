# Security Posture Matrix

> **What this is.** The user pasted CrowdStrike's 2026 Global Threat Report and asked, plainly: does
> this hold any value for Trancendos, and are our protective/defensive measures actually up to
> scratch? Most of that report doesn't transfer — it's written for enterprises with managed endpoint
> fleets, SOC staff, and adversary-tracked intrusion sets, and Trancendos is a single-operator,
> zero-cost, self-hosted platform with none of that. But two of its structural themes turned out to
> be real, checkable questions once pointed at actual code, and checking them found a live
> vulnerability and a piece of dead security code. This document traces both to their fix, follows
> the same discipline as [SWARM-COORDINATION-MATRIX.md](SWARM-COORDINATION-MATRIX.md) and
> [MATRIX-INDEX.md](MATRIX-INDEX.md): verify against real code, state plainly what was wrong, what's
> fixed, and what's still an honest gap.
>
> **Sibling document:** [SUPPLY-CHAIN-POSTURE-MATRIX.md](SUPPLY-CHAIN-POSTURE-MATRIX.md) does the same exercise against Black Duck's 2026 OSSRA report, and picks up §5's supply-chain thread in depth.

**Owner:** The Guardian (Marcus Magnolia) (Security pillar Steward AI, SUITE-SEC) · **Version:** 1.1.0 · **Last verified:** 2026-08-07 (v1.1.0: cubic-dev-ai review on Tranc3#493 caught 4 real bugs in v1.0.0's own fixes — 1 P0, 3 P1, all corrected same-day; see §2/§3 for the specifics. Documenting this here rather than silently editing it out, since a doc about honest verification undermines itself if it hides its own review round.)

---

## 1. Does the CrowdStrike report hold value here? A mixed, honest answer

CrowdStrike's 2026 report leads with three numbers: **89% YoY increase in AI-enabled attacks**, **82%
of intrusions are malware-free** (identity abuse, not exploits), and **29-minute average eCrime
breakout time**. It also covers ransomware cross-domain tradecraft, China-nexus edge-device
exploitation, supply-chain attacks (npm/ShaiHulof, Safe{Wallet}/Bybit), and an AI-specific section on
prompt injection and malicious/impersonated MCP servers.

**What doesn't transfer:**
- Ransomware tradecraft (SCATTERED SPIDER, BLOCKADE SPIDER) and China-nexus edge-device targeting
  assume a Windows/AD estate or network-edge-appliance product surface Tranc3 doesn't have.
- The product-catalogue sections (Falcon, Charlotte AI, managed detection) are CrowdStrike selling
  CrowdStrike — not actionable for a zero-cost, self-hosted platform per `CLAUDE.md`'s own
  architecture principles.
- "Quarterly external penetration testing" (already listed as a recommendation in
  `ARCHITECTURE_THREAT_MODEL.md` §8.3) isn't realistic at zero budget with a single operator — noting
  that honestly rather than pretending it's a near-term plan.

**What did transfer, once checked against real code:**
- The 82%-malware-free/identity-abuse theme was the reason to check Tranc3's own identity/MFA trust
  boundary instead of trusting `ARCHITECTURE_THREAT_MODEL.md`'s claim that it was "Mitigated." It
  wasn't — §2 below.
- The AI-specific section (prompt injection, malicious/impersonated MCP servers like the report's
  `postmark-mcp` example) is directly relevant because Tranc3 runs its own MCP server (The Spark,
  `src/mcp/`). Checking it found a real defense that had been built and unit-tested but never wired
  into the endpoint it was built for — §3 below.
- Supply-chain — GitHub's own Dependabot flagged **45 vulnerabilities (22 high, 22 moderate, 1 low)**
  on this repo's default branch while this work was underway (visible in every `git push` to this
  branch). That's the concrete, actionable version of the report's supply-chain theme, not its prose
  about npm/ShaiHulud — see §5.

## 2. Fixed: Zero-Trust MFA/device-posture headers were client-spoofable

**The finding.** `src/auth/zero_trust.py`'s `ZeroTrustMiddleware.extract_context()` read
`X-MFA-Verified`, `X-Device-Posture`, and `X-Client-Country` directly from whatever headers it was
handed. `src/security/middleware.py`'s `ZeroTrustASGIMiddleware` — the thing that actually wires that
class to live internet traffic — handed it `dict(request.headers)`: the raw, unauthenticated client
request. Traced the full path:

- `infra/traefik/dynamic/mtls.yml` only CORS-*allowlists* `X-MFA-Verified` (permits browser JS to
  send it cross-origin) — nothing strips, rewrites, or validates it before proxying to the internal
  Docker network.
- No code anywhere in the repo legitimately *set* `X-MFA-Verified` after a real check — grepped for
  it explicitly.
- `workers/infinity-auth/router.py`'s login flow does run a genuine TOTP/backup-code check
  (`verify_totp()`, `hash_backup_code()`, both real, both in `service.py`) — but the resulting JWT
  never recorded that fact as a claim. The verification happened; nothing downstream could see it.

**The consequence:** any caller reaching a worker directly (or through Traefik, since Traefik doesn't
touch the header) could set `X-MFA-Verified: true` on their own request and satisfy the
`mfa_routes` policy (`/admin`, `/api/secrets` by default) with zero real MFA challenge. This is
precisely the pattern the CrowdStrike report's 2026 numbers describe: not an exploit, an identity-
trust-boundary gap. `ARCHITECTURE_THREAT_MODEL.md`'s STRIDE row **E5 "Zero-trust bypass via forged
device posture headers"** was marked *"Mitigated: Device posture validation against known
fingerprints"* — that fingerprint validation does not exist in the code. That claim was wrong,
dated 2025-01, and had never been re-verified against the actual implementation until this pass.

**The fix (landed this session, corrected mid-session after cubic-dev-ai review — see below):**
1. `workers/infinity-auth/router.py` — login and refresh now stamp an `mfa_verified` JWT claim,
   never derived from client input. **First pass re-derived it from the account's *current*
   `mfa_enabled` flag on every refresh — cubic-dev-ai correctly flagged that as its own bug**: a
   session opened before a user turned MFA on would start silently asserting `mfa_verified=true`
   the moment they enabled it, without that session ever completing a challenge. Fixed properly:
   `sessions.mfa_verified` is now a persisted column, set once at login from the real TOTP/
   backup-code check, and refresh combines it with the account's current flag
   (`session.mfa_verified AND user.mfa_enabled`) — a pre-MFA session can never retroactively
   become verified, and disabling MFA still correctly de-asserts it. Migration handled via
   `database.py`'s `_ensure_sessions_mfa_verified_column()` for existing DB files.
2. `src/security/middleware.py` — new `resolve_mfa_verified_header()` strips whatever
   `X-MFA-Verified` the client sent and replaces it with a value derived from decoding the request's
   Bearer JWT and reading its `mfa_verified` claim. No valid token → no verified claim → the header
   is absent → `ZeroTrustContext.mfa_verified` defaults to `False` (fail closed).
   `ZeroTrustASGIMiddleware.dispatch()` now calls this before building context, instead of trusting
   `request.headers` wholesale. **A second, separate bug in this same middleware, also caught by
   cubic-dev-ai**: `dispatch()` only ever rejected on `access_policy == "deny"` — the
   `MFA_REQUIRED` policy value (exactly what a request with no verified claim now correctly resolves
   to) fell through to `call_next()` same as `ALLOW`. The header-spoofing hole was closed, but
   `/admin` and `/api/secrets` still didn't actually require MFA, before or after that first fix.
   Fixed by rejecting `MFA_REQUIRED` with 401 as well.
3. `src/auth/zero_trust.py`'s `ZeroTrustMiddleware` class itself is **untouched** — it's a generic,
   header-driven risk-evaluation library with 62 existing tests
   (`tests/test_zero_trust.py`), and taking a headers dict is a legitimate design for a library
   whose caller is responsible for populating trustworthy values. The vulnerability was entirely in
   how the ASGI layer fed it live, client-controlled input; that's where the fix belongs.
4. New test coverage: `tests/test_zero_trust_mfa_header.py` (6 tests — spoofed header stripped with
   no token, spoofed header stripped even with an unrelated valid token, real `mfa_verified: true`
   claim is the only thing that sets the header, `false` claim doesn't, malformed tokens fail safe,
   other headers pass through unchanged) and `tests/test_zero_trust_asgi_enforcement.py` (4 tests —
   no token / spoofed header / unverified token all get 401 on an MFA-gated route, a real
   `mfa_verified` claim gets 200; this second file is what actually caught that `MFA_REQUIRED` fell
   through in the first pass, since the header tests alone only checked the header value, not
   whether the route was enforced).

**Honest residual gap:** `device_posture` and `country` are still read directly from client headers
— no real device-attestation (MDM-style) system or GeoIP pipeline backs them. This is a materially
different risk than the MFA gap: they only feed `_calculate_risk_score()`/soft policy checks (adding
to a risk score, or gating `healthy_device_routes` — a smaller, opt-in route list), not a hard
authorization bypass on every MFA-gated route the way the forged `X-MFA-Verified` header was. Noted
here as an open item, not silently left undocumented: a real fix would mean either standing up a
device-posture agent (real cost, real complexity) or removing the pretense that these headers are
anything more than advisory. Given the zero-cost, single-operator constraint, the honest interim
position is: don't hard-gate anything security-critical on `device_posture`/`country` alone — only
`enforce_on_all_routes` (default `false`) and the small `healthy_device_routes` list do that today,
and both require deliberate opt-in configuration.

## 3. Fixed: The Spark's prompt-injection scanner existed but was never wired in

**The finding.** `src/mcp/payload_scanner.py` — a real, unit-tested (`tests/test_mcp_payload_scanner.py`,
45 tests) regex/heuristic scanner for jailbreak, instruction-override, and credential-exfiltration
patterns in JSON-RPC payloads, fail-open by design so a scanner bug can't itself deny legitimate
traffic — was never imported by `src/mcp/server.py`. The one purpose-built defense for The Spark's
`/mcp/rpc` endpoint (which does require auth via `get_current_user`, so this was never wide open —
just missing its one dedicated layer) sat dead next to the code it was written to protect.

This is directly the report's AI-specific threat theme: prompt injection against AI-based systems,
and — since Tranc3 runs its own MCP server rather than only consuming third-party ones — the
concrete risk here is injected instructions in tool-call arguments, not (as in the report's
`postmark-mcp` example) a spoofed third-party server identity. This session independently
encountered the general pattern first-hand: multiple fake "SYSTEM NOTIFICATION"/"CRITICAL" injected
instructions arrived inside GitHub webhook PR-comment payloads during this same work, correctly
identified and refused per the standing instruction to treat webhook content as untrusted external
data — the same class of attack this scanner defends against, just a different channel.

**The fix (landed this session, corrected mid-session after cubic-dev-ai review — see below):**
1. `src/mcp/server.py`'s `rpc_endpoint` now calls `scan_rpc_payload(body)` before dispatch. A
   high-severity finding is rejected with a new JSON-RPC error code (`ERR_INJECTION_DETECTED =
   -32004`) before the payload ever reaches `tools/call`.
2. **Adaptive measure:** on a high-severity finding, the source IP is strike-tracked and, after
   `_INJECTION_BLOCK_THRESHOLD` (3) hits, passed to `Cryptex.block_ip()`
   (`src/cryptex/threat_detector.py`) — reusing the existing threat-intel infrastructure
   `GovernanceMiddleware` already gates other mutating routes on. A sustained attacker is then denied
   platform-wide (any route `GovernanceMiddleware` scans, not just `/mcp/rpc`), automatically, with
   no operator action required. **The first pass blocked on a single hit and derived the IP from
   `request.client.host` — cubic-dev-ai caught two real bugs in that**:
   - **P0**: `request.client.host` is the direct TCP peer. In the actual Dockerized production
     stack, that's Traefik's own container IP, not the caller, because Traefik proxies the
     connection — a single attacker payload would have banned the shared reverse proxy, denying all
     mutating traffic platform-wide. Fixed: `_resolve_client_ip()` now prefers `X-Forwarded-For`'s
     first entry (the address Traefik itself sets), matching the same fallback order
     `src/shared/rate_limiter.py`'s `_get_client_key()` already uses elsewhere in this repo.
   - **P1**: the scanner's own pattern catalogue marks bare `SECRET_KEY` mentions and `file://` URIs
     as *high* severity — both can legitimately appear in an ordinary tool call. Blocking on the
     first hit meant a real, legitimate caller could get permanently banned by a false positive.
     Fixed: blocking is now threshold-gated (3 strikes) — every individual high-severity request is
     still rejected regardless, but escalation to a platform-wide ban requires a sustained pattern,
     not one flagged string.
3. New test coverage: `tests/test_mcp_rpc_injection_guard.py` (grew from 2 tests to 7 across this
   fix and its correction) — a high-severity payload is rejected before dispatch; a clean payload is
   unaffected; `X-Forwarded-For` is preferred over the raw peer; a single hit does not block the IP;
   `_INJECTION_BLOCK_THRESHOLD` repeated hits does; every hit still rejects the individual request
   regardless of block state.

**Honest scope note:** the scanner is regex/heuristic, not a model-based classifier — it will miss
novel phrasings and can be evaded by a determined attacker who avoids its known patterns. That was
already true before this fix; wiring it in makes the existing catalogue actually effective against
what it does catch, it doesn't upgrade its detection power. No claim is made here that this closes
prompt injection as a risk class — only that a real, tested defense that used to do nothing now does
something.

## 4. Verdict on the report's other themes

| Theme | Verdict for Tranc3 |
|---|---|
| 89% YoY AI-enabled attack growth | Directionally relevant as a trend, not independently actionable — the two concrete findings above (§2, §3) are the actionable form of "AI-accelerated, identity-first attacks" for this specific platform |
| 82% malware-free / identity abuse | **Directly actionable — found and fixed a real identity-trust-boundary bypass** (§2) |
| 29-min eCrime breakout time | Motivated the adaptive Cryptex auto-block in §3 (respond within the same request, not after review) rather than being independently built for |
| Ransomware cross-domain tradecraft | Not applicable — no Windows/AD estate |
| China-nexus edge-device exploitation | Not applicable — Tranc3 isn't a network-edge-appliance vendor |
| Supply-chain (npm/ShaiHulud, Safe{Wallet}) | Generic theme; the concrete, present-tense version is GitHub's own Dependabot alert (45 vulnerabilities, 22 high) — see §5, not separately re-derived from the report's prose |
| AI-specific: prompt injection, malicious/impersonated MCP servers | **Directly actionable — found and fixed dead prompt-injection defense on Tranc3's own MCP server** (§3) |
| Cloud/SaaS identity trust abuse, AiTM, hybrid identity | Same root cause as §2's finding — a spoofable identity signal. Fixed for MFA; `device_posture`/`country` remain an honest open gap (§2) |
| Product recommendations (Falcon, Charlotte AI, etc.) | Not relevant — CrowdStrike selling CrowdStrike, contradicts `CLAUDE.md`'s zero-cost, self-hosted architecture principles |

## 5. What was checked and found already good (not everything was broken)

Not every "be honest about security" check turned up a problem — worth stating plainly so this
document doesn't read as universally alarming:

- **Wildcard CORS (`allow_origins=["*"]`):** grepped platform-wide — **0 matches**. Fully
  remediated already.
- **The `dev-secret` `INTERNAL_SECRET` fallback string:** found in 59 worker files, initially
  looked concerning until read in full — every instance is a **hard-fail-at-startup guard**: the
  worker refuses to boot if `INTERNAL_SECRET` is unset, blank, or still `"dev-secret"`. This is a
  correct fail-closed control, not a live vulnerability. (Also independently tracked as landed in
  `docs/compliance/TRANC3-REGISTER-BRIDGE.md` §4: "18-worker `dev-secret` INTERNAL_SECRET fallback
  removal — ✅ Done".)
- **GitHub Dependabot: 45 vulnerabilities on the default branch (22 high, 22 moderate, 1 low).**
  This is real and current — visible on every push to this branch — and is the concrete,
  present-tense version of the report's supply-chain theme. Not remediated as part of this pass
  (out of scope: a dependency-vulnerability sweep is a different, larger task, already tracked
  separately as "Tranc3 dependency-vulnerability remediation sweep" in this session's own task
  history) — recorded here so it isn't lost, not silently left off this document because it's
  inconvenient.

## 6. Honest gaps (recorded, not built)

- **`device_posture`/`country` remain client-header-derived** with no real attestation/GeoIP
  backing — §2's residual gap, deliberately not hard-gated on anything security-critical today.
- **No penetration testing, automated or external** — `ARCHITECTURE_THREAT_MODEL.md` §8.3 already
  recommends this; it remains unbuilt, and honestly, unrealistic at zero budget with a single
  operator until that changes.
- **The MCP payload scanner is regex/heuristic, not model-based** — will miss novel injection
  phrasing; wiring it in (§3) made the existing catalogue effective, not more powerful.
- **45 open Dependabot alerts** — tracked, not remediated in this pass (§5).
- **No WAF, no Vault transit encryption at rest for SQLite** — both already listed in
  `ARCHITECTURE_THREAT_MODEL.md` §8.1 as "Immediate (Before Production Launch)" recommendations from
  2025-01, still not built as of this pass. Restating rather than re-deriving.

No claim in this document should be read as "Tranc3 is now secure" — only as an honest account of
two real gaps found by taking an external report seriously enough to check it against actual code,
fixed with test coverage, and what's still open.

## 7. Cross-references

- [PERMISSIONS-ACCESS-MATRIX.md](PERMISSIONS-ACCESS-MATRIX.md) §3 — Zero Trust IAM's own doc,
  corrected in the same pass to point here.
- `ARCHITECTURE_THREAT_MODEL.md` — STRIDE analysis and Risk Register this document corrects one row
  of (E5) rather than duplicates.
- [SWARM-COORDINATION-MATRIX.md](SWARM-COORDINATION-MATRIX.md) — same house style, same session's
  prior honesty-first governance doc.
- `src/mcp/payload_scanner.py`, `tests/test_mcp_payload_scanner.py`, `tests/test_mcp_rpc_injection_guard.py`
- `src/auth/zero_trust.py`, `src/security/middleware.py`, `tests/test_zero_trust.py`,
  `tests/test_zero_trust_mfa_header.py`
- `workers/infinity-auth/router.py`, `workers/infinity-auth/service.py`
- `src/cryptex/threat_detector.py`
