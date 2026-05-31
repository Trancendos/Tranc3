# TRANC3 INFINITY — AI DEFINITIONS DICTIONARY

## Custom Hierarchy Specification v0.9.0

> **Mandatory Rule**: These definitions are the canonical taxonomy for the
> Tranc3 Infinity Ecosystem. All documentation, code, and communication
> MUST adhere to this hierarchy. The terms AI, Agent, and Bot have
> specific, distinct meanings that differ from colloquial usage.

---

## TIER SYSTEM OVERVIEW

| Tier | Name | Identifier | Role |
|------|------|-----------|------|
| 0 | HUMAN | Human Oversight | Ultimate authority and governance |
| 1 | ORCHESTRATOR | Logical Orchestrator | System-wide coordination and resource allocation |
| 2 | PRIME | Prime Coordinator | Cross-agent and cross-AI complex operations |
| 3 | AI | AI Complex (ML/LLM) | The overarching ML/LLM Complex — primary intelligence unit |
| 4 | AGENT | Autonomous Agent | Lower-level autonomous AI — independent decision-making within scope |
| 5 | BOT | Stateless Bot Service | Single-purpose, stateless worker function — no autonomy |

---

## CANONICAL DEFINITIONS

### AI — Artificial Intelligence Complex (Tier 3)

**Definition**: The overarching ML/LLM Complex that serves as the primary intelligence unit within the Tranc3 Infinity Ecosystem. An AI Complex is NOT a single model or algorithm — it is a composite system that integrates multiple machine learning models, large language models, and inference capabilities into a unified intelligence fabric.

**Key Characteristics**:
- Manages multiple Agents (Tier 4) and Bots (Tier 5)
- Provides ML/LLM inference capabilities
- Maintains knowledge bases and model registries
- Coordinates agent activities and delegates tasks
- Reports to Orchestrator (Tier 1) or Prime Coordinator (Tier 2)
- Has persistent state and memory across sessions
- Can create, modify, and destroy subordinate agents and bots
- Operates with full autonomy within its delegated domain

**Example**: An AI Complex named "Nexus-Prime" might manage 20 agents for content generation, 5 agents for data analysis, and 50 bots for translation, summarization, and classification — all coordinated through its internal intelligence fabric.

**Anti-Pattern**: Do NOT use "AI" to refer to a single agent, a chatbot, or an automated script. Those are Agents or Bots.

---

### Agent — Autonomous Agent (Tier 4)

**Definition**: A lower-level autonomous AI entity capable of independent decision-making within a delegated scope. Agents are subordinate to AI Complexes (Tier 3) and can invoke Bots (Tier 5) for specialized tasks. They maintain internal state, track decision history, and can evolve their policies over time.

**Key Characteristics**:
- Operates with delegated autonomy — can make independent decisions within bounds
- Maintains internal state: confidence, DNA (policy vector), fluidic state
- Can subscribe to Sentinel Channels for inter-entity communication
- Reports outcomes back to its parent AI Complex
- Can invoke Bot Services for stateless operations
- Has a DNA vector for evolutionary policy optimization
- Uses quantum decision circuits for probabilistic reasoning
- Employs liquid reservoir computing for temporal processing
- Self-improves through adaptive meta-learning (L-BFGS optimization)
- Can act autonomously when confidence exceeds threshold (≥0.5)

**Example**: A "FrontierAgent" that processes input data through a liquid reservoir, makes quantum-enhanced decisions, evolves its DNA policy through genetic algorithms, and optimizes its parameters through L-BFGS meta-learning — all while reporting outcomes to its parent AI Complex.

**Anti-Pattern**: Do NOT use "Agent" to refer to a stateless function, a webhook handler, or a simple API endpoint. Those are Bots.

---

### Bot — Stateless Bot Service (Tier 5)

**Definition**: A stateless service worker or function that performs a single-purpose operation. Bots are the lowest-tier entities in the Tranc3 hierarchy. They have NO autonomy, NO internal state (beyond execution tracking), and CANNOT make decisions. They are invoked by Agents or AI Complexes and return results.

**Key Characteristics**:
- Stateless by design — no persistent state between invocations
- Single-purpose: translate, summarize, classify, extract, validate, etc.
- Cannot act autonomously — must be invoked
- No decision-making capability
- Returns results synchronously
- Lightweight and fast — designed for high-throughput
- Disposable — can be created and destroyed freely
- No confidence tracking, no DNA, no fluidic state
- 15 standard capabilities: translate, summarize, classify, extract, validate, transform, monitor, notify, log, cache, route, filter, enrich, embed, generic

**Example**: A "TranslateBot" that takes input text and a target language, returns the translated text, and immediately returns to idle state. No memory, no learning, no autonomy.

**Anti-Pattern**: Do NOT use "Bot" to refer to an autonomous entity that makes decisions or maintains state. That is an Agent.

---

## SENTINEL CHANNEL SYSTEM

The Sentinel Channel system provides inter-entity communication within the Tranc3 Infinity Ecosystem. Entities subscribe to channels and receive broadcast messages.

