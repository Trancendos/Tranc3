# API Marketplace / OpenRouter consolidation — evidence and implementation contract

Status: **DRAFT / NO RUNTIME CHANGES**
Date: 2026-10-24
Scope: Trancendos Universe platform services currently housed in the Tranc3 migration repository.

## Verified existing implementation

- `src/apimarket/marketplace.py`: in-process, in-memory connector metadata registry; connector registration, lookup, endpoint metadata and counters; event emission to Observatory on registration.
- `src/apimarket/routes.py`: read/list/register/add-endpoint HTTP routes. Registration and endpoint changes have no local authentication enforcement in this module.
- `src/ai_gateway/providers/openrouter.py`: HTTPX-based OpenRouter chat completion and model health adapter, independent of Marketplace registration.
- `src/core/openrouter_adapter.py`: second HTTPX-based OpenRouter completion adapter with its own fallback selection and a claim about unauthenticated free access that must be verified/removed.
- `src/inference/llm_router.py`: further inference selection; inspect consumers before consolidation.
- `tranc3-ts/src/hubs/apimarketplace/`: TheAPIMarketplaceAI, BrokerAgent, TollAgent, RegistrarBot, ValidatorBot and RouterBot already have defined homes. Preserve their identity.
- `docs/services/api-marketplace/README.md`: existing factual gap assessment: gateway execution, credential lifecycle, enforced rate limits, webhook delivery, persistence and MCP tool generation are *not* implemented by the Python Marketplace registry.

## Ownership / no-duplication contract

| Concern | Authority |
| --- | --- |
| External API/model provider registration, contract and connection lifecycle | API Marketplace |
| Model benchmarking, evaluations, suitability evidence | Turing's Hub |
| Cross-application demand and workflow coordination | Luminous / Mastermind |
| Observed integration evidence and reconciliation | Observatory |
| Configuration item identity and dependency relationships | CMDB |
| Documentation, provenance and architectural evidence | Library |
| Policy authorship, approval and exceptions | Townhall |
| Secret custody | The Void / currently authorised credential service |

Do not create a separate AI Fabric platform or transfer model benchmarking to Marketplace. Treat the existing Tranc3 repository as migration source, not the Trancendos Universe identity.

## Implementation backlog, ordered by prerequisite

### P0 — stop unsafe state transitions
1. Protect all Marketplace mutation routes with existing platform authentication and role-based authorisation. Test unauthenticated calls cannot register connectors or endpoints.
2. Validate connector URL schemes and hosts at registration and **again at execution**, including DNS rebinding, redirect, localhost, link-local and private-address SSRF protections appropriate to policy; do not grant arbitrary outbound proxy access.
3. Establish stable Integration IDs and a typed, versioned event contract. Distinguish `discovered`, `registered`, `approved`, `enabled`, `disabled` and `retired`. Neither discovery nor registration implies authorisation.
4. Remove misleading production-ready labels until tests prove effective enforcement.

### P1 — integrate rather than duplicate
5. Map existing OpenRouter adapters and all callers; choose a canonical adapter behind the Marketplace's provider contract. Preserve compatibility wrappers temporarily; retire only after dependency tests.
6. Integrate runtime execution with the existing approved API gateway (Gravitee if actually deployed) rather than coding an unauthorised new generic proxy.
7. Keep credentials in authorised secret storage; Marketplace stores references, not secrets. Scope credentials to tenant, integration, provider and operation.
8. Enforce per-consumer limits/budgets and policy-compatible model fallbacks. Never permit fallback to loosen residency, confidentiality, provider or model restrictions.
9. Persist catalogue state with transactional uniqueness constraints and migrations. Document recovery, rollback and config-source precedence.

### P2 — reconcile and verify
10. Publish anonymised, correlation-ID-linked lifecycle and execution events to Observatory. Reconcile observed connections with authoritative Marketplace records without silently auto-approving them.
11. Upsert CMDB relationship edges and Library evidence references idempotently. Record origin, version, effective time and source evidence.
12. Consume Turing's Hub benchmark artefacts for candidate model selection, without reimplementing evaluations in Marketplace.
13. Implement integration contract tests, secrets/SSRF abuse tests, outage/fallback tests, rate-limit tests and audit-event verification; verify staging before production rollout.

## Acceptance criteria

- Unauthenticated registration and endpoint mutation attempts fail.
- An unapproved connector can be discovered but cannot execute.
- Calls cannot target blocked network destinations, including through redirects or DNS changes.
- Only the selected canonical OpenRouter adapter performs production requests; existing consumers stay compatible.
- Missing credentials fail safely without secret leakage in logs/exceptions.
- Fallback choices satisfy the same policy envelope as the original request.
- All approved calls trace to Marketplace Integration ID and emit correlated Observatory events.
- CMDB and Library maintain linked records without becoming competing provider catalogues.
- Turing's Hub supplies evaluation evidence, not a second execution gateway.
- The integration has reproducible local and CI tests, rollback instructions and deployment evidence.

## Evidence / limitations

This is a code-inspection and architectural consolidation deliverable, **not** proof of production deployment or tested operation. Existing deployed Gravitee, Void, Observatory, CMDB and Library integrations require separate verification. Do not merge or migrate the runtimes based only on this document.
