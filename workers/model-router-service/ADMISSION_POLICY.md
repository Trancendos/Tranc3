# Luminous model-routing admission: initial enforcement

Owner: Luminous / Mastermind (PID-LUM)
Scope: `workers/model-router-service/worker.py`, `POST /route` selection only.

## Configuration

`LUMINOUS_ALLOWED_LOCAL_MODELS` is a comma-separated **explicit allowlist** of installed Ollama model IDs (for example `llama3.1:8b,qwen2.5-coder:7b`). It defaults to empty, which means **no model is routed**. Provision the local models and verify their provenance before configuring these IDs.

The selected provider must equal `ollama`; the model ID must appear in the allowlist; the row must be active and satisfy existing free-tier filtering. The `is_free` database bit is **not** treated as current proof of external free pricing. The selection API will return HTTP 403 if no candidates pass.

No external network model, paid provider, or restricted-classification path is enabled. The current endpoint does not execute inference, and therefore this guard is NOT an execution-layer security boundary.

## Production blockers

- Apply centrally authenticated principal, tenancy and classification policy at **every** execution boundary, including LiteLLM chat/embed, streaming, tools, fallback and direct provider SDK integrations.
- Do not expose cost_verified/advertised_free as client-controlled booleans. Obtain pricing and cost evidence from trusted, refreshed catalogue records; use signed/controlled policy snapshots with expiry.
- Implement budget reservations and atomic accounting before allowing billable requests, accounting for concurrency and streaming cancellation.
- Add route contract tests with authenticated test clients, configuration combinations and SQLite fixture isolation; run CI/security scans; validate Docker import/build context.
- Provide audit/trace events to Observatory without raw prompts, secrets or sensitive responses.
- Review historical seeded model pricing, remove false claims of zero cost, validate local availability and create a staged rollout/rollback plan.

## Ownership boundaries

Luminous owns decision/adapter logic. Turing's Hub benchmarks, The Spark owns MCP connectivity, Observatory owns monitoring evidence, and Artifactory owns artefact promotion. Do not merge those platforms into Luminous.

This change deliberately **reduces** eligible routing results unless administrators explicitly configure approved local models.