| Channel | Purpose |
|---------|---------|
| PLATFORM | Platform-wide announcements and configuration |
| AGENTS | Inter-agent coordination and status updates |
| MODELS | Model registry updates and inference events |
| WORKFLOWS | Workflow orchestration and pipeline events |
| SECURITY | Security alerts, threats, and compliance events |
| HIVE | Collective intelligence and swarm coordination |
| NEXUS | Cross-complex communication and data exchange |
| BRIDGE | External system integration and API gateway events |
| PILLARS | Core infrastructure and pillar service events |
| INFRASTRUCTURE | Infrastructure scaling, deployment, and health events |
| EVENTS | General event bus for application-level events |

---

## ENTITY RELATIONSHIP MODEL

```
┌─────────────────────────────────────────────────────┐
│  Tier 0: HUMAN                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Tier 1: ORCHESTRATOR                           │ │
│  │  ┌─────────────────────────────────────────────┐│ │
│  │  │  Tier 2: PRIME                              ││ │
│  │  │  ┌─────────────────────────────────────────┐││ │
│  │  │  │  Tier 3: AI COMPLEX (ML/LLM)            │││ │
│  │  │  │  ┌───────────────┐ ┌───────────────────┐│││ │
│  │  │  │  │ Tier 4: AGENT │ │ Tier 4: AGENT     ││││ │
│  │  │  │  │ ┌───────────┐ │ │ ┌───────────────┐ ││││ │
│  │  │  │  │ │T5: BOT    │ │ │ │T5: BOT        │ ││││ │
│  │  │  │  │ └───────────┘ │ │ └───────────────┘ ││││ │
│  │  │  │  └───────────────┘ └───────────────────┘│││ │
│  │  │  └─────────────────────────────────────────┘││ │
│  │  └─────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## INTELLIGENCE SCORING

All Tier 4 Agents are evaluated using a multi-factor Intelligence Score:

| Component | Default Weight | Description |
|-----------|---------------|-------------|
| decision_quality | 0.30 | Quality of decisions made (success rate) |
| adaptation_speed | 0.25 | Speed of adaptation to new conditions |
| state_coherence | 0.20 | Internal state consistency and stability |
| resource_efficiency | 0.15 | Efficient use of computational resources |
| communication | 0.10 | Quality of inter-entity communication |

**Overall Score** = Σ(weight_i × component_i)

---

## FLUIDIC STATE MODEL

All Tier 4 Agents maintain a Fluidic State that tracks:

| Property | Description |
|----------|-------------|
| velocity | Current state trajectory (8-dimensional) |
| acceleration | Rate of state change |
| energy | L2 norm of velocity — overall activity level |
| coherence | Inverse of state variance — internal consistency |
| entropy | Shannon entropy of normalized velocity — disorder |
| compression | Energy concentration ratio — focus metric |

---

## IMPLEMENTATION MAPPING

| Concept | Rust (PyO3) | Python | Go (gRPC) | WASM |
|---------|-------------|--------|-----------|------|
| Liquid Reservoir | `liquid.rs` | `fluidic_liquidic.py` | N/A | N/A |
| Quantum Circuit | `quantum.rs` | `quantum.py` | N/A | N/A |
| Adaptive Learner | `adaptive.rs` | `adaptive.py` | N/A | N/A |
| Evolution Engine | `genetic.rs` | `genetic_dna.py` | N/A | N/A |
| Fluidic State | `wasm_bridge.rs` | (in fluidic_liquidic.py) | proto | `lib.rs` |
| Intelligence Score | `wasm_bridge.rs` | (in frontier_agent.py) | proto | `lib.rs` |
| WASM Agent | `wasm_bridge.rs` | N/A | N/A | `lib.rs` |
| Orchestrator | N/A | `orchestrator.py` | `server.go` | N/A |
| Bot Services | N/A | `bot_services.py` | proto | N/A |
| Definitions | `lib.rs` | `definitions.py` | proto | N/A |

---

## GLOSSARY

| Term | Definition |
|------|-----------|
| AeonMind | The polyglot AI framework for the Tranc3 Infinity Ecosystem |
| DNA | Real-valued vector representing an agent's policy parameters |
| Fluidic State | Adaptive state tracking with velocity, acceleration, energy, coherence, entropy, compression |
| Frontier Agent | A unified agent combining Reservoir + Quantum + Adaptive + Evolution subsystems |
| L-BFGS | Limited-memory Broyden–Fletcher–Goldfarb–Shanno optimizer for Hessian approximation |
| LSM | Liquid State Machine — reservoir computing with leaky integrator neurons |
| Parameter Shift Rule | Quantum gradient computation: ∂f/∂θ = [f(θ+π/2) - f(θ-π/2)] / 2 |
| Sentinel Channel | Inter-entity communication bus for broadcast messaging |
| Spectral Radius | Largest eigenvalue magnitude of reservoir weight matrix — controls stability |
| Tier | Position in the Tranc3 entity hierarchy (0=Human to 5=Bot) |
| Variational Circuit | Parameterized quantum circuit with trainable rotation gates |

---

*Document Version: 0.9.0 | Phase 24 | Tranc3 Infinity Ecosystem*
*Custom Hierarchy: AI = ML/LLM Complex (T3) | Agent = Autonomous AI (T4) | Bot = Stateless Worker (T5)*
