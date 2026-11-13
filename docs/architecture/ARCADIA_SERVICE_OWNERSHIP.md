# Arcadia source ownership and delivery boundary

**Status:** Proposed for review, 23 October 2026. Linked to #1445. **Not a deployment certification.**

## Canonical responsibilities

| Area | Existing Tranc3 source | Source default port | Boundary |
| --- | --- | --- | --- |
| Arcadia (PID-ARC) post-login UX | web/ (web/src/AppRouter.tsx) | Nginx 8080 (service doc-pack) | React SPA, no privileged secrets |
| Product catalogue | workers/products-service/worker.py | 8011 | Internal FastAPI/SQLite worker |
| Arcadian Exchange | workers/orders-service/worker.py | 8012 | Separate resource marketplace service |
| Royal Bank of Arcadia | workers/payments-service/worker.py | 8013 | Separate account/transfer service |
| Cross-domain ledger | workers/ledger-service/worker.py | 8032 | Separation blocker tracked in #474 |
| Legacy Arcadia community/marketplace | Trancendos/arcadia (archived private repository) | 3026 per README | Reference implementation only; volatile in-memory state |

**Important correction:** Historical Arcadia Drive generated LOCATION-PROFILE.md says no standalone repo exists; the archived repository does exist. Correct the generator's source before rebuilding; do not manually edit a generated profile. A historical blueprint's 3012 port is not the SPA's serving port.

## Delivery principles

1. Use the Tranc3 React app as Arcadia's UX rather than deploy the legacy API.
2. Internal-secret authentication on workers does **not** establish the identity, object ownership or permissions of an external human user. The browser must call an authenticated gateway; never put worker secrets into a client bundle.
3. Read-only catalogue and community views can launch before commercial transaction flows. Offline entries remain drafts until confirmed by a durable server.
4. Keep Arcadian Exchange and Royal Bank in separate financial and identity boundaries. No real payment, exchange settlement or ledger transfer is authorised by frontend display state.
5. Treat floating-point monetary amounts, missing durable idempotency and the distinct-ledger gap in #474 as unresolved release blockers pending fixed-precision, access-control, concurrency and recovery tests.
6. Do not mark a cloud worker operational from historical documentation alone: establish source commit, deployment ID, current health and operator evidence.
7. Maintain an explicit source-to-service registry; migrate a component only after contract tests prove behaviour and rollback.

## First executable control

Read-only, no-dependency audit:

    python scripts/arcadia_readiness.py
    python -m unittest discover -s tests -p 'test_arcadia_readiness.py' -v

For *opt-in* CI use only, `python scripts/arcadia_readiness.py --strict` exits 2 when there are source findings. Do **not** make this a required CI gate until reported findings are triaged. Regex detections are source-level signals, not penetration testing or complete identity verification.

## Next delivery waves

- **Wave 0:** Source registry, Drive access review and ownership of API/frontend/archived code. Document and test financial hard stops.
- **Wave 1:** Protected Arcadia SPA route with read-only catalogue; verify Infinity login and gateway contract before API exposure.
- **Wave 2:** Durable community data, object-level permissions, events to Observatory, notifications and conflict-safe offline drafts.
- **Wave 3:** Idempotent order-intent lifecycle and audited finance boundaries after #474, fixed-precision migration and recovery tests.
- **Wave 4:** Staging, restore/rollback, accessibility, OWASP security verification and owner sign-off.

## Evidence and limitations

Read on 23 October 2026: Tranc3 workers and web router, docs/services/arcadia/README.md, archived Trancendos/arcadia README and source, Arcadia Drive location profile and repository split decision record. The source scanner does not inspect deployed endpoints, verify end-user IAM, enumerate Cloudflare projects or prove uptime. For relevant baseline controls use the OWASP API Security Top 10 (https://api-security.owasp.org/editions/2023/en/0x11-t10/) and ASVS 5.0 (https://asvs.owasp.org/).
