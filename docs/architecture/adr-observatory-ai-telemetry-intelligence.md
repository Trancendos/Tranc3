# ADR — AI telemetry intelligence ownership and integration (draft)

**Date:** 2026-10-24
**Status:** Proposed; implementation gated by existing Observatory release work.
**Repository context:** Tranc3 is a disassembly/migration source; it is not the Tranc3 AI model or the Trancendos Universe platform identity.

## Decision
Extend **The Observatory** as the single authoritative sink for AI/agent/MCP execution telemetry, diagnosis and operational evaluation findings. Do not create another observability platform. **Luminous / Mastermind** consumes actionable findings and coordinates responses, without owning tracing persistence. **The Lab** owns experiments, replay and benchmarks; **Turing's Hub** retains model benchmarking ownership. **Dimensionals** owns worker-facing instrumentation and secure transport; **The Artifactory** owns promotion evidence; CMDB owns service relationships; API Marketplace owns external provider connections.

## Existing evidence
- `docs/services/the-observatory/README.md`: Observatory charter covers audit, tracing, metrics, health and verification; existing `src/observability/` implementation.
- `workers/observatory/main.py`: separate FastAPI Observatory worker with OTel and Tempo/Jaeger, Victoria/Prometheus, Loki, Netdata, SigNoz routing.
- `docs/services/luminous/README.md`: Luminous coordinates inference/runtime; existing OpenRouter adapter belongs to inference, not observability.
- `docs/architecture/SHARED-FUNCTIONAL-SERVICES-CORE.md`: worker build boundaries render `src.observability.worker_setup` unreachable in many own-context images. **Fix instrumentation reachability before claiming platform-wide AI telemetry.**
- Existing Observatory release/PR work must be reconciled before touching runtime paths.

## Proposed vendor-neutral v1 event contract
Producer emits a versioned envelope to the existing authorized ingestion boundary:
```json
{
  "schema_version": "trancendos.telemetry.ai.v1",
  "event_id": "uuid",
  "occurred_at": "RFC3339 timestamp",
  "trace_id": "32 lowercase hex chars",
  "span_id": "16 lowercase hex chars",
  "parent_span_id": null,
  "service_id": "CMDB identifier",
  "operation": "model.invoke | agent.step | tool.invoke | workflow.step",
  "provider": "opaque provider id",
  "model": "opaque model id",
  "duration_ms": 0,
  "tokens": {"input": 0, "output": 0},
  "status": "ok | error | cancelled",
  "error_code": null,
  "metadata": {}
}
```
The boundary MUST reject malformed identifiers, unknown schema versions, negative durations/token counts, oversized or high-cardinality fields, and unauthenticated callers; tenant/user identity MUST derive from authenticated context, never from event payload. Raw prompts, completions, bearer tokens, API keys and PII must not be ingested by default.

## Delivery stages
1. **Inventory and non-duplication:** reconcile Observatory worker, `src/observability`, audit-service, monitoring service, OTel helpers, existing draft PRs, and any CMDB entity mapping. Agree on the authoritative ingestion path.
2. **Instrumentation reachability:** package a minimal reusable OTel adapter via Dimensionals, and verify own-context worker Docker builds can actually import it. No silent success status after an instrumenting import fails.
3. **Ingestion MVP:** add bounded, authenticated, redacted and validated AI event ingestion to the canonical Observatory runtime, reusing storage, routing and audit security.
4. **Diagnostics:** correlate trace/service/deployment/model data with structured findings and evidence IDs; no autonomous corrective writes.
5. **Lab and Luminous contracts:** evaluation request/result messages for The Lab; read-only finding notifications for Luminous; remediation requires governance approval.
6. **Production gate:** test authentication fail-closed, malicious/oversized payloads, redaction, retries/deduplication, partial backend outages, graceful degradation, trace propagation, retention, metrics cardinality and replay integrity.

## Non-goals
- No deployment of `@openrouter/devtools` to production: pre-release, unsupported public hook path.
- No new universal model gateway, orchestration engine, benchmark platform or shared CMDB within Observatory.
- No new unauthenticated telemetry endpoint or credentials in logs.

## Verification / rollout
Tests should cover valid events, invalid schema, invalid trace IDs, missing auth, tenant spoofing, prompt/key redaction, limits, duplicate events and backend-unavailable behaviour. Stage behind a default-off feature flag until container import tests and authorization integration pass. Reconcile active Observatory PR #1438 and related work before merging.
