# Three-Lane Transport and the Terminal Hub

**Date:** 2026-08-17
**Status:** design of record — see §5 for what is actually built
**Owner:** The Nexus (Chief Communications Officer)

Traffic across Trancendos is split into three dedicated, separately secured
lanes. Each lane has an owning Location, carries one class of payload, and
transmits on its own stream. The lanes converge only at a **Terminal Hub** —
one per Location — where the three data sets merge so the Location can act on
full context rather than on a single lane's fragment.

## 1. The three lanes

| Lane | Owner | Carries | Owning AI |
|---|---|---|---|
| **1 — Entity** | The Nexus (`PID-NXS`) | AI, Agent and Bot traffic: prompts, inter-agent messages, worker/entity transfer | Nexus-Prime |
| **2 — Human** | Infinity Bridge (`infinity-bridge-service`) | User traffic and navigation: sessions, page transitions, human-initiated actions | The Guardian (Marcus Magnolia) |
| **3 — Payload** | The HIVE (`PID-HVE`) | File and data transfer: artefacts, blobs, bulk data, queue payloads | The Queen |

Why three and not one: the lanes have genuinely different security postures,
failure modes and volume profiles. Human navigation is latency-sensitive and
low-volume; file transfer is throughput-sensitive and bursty; entity traffic is
the only lane where an untrusted prompt can reach a tool. Collapsing them means
a bulk upload can starve a login, and a prompt-injection surface sits on the
same channel as session management. Separating them lets each lane be rate
limited, audited and quarantined on its own terms — Cryptex and The Warp Tunnel
can scan lane 3 aggressively without adding latency to lane 2.

## 2. The Terminal Hub

Every Location exposes a Terminal Hub: the single point where its three inbound
lanes are correlated and merged.

```
        lane 1 ── entity  ──┐
        lane 2 ── human   ──┼──▶  ┌──────────────┐
        lane 3 ── payload ──┘     │ TERMINAL HUB │  correlate → merge → act
                                  │  <Location>  │
                                  └──────┬───────┘
                                         │
                          Location's Agents + Bots
                                         │
                                  The Observatory (audit)
```

The Hub's job is correlation, not transport. It answers: *which human action,
which entity decision, and which payload belong to the same piece of work?*
Without it, a Location receives three unrelated streams and has to guess. The
practical requirement is a shared correlation identifier spanning all three
lanes — the estate already propagates W3C TraceContext
(`src/observability/tracing.py`), which is the natural carrier: one `trace_id`
per unit of work, present on all three lanes, merged at the Hub.

**Design constraint.** A Terminal Hub must degrade per-lane, not wholesale. If
lane 3 is unavailable the Location should still serve what lanes 1 and 2 permit,
in line with each Location's declared `offline_mode`. A Hub that fails closed
on any missing lane converts a partial outage into a total one.

## 3. tAimra's Omni layer

**Omni Router**, **Omni Core** and **Omni Bridge** belong to tAimra
(`PID-TMR`, port 8074) — the opt-in digital twin — not to the transport lanes
themselves. Their purpose is to link the *types* of data flowing across the
three lanes, reason about them together, and analyse patterns over time so the
twin can assist more usefully.

The distinction matters and is easy to lose:

- the **lanes** move data and keep it separated for security and performance
- the **Terminal Hub** merges the lanes for a single unit of work, in the moment
- **tAimra's Omni layer** learns across many units of work, over time,
  correlating data *types* to build understanding of the person it serves

A naming caution: `The Nexus`'s Agent Beta is already called **Omni-Router**
(`SID-NXS-02`), whose job is routing prompts to the correct AI/Bot. That is a
different thing from tAimra's Omni Router. Two components with one name in one
estate is a defect waiting to happen — one of them should be renamed before
either is built. The Nexus agent has the prior claim in code.

## 4. The testing → evidence → learning pipeline

Testing is not a terminal activity; its output is an input to platform
improvement. The chain, with its owners:

