# DVMS entity flow — who does what with a vulnerability

**Status:** partially wired, and this document says which parts.
**Last measured:** 2026-09-04 against `claude/cloud-only-production-ready-25usvd`.

The flow below is the platform owner's architecture, written down and then
measured against the tree. Where a step is real, the code path is named. Where
it is not, it says so — an architecture document that describes intent as
though it were implementation is the same failure this whole engagement has
been chasing: a control that exists on paper, reports as present, and does not
act.

## The flow

```
                    Section 7 (The Dutchy)
                    comprehensive updates + evidence
                     │            │            │
                     ▼            ▼            ▼
Cryptex (Renik) ─────────► The Lab (The Dr. + Slime) ─────► The Chaos Party
identifies, assesses,      remediates: Requests and         post-action testing
flags critical             Changes, debugging, incidents    and validation
       │                            │                             │
       └──────────────┬─────────────┴─────────────────────────────┘
                      ▼
            The Observatory (Norman Hawkins)
            every report, success and failure, logged
                      │
                      ▼
            The Basement (Gary Glowman)
            learning, evolution, living wiki
                      ▲
                      │  orchestration
            Luminous (Cornelius MacIntyre) ──► The Digital Grid (Tyler Towncroft)
            routes information to its              pipelines and workflows
            Location                                        │
                      │                                     ▼
                      └──────────► The HIVE (The Queen) ─── swarm, when an AI's
                                   own Bots and Agents are overtaxed
```

## Step by step, with what is actually wired

### 1. Cryptex identifies — **partly wired**

`src/cryptex/` holds the threat detector, CVE scanner, MISP and Wazuh
connectors and the IOC bridge to `workers/cryptex/`. Separately,
`scripts/vulnerability_census.py` scans 97 dependency surfaces across pip and
npm and classifies every finding as `fixable`, `accepted` or `blocked`.

Those two are not yet the same system. The census is Cryptex's dependency
assessment in everything but name and does not run under Cryptex's routes.

### 2. Cryptex hands The Lab a priority order — **wired, this change**

This was the gap. The census produced findings keyed by *manifest path*
(`workers/the-studio/requirements.txt`); The Town Hall's ITSM
(`src/townhall/itsm.py`) produces Incidents and Changes keyed by a *service*
string it resolves to a Location. Nothing turned one into the other, so the
assessment stopped at a report and the remediation queue stayed empty.

Two pieces close it:

- **`src/dvms/surface_owner.py`** joins a manifest path to the Location that
  owns it, through three ladders: each Location's declared `worker_path`, the
  compose port via `get_entity_for_port`, and an explicit table for the rest.
  Measured today: **97 surfaces, 68 owned across 37 Locations, 29 cross-cutting
  and stewarded, 0 unowned.** `scripts/check_surface_ownership.py` fails if
  that last number ever stops being zero.
- **`src/dvms/dispatch.py`** turns an owned finding into the record ITIL says
  it is: a **Change** where a patch exists and is reachable, an **Incident**
  where one does not, and an Incident at the top of the queue for a surface
  that could not be scanned at all — unknown exposure outranks known exposure.
  `scripts/dvms_dispatch.py` shows the plan; `--apply` files it.

Priority bands, highest first: P1 unscannable surface, P2 fixable on an owned
surface, P3 fixable on a cross-cutting surface and blocked findings, P4 the
rest. Volume breaks ties. Deliberately simple: a score nobody can reproduce by
hand is a queue nobody trusts, and an untrusted queue gets worked in whatever
order somebody prefers.

### 3. Section 7 briefs both, and gives The Observatory the evidence — **not wired**

`src/research/section7.py` already summarises Observatory audit trails, runs
analysis over Basement archives, and feeds The Library. What it does not do is
brief Cryptex or The Lab on their own aspects, or file the evidence behind a
brief as an Observatory record. Today the census's evidence lives in
`docs/governance/vulnerability-census-history.jsonl`, which nothing reads back.

### 4. The Observatory records everything — **wired for audit, not for DVMS**

`src/observability/` writes the audit log and `src/basement/bridge.py` forwards
SECURITY/CRITICAL events to the durable archive. ITSM emits `incident.raised`,
`incident.resolved` and `change.requested`, so records filed by the dispatcher
DO reach the Observatory through the existing event path. The census's own
successes and failures do not.

### 5. The Basement learns — **wired for archive, not for learning**

`src/basement/` archives, scores holding value and promotes. The living wiki
The Dr. would grow from is not built: nothing turns a resolved remediation into
a Library article.

### 6. The Chaos Party validates after the fact — **not wired**

`tests/test_chaos.py` and `workers/chaos-party/` exist. Nothing triggers a
validation run off a completed remediation, and nothing relays the result to
The Observatory.

### 7. Luminous orchestrates, the Grid carries it — **not wired**

`src/bio_neural/` and `src/workflow/` both exist and are both real. No workflow
DAG carries a DVMS finding from Cryptex to The Lab today; the dispatcher writes
to ITSM directly. That is the right first step and the wrong end state — the
Grid is where the routing belongs once there is more than one consumer.

### 8. The HIVE swarms when an AI is overtaxed — **not wired**

`workers/hive-service/` and `workers/swarm-coordinator-service/` exist. There
is no signal from The Lab or Cryptex that says "I am at capacity", so nothing
can call for help. The design principle stands and is worth keeping: an AI uses
its own Bots and Agents first, and escalates only when overwhelmed.

## The correction this document records

An earlier assessment in this workstream measured the DVMS/CMDB overlap as
**zero** and reported it as though the linkage did not exist. That number was
right about the data and wrong about the architecture, and the difference
matters.

What was measured was the **join**: the census keys everything by manifest
path, `src/cmdb/identity.py` keys by ServiceID, PID, Location name or port, and
nothing mapped between them. What was *concluded* — that the entity design was
absent — was wrong. Cryptex and The Lab are Locations in `PLATFORM_ENTITIES.md`
and `src/entities/platform.py`, with Renik and The Dr. + Slime as their Lead
AIs, exactly as described. The design was **unwired**, not absent.

That distinction is the difference between "build this" and "connect this", and
it changed the work: the fix was a 200-line join, not a new subsystem.

## What refuses to guess, and why

Three places in this path decline to infer an owner, and all three do it for
the same reason:

- `src/cmdb/identity.py` returns a null PID for cross-cutting infrastructure
  rather than picking a plausible Location.
- `src/townhall/itsm.py::resolve_ownership` records `resolved: False` rather
  than guessing.
- `src/dvms/surface_owner.py` returns `unmapped` rather than nearest-match.

A finding routed to the wrong Location is worse than a finding routed nowhere.
The wrong Location closes it as not-mine, the right one never hears about it,
and the summary shows it as handled. A gap that is visible gets fixed; a wrong
answer that looks right does not.

## Next, in the order that pays

1. **Section 7 → Observatory evidence records.** The census already produces
   the evidence; it needs a writer, and it is the cheapest step here.
2. **Chaos Party validation on remediation close.** A Change that closes
   without a validation run is a Change nobody proved.
3. **Basement → Library article on resolution.** This is the learning loop the
   owner asked for, and it needs (1) and (2) to have anything to learn from.
4. **Grid workflow for the dispatch path.** Once more than one consumer needs
   the routing, the direct ITSM write becomes the thing to replace.
5. **HIVE capacity signal.** Last, because nothing can act on it until the
   queue above it is real enough to saturate.
