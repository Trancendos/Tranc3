# VRAR3D P0 — Asset ingestion and truthful job states

**Scope:** Security and reliability changes to the existing workers/vrar3d/main.py service, port 8060. Not a deployment, not a migration of legacy worker.py on port 8068, and not a new orchestration engine.

## Findings addressed

- Untrusted asset_url was fetched without host restrictions, response size bounds or HTTP status validation. TLS validation was disabled by default.
- Offline placeholders were reported as successfully completed conversions.
- POST /vrar3d/scenes had an incorrectly typed and aliased authentication header.
- Clients lacked a protected status endpoint to poll jobs safely.

## New defaults and controls

- Remote URL imports are **disabled by default**; base64 source imports remain supported and bounded.
- Operators must set VRAR3D_REMOTE_INGEST=1 AND VRAR3D_REMOTE_INGEST_HOSTS=assets.example.org before allowing any remote fetch.
- Allowlist entries are **exact names**, not wildcard suffixes. Only HTTPS port 443, no credentials and no IP literals. Preflight DNS rejects non-public answers. Redirects, non-200 statuses, empty and oversized responses are refused.
- VRAR3D_MAX_ASSET_BYTES defaults to 20 MiB. TLS cert checks are enforced, environment proxies are ignored, and VRAR3D_PROBE_TIMEOUT constrains network calls.
- Offline fallback returns status **deferred** and no artifact URL. Deferred does not mean the job is automatically queued or retried: a durable job runner remains to be implemented.
- GET /vrar3d/assets/{job_id} is authenticated, returns job status and optional downloadable same-origin URL, but never the host filesystem path.
- POST /vrar3d/scenes now correctly reads x-internal-secret.

## Security requirements before enabling remote ingestion

**DNS preflight is not DNS pinning.** DNS may rebind between validation and outbound connection. Network/container egress controls MUST block private ranges, metadata, loopback, link-local and internal destinations including IPv6. Only explicitly trusted asset hosts should be allowlisted. Without verified egress rules, keep remote ingest disabled.

Never transmit the INTERNAL_SECRET through browser JavaScript, fragments, query params or local storage. The legacy React dashboard still has a hardcoded dev-secret on the browser side, and points to the older 8068 service rather than the 8060 Docker image. It needs a user-authenticated BFF / gateway which injects the service secret server-side; this PR deliberately does not expose the internal secret to browsers.

## Tests and review gates

Local isolated regression suite:
    python -m pytest -q tests/test_vrar3d_asset_ingest.py

Repository endpoint regression suite:
    python -m pytest -q tests/test_vrar3d_viewer.py

CI must also run full integration tests, type/lint checks, container build and a non-production GLB upload/download smoke test before merge. Do not infer deployment readiness from isolated unit tests.

## Rollback

Revert this pull request. Remote URL ingestion remains disabled by default, so no credentials are needed. Historical done jobs with offline:// placeholders must be audited, not silently presented as real GLBs.

## Next implementation PRs

1. Add user-scoped BFF/auth proxy and remove browser-exposed internal-secret headers.
2. Consolidate legacy worker.py experience/session features into canonical worker with migration tests.
3. Validate GLB/VRM structure, SHA-256 and provenance before registry publication.
4. Implement durable jobs, idempotency, quotas, retries, dead-letter handling, metrics and human override.
5. Package pinned offline WebXR viewer dependencies and test actual headset/device capabilities.
6. Use real backend health evidence and measured telemetry.

Do not delete or merge existing Drive/GitHub assets without an inventory and approval.