```
The Chaos Party  (PID-TCP)
  ├─ The Mad Hatter  — adversarial: fault injection, chaos, boundary abuse
  │     agents: The March Hare, The Dormouse
  └─ Alice Dream     — deterministic: acceptance, regression, smoke
        agents: The White Rabbit, The Looking-Glass
        ↓ results
The Observatory  (PID-OBS, Norman Hawkins) — trend analysis across runs
        ↓ events
The Basement     (PID-BSM, Gary Glowman)   — durable evidence store
        ↓ when a trend or pattern is confirmed
The Library      (PID-LIB, Zimik)          — promoted to an article for admin review
        ↓ if the article warrants action
Think Tank       (PID-TNK)                 — studies it, designs the enhancement
        ↑ informed by
Section 7        (PID-DUT, The Dutchy)     — external scan: news, releases, papers,
                                             developments that bear on the problem
```

**Two Lead AIs, on purpose.** Chaos alone cannot tell you a system works — only
where it breaks. Deterministic suites cannot find what nobody thought to assert.
The two disciplines also want opposite things from a run: The Mad Hatter seeks
variance, Alice Dream requires none. One agent pair cannot serve both without
the sane suite inheriting non-determinism, which is why Alice Dream has her own
pair rather than sharing.

Both names are Lewis Carroll (*Alice's Adventures in Wonderland*, 1865, public
domain worldwide), consistent with the Location's existing March Hare, Dormouse
and Teapot-Bot naming. Only Disney's 1951 visual designs carry protection; the
names and the source text do not.

**Escalation.** The Dr. (Nikolai O'denhime) is Prime over The Chaos Party and
handles escalations within his remit, as every Prime does for their Locations.
Beyond that remit it goes to Cornelius MacIntyre (Trance-One, Luminous) or to a
governance review board — the same two-step the AI Governance Constitution's
escalation FSM already implements.

## 5. What is actually built — honest status

Nothing above should be read as describing running code. Current state:

| Element | Status | Evidence |
|---|---|---|
| Lane 1 transport | ⚠️ partial | `workers/infinity-ws/` is a WebSocket **pub/sub hub** (connect, subscribe, broadcast, channels). It carries entity traffic but does **not** route by intent — Omni-Router is designed, not implemented |
| Lane 2 transport | 🔧 declared | `infinity-bridge-service` (8070) exists in the worker map as "human traffic transfer hub"; not verified as carrying a distinct lane |
| Lane 3 transport | ⚠️ partial | The HIVE is implemented by `workers/queue-service/` (8022). A queue, not yet a three-lane-aware payload channel |
| Terminal Hub | ❌ not built | No Location has a component that correlates and merges three inbound lanes. This is the largest gap in the design |
| Lane separation | ❌ not enforced | All traffic currently arrives through Traefik on one ingress; there is no per-lane rate limit, audit or quarantine |
| Shared correlation ID | ✅ available | W3C TraceContext propagation exists (`src/observability/tracing.py`) and is the right carrier |
| tAimra Omni layer | ❌ not built | `workers/taimra/` is real and SQLite-backed but contains no Omni Router/Core/Bridge |
| Chaos Party | ✅ real | `workers/chaos-party/worker.py` (459 lines) — suites, runs, batch runs, listing |
| Chaos Party → Observatory | ❌ not wired | Chaos Party records runs to its own SQLite; nothing forwards them |
| Observatory → Basement | ✅ wired | `src/observability/observatory.py` calls `get_basement().ingest_observatory_event(event)` |
| Basement → Library promotion | ❌ not built | No mechanism promotes a confirmed pattern into a Library article |
| Section 7 external scan | 🔧 partial | `src/research/section7.py` (289 lines) exists; not wired to Think Tank |

**The two highest-value gaps**, in order: the Terminal Hub (without it the
three-lane split delivers separation but no reassembly, so Locations act on
fragments) and Chaos Party → Observatory (without it every test run is
discarded, and the entire learning pipeline downstream has no input).
