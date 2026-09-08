# Documentation Catalog

> Generated from `config/docs/living_documents.yaml` by `scripts/documentation_health.py --catalog`. Do not edit the table directly.

## Use This Map

- Start here to choose the canonical document for a platform concern.
- Treat `wiki-content/` as the reviewed source for the GitHub Wiki; the live wiki is a one-way publication mirror.
- Update a mapped canonical document in the same change as its source, or explicitly amend the registry after review.

## Living Document Contracts

| Topic | Canonical document | Kind | Role owner | Lifecycle | Change signals |
|---|---|---|---|---|---|
| Production deployment runbook | `docs/DEPLOYMENT_RUNBOOK.md` | how-to | Platform Operations (The Library) | The Workshop -> The Town Hall; intake: manual-only; destinations: repository documentation | `docker-compose.production.yml`, `scripts/compose_contract_audit.py` |
| CI/CD audit and operating model | `docs/CI-CD-AUDIT.md` | explanation | Platform Engineering (The Library) | The Workshop -> The Town Hall; intake: manual-only; destinations: repository documentation | `.github/workflows/ci.yml`, `scripts/ci_health.py`, `scripts/ci_diagnostics.py`, `scripts/retry_transient.py`, `scripts/security_backlog.py` |
| Runtime API reference | `docs/API_REFERENCE.md` | reference | API Platform (The Library) | The Workshop -> The Town Hall; intake: manual-only; destinations: repository documentation | `api.py`, `src/routers/enhanced_capabilities.py` |
| Wiki source and publishing policy | `docs/WIKI_INDEX.md` | reference | Documentation Maintainers (The Library) | The Workshop -> The Town Hall; intake: manual-only; destinations: repository wiki source, GitHub Wiki mirror | `scripts/publish-wiki.sh`, `.github/workflows/publish-wiki.yml` |
| Runtime Library review and publication | `docs/DOCUMENT_LIFECYCLE.md` | explanation | Chief Knowledge Officer (The Library) | The Workshop -> The Town Hall; intake: library-reviewed; destinations: The Library durable store, Search and RAG consumers | `src/library/knowledge_base.py`, `src/library/routes.py`, `src/library/bridge.py`, `src/townhall/itsm.py`, `src/townhall/itsm_routes.py`, `src/event_bus/wiring.py`, `src/observability/library_pipeline.py`, `src/research/section7.py`, `src/models/knowledge.py` |

## Documentation Model

The catalog uses the four Diataxis forms: tutorials teach, how-to guides solve a task, reference documents state facts, and explanations provide context. The registry is a federated knowledge model: each domain owns its canonical page and change signals while common validation runs centrally. Lifecycle locations are accountability assignments, not assertions that repository Markdown automatically enters a runtime service; see `docs/DOCUMENT_LIFECYCLE.md`. It is not a machine-learning system and does not autonomously alter operational or security guidance.

Run `python scripts/documentation_health.py --check --base-ref origin/main --check-catalog` to validate navigation, registry paths, source-to-document review coupling, and the generated catalog.
