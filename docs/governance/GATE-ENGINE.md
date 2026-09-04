# Deterministic Gate Engine

> **Generated from `src/gates/decision.py` by
> `scripts/generate_gate_engine_doc.py`.** Do not edit by hand — change
> the resolver and regenerate. `--check` fails CI when the two disagree.

## What it is for

The platform already had a request-path gate before this one:
`MagnaCartaMiddleware`, installed on the app at `api.py`, inside
`ZeroTrustASGIMiddleware` so it can read decoded claims. Two things stop
it being a control.

`MAGNA_CARTA_ENABLED` defaults to `false` — in
`src/compliance/magna_carta.py` and again in
`docker-compose.production.yml` as `${MAGNA_CARTA_ENABLED:-false}` — so
`dispatch` returns before a single rule runs. And when it is switched on
it is advisory: the outcome is a boolean, and blocking needs a second
flag in a config file.

A boolean also cannot say what governance needs to say. *Not compliant*
collapses four different responses into one: refuse it, hold it for a
human, strip the offending part and continue, or continue with less
capability. This engine is that vocabulary and the resolver over it.

It does not change the default. Turning a security control from advisory
to enforcing changes production behaviour and belongs to the owner, not
to the change that supplied the decision model it lacked.

## Decisions

| Decision | Meaning |
|---|---|
| `allow` | Continue normally. |
| `block` | Refuse the request or action. |
| `hold` | Pause for a named human approver. |
| `redact` | Continue without the offending content. |
| `degrade` | Continue with reduced capability or a safe fallback. |

### Severity order

A request carrying several violations takes the strongest response any
one of them demands. Severity is ranked by how much is withheld from the
caller, ascending:

```text
  allow  <  degrade  <  redact  <  hold  <  block
```

Not alphabetically. Sorted as text the order would be allow, block, degrade, hold, redact, which ranks `redact` above `block` — so a prohibited action would
proceed with its address masked.

## Risk tiers

Tiers are `RiskTier` from `src/compliance/ai_governance.py`, mapped to
the EU AI Act. When policy cannot be read, what happens depends on what
is at stake:

| Tier | Policy unreadable | Why |
|---|---|---|
| `unacceptable` | `block` | an unenforceable control on a consequential action is worse than an outage, because it looks like it worked |
| `high` | `block` | an unenforceable control on a consequential action is worse than an outage, because it looks like it worked |
| `limited` | `degrade` | refusing everything on a policy-store hiccup teaches operators to disable the gate, which is the failure it exists to prevent |
| `minimal` | `degrade` | refusing everything on a policy-store hiccup teaches operators to disable the gate, which is the failure it exists to prevent |

### The unrecognised tier

A tier the engine does not recognise — absent, empty, misspelled, or
from a newer policy version — is treated as the **highest**, never the
lowest. That is the fail-open this engine exists to avoid: an
unclassified request is the one most likely to need the gate, and
mapping it to `minimal` waves exactly that through.

## Prohibited actions

`unacceptable` is Article 5 — prohibited outright. It blocks with no
violation required, and a clean rule evaluation cannot excuse it.

## Determinism

`decide()` is pure: no clock, no randomness, no I/O, no model. The same
context and violations give the same outcome, which is what makes a
trace replayable and a policy change regression-testable. Models may
classify, score and recommend *into* the context; they never decide.

`GateContext` is frozen for the same reason — a decision re-derived from
a mutated context is not the decision that was taken.

## Worked outcomes

| Situation | Decision |
|---|---|
| clean evaluation, limited risk | `allow` |
| prohibited action, nothing flagged | `block` |
| policy unreadable, high risk | `block` |
| policy unreadable, minimal risk | `degrade` |
| one rule wants redaction, another wants approval | `hold` |

## What an outcome carries

Rendered from a real `GateOutcome.to_dict()`, so this list cannot
outlive the record it describes.

| Field | Where |
|---|---|
| `decision` | outcome |
| `control_ids` | outcome |
| `reasons` | outcome |
| `policy_available` | outcome |
| `trace_id` | outcome.context |
| `tenant_id` | outcome.context |
| `actor_id` | outcome.context |
| `action` | outcome.context |
| `risk_tier` | outcome.context |
| `purpose` | outcome.context |
| `policy_version` | outcome.context |
| `data_tags` | outcome.context |
| `agent_id` | outcome.context |

`control_ids` holds every rule that fired, not only the strongest. An
operator fixing a blocked request needs the whole set; the winning rule
alone tells them to fix one thing and hit the next block immediately.
`policy_available` records whether policy was readable at all, which is
what separates a refusal the policy asked for from one the outage forced.
