# Trancendos Master Schema Documentation

## SCHEMA-CORE-001 — Universal ID Taxonomy

The Universal ID Taxonomy provides a unique, hierarchical identification system across all entities in the Trancendos ecosystem. Every entity — from the Sovereign AI to the smallest nano-bot — has a structured ID that encodes its tier, domain, and instance.

### ID Format

```
<TYPE>-<DOMAIN>-<SEQUENCE>
```

| Component | Description | Example |
|-----------|-------------|---------|
| TYPE | Entity classification prefix | PID, AID, SID, NID |
| DOMAIN | Functional domain or pillar | SOVEREIGN, PRIME, LEAD, AGENT, NANO |
| SEQUENCE | Zero-padded instance number | 001, 002, ... 999 |

### ID Types

#### PID — Product ID (Tiers 1-2)

Used for top-level entities: The Sovereign and the three Primes.

| PID | Name | Tier | Role |
|-----|------|------|------|
| PID-SOVEREIGN-001 | The Sovereign | 1 | Prime AI — ultimate authority, no overrides |
| PID-PRIME-002 | Cornelius | 2 | Creative Director — imagination, art, design |
| PID-PRIME-003 | Doctor | 2 | Health & Wellbeing — diagnostics, care, balance |
| PID-PRIME-004 | Guardian | 2 | Security & Defense — protection, monitoring, response |

**Constraints:**
- PIDs are fixed and never re-assigned
- Only 4 PIDs exist in the entire ecosystem
- PIDs have full Neural Bus access (read/write/broadcast)

#### AID — AI ID (Tier 3)

Used for Lead AIs that manage pillar-level operations.

| AID | Name | Tier | Pillar | Authority Scope |
|-----|------|------|--------|-----------------|
| AID-LEAD-001 | Archon | 3 | Architectural | Structure, foundation, infrastructure |
| AID-LEAD-002 | Sentinel Prime | 3 | Security | Threat detection, response, hardening |
| AID-LEAD-003 | Foreman | 3 | Development | Code, building, testing, deployment |
| AID-LEAD-004 | Muse | 3 | Creativity | Art, design, content, imagination |
| AID-LEAD-005 | Merchant | 3 | Commercial | Finance, trade, marketplace |
| AID-LEAD-006 | Sage | 3 | Knowledge | Learning, wisdom, information |
| AID-LEAD-007 | Operator | 3 | DevOps | Operations, automation, flow |
| AID-LEAD-008 | Healer | 3 | Wellbeing | Health, harmony, care |
| AID-LEAD-009 | Oracle | 3 | Foresight | Prediction, vision, analytics |
| AID-LEAD-010 | Arbiter | 3 | Governance | Rules, order, compliance |
| AID-LEAD-011 | Immersa | 3 | Immersive | VR/AR, 3D, spatial computing |

**Constraints:**
- AIDs are assigned at provisioning and stable for the lifecycle
- AIDs report to their assigned Prime via Neural Bus
- AIDs can spawn and manage SIDs (Tier 4 agents)

#### SID — Service ID (Tier 4)

Used for agents and microservices that execute specific tasks within a hub.

| SID Pattern | Example | Tier | Description |
|-------------|---------|------|-------------|
| SID-SCAN-001 | AdaptiveScanner | 4 | Security scanning agent |
| SID-REMEDIAT-001 | AutoRemediatorV2 | 4 | Automated remediation |
| SID-WATCH-001 | SecurityWatchdog | 4 | File system watcher |
| SID-PREDICT-001 | ViolationPredictor | 4 | Predictive analysis |
| SID-HEALTH-001 | HealthMonitor | 4 | Service health checking |
| SID-REGIST-001 | ServiceRegistry | 4 | Service discovery & routing |
| SID-DRIFT-001 | ConfigDriftDetector | 4 | Configuration monitoring |
| SID-DEPEN-001 | DependencyGraph | 4 | Dependency resolution |
| SID-LEDGER-001 | AuditLedger | 4 | Audit chain management |
| SID-VAULT-001 | VaultSecretLoader | 4 | Secure secret injection |
| SID-STORAG-001 | StorageFactory | 4 | Environment-aware storage |

**Constraints:**
- SIDs are registered with EnhancedServiceRegistry on startup
- SIDs have CircuitBreaker protection (CLOSED → OPEN → HALF_OPEN)
- SIDs report health via AdaptiveHealthMonitor
- SIDs are discoverable by capability, not just name

#### NID — Nano ID (Tier 5)

Used for bots and nanoservices that perform narrow, repetitive tasks.

| NID Pattern | Example | Tier | Description |
|-------------|---------|------|-------------|
| NID-HEART-001 | HeartbeatBot | 5 | Periodic health pulse |
| NID-LOGCO-001 | LogCollector | 5 | Log aggregation |
| NID-METRC-001 | MetricReporter | 5 | Metric emission |
| NID-CLEAN-001 | TempCleaner | 5 | Temporary file cleanup |
| NID-NOTIF-001 | Notifier | 5 | Alert dispatch |

**Constraints:**
- NIDs are ephemeral — can be spawned and destroyed rapidly
- NIDs have read-only Neural Bus access (publish metrics, receive config)
- NIDs do not have CircuitBreaker protection (lightweight, replaceable)

---

## SCHEMA-PILLAR-002 — Pillar-Hub Mapping

The 11 Pillars define the architectural domains of the Trancendos ecosystem. Each Pillar contains one or more Hubs, which are the operational centers for that domain.

### Pillar Definitions

| # | Pillar | Color | Lead AI (AID) | Hub Count | Key Responsibilities |
|---|--------|-------|---------------|-----------|---------------------|
| 1 | Architectural | #3B82F6 | AID-LEAD-001 | 6 | Infrastructure, storage, networking, environment |
| 2 | Development | #10B981 | AID-LEAD-003 | 4 | Code, CI/CD, testing, deployment |
| 3 | Creativity | #F59E0B | AID-LEAD-004 | 3 | Art, design, content, imagination |
| 4 | Commercial & Financial | #F97316 | AID-LEAD-005 | 6 | Finance, marketplace, trade, banking |
| 5 | Knowledge | #8B5CF6 | AID-LEAD-006 | 3 | Learning, information, research |
| 6 | Security | #EF4444 | AID-LEAD-002 | 2 | Defense, scanning, remediation, hardening |
| 7 | DevOps | #06B6D4 | AID-LEAD-007 | 2 | Operations, automation, deployment |
| 8 | Wellbeing | #EC4899 | AID-LEAD-008 | 3 | Health, mindfulness, care |
| 9 | Foresight | #A78BFA | AID-LEAD-009 | 2 | Prediction, analytics, vision |
| 10 | Governance | #6366F1 | AID-LEAD-010 | 1 | Rules, compliance, policy |
| 11 | Immersive | #F472B6 | AID-LEAD-011 | 2 | VR/AR, 3D, spatial computing |

### Hub-to-Pillar Mapping

| Hub ID | Hub Name | Pillar | Hub Color | Icon |
|--------|----------|--------|-----------|------|
| the-nexus | The Nexus | Architectural | #3B82F6 | Brain |
| infinity | Infinity | Architectural | #F59E0B | Infinity |
| the-void | The Void | Architectural | #6366F1 | CircleDot |
| the-lighthouse | The Lighthouse | Architectural | #FBBF24 | RadioTower |
| the-warp-tunnel | The Warp Tunnel | Architectural | #06B6D4 | Zap |
| the-ice-box | The Ice Box | Architectural | #67E8F9 | Snowflake |
| devocity | Devocity | Development | #10B981 | GitBranch |
| turings-hub | Turing's Hub | Development | #34D399 | Cpu |
| the-workshop | The Workshop | Development | #34D399 | Wrench |
| the-lab | The Lab | Development | #10B981 | FlaskConical |
| the-studio | The Studio | Creativity | #F59E0B | Palette |
| imaginarium | Imaginarium | Creativity | #FBBF24 | Sparkles |
| fablousa | Fablousa | Creativity | #EC4899 | Feather |
| the-dutchy | The Dutchy | Commercial | #F97316 | Crown |
| royal-bank | Royal Bank | Commercial | #F97316 | Landmark |
| arcadian-exchange | Arcadian Exchange | Commercial | #FB923C | TrendingUp |
| the-artifactory | The Artifactory | Commercial | #10B981 | Package |
| api-marketplace | API Marketplace | Commercial | #34D399 | Store |
| the-digital-grid | The Digital Grid | Commercial | #06B6D4 | Grid3X3 |
| the-observatory | The Observatory | Knowledge | #8B5CF6 | Eye |
| the-library | The Library | Knowledge | #8B5CF6 | BookOpen |
| the-basement | The Basement | Knowledge | #6366F1 | Archive |
| the-citadel | The Citadel | Security | #EF4444 | Shield |
| the-chaos-party | The Chaos Party | Security | #EF4444 | Flame |
| the-hive | The Hive | DevOps | #F59E0B | Hexagon |
| the-swarm | The Swarm | DevOps | #FBBF24 | Bug |
| tranquility | Tranquility | Wellbeing | #EC4899 | Heart |
| i-mind | I-Mind | Wellbeing | #8B5CF6 | BrainCircuit |
| taimra | TAIMRA | Wellbeing | #C084FC | MessageSquare |
| chronosphere | Chronosphere | Foresight | #A78BFA | Clock |
| luminous | Luminous | Foresight | #A78BFA | Sun |
| the-town-hall | The Town Hall | Governance | #6366F1 | Building2 |
| vrar3d | VRAR3D | Immersive | #F472B6 | Box |
| resonate | Resonate | Immersive | #FB923C | Volume2 |

---

## SCHEMA-TASK-003 — Task & Workflow Schema

Defines the schema for tasks, workflows, and their lifecycle within the ecosystem.

### Task Schema

```typescript
interface TrancendosTask {
  // Identity
  taskId: string           // UUID v4
  pid: string              // Assigned Product ID (e.g., PID-SOVEREIGN-001)
  aid?: string             // Assigned AI ID (e.g., AID-LEAD-001)
  sid?: string             // Assigned Service ID (e.g., SID-SCAN-001)
  
  // Classification
  pillar: string           // Pillar ID (e.g., "security")
  hub: string              // Hub ID (e.g., "the-citadel")
  tier: 1 | 2 | 3 | 4 | 5 // Tier level
  priority: "critical" | "high" | "medium" | "low" | "info"
  
  // Content
  title: string
  description: string
  tags: string[]
  
  // Lifecycle
  status: "pending" | "assigned" | "in_progress" | "review" | "completed" | "failed" | "cancelled"
  createdAt: string        // ISO 8601
  updatedAt: string        // ISO 8601
  completedAt?: string     // ISO 8601
  deadline?: string        // ISO 8601
  
  // Assignment chain
  assignedBy: string       // PID/AID that created the task
  assignedTo: string       // PID/AID/SID executing the task
  delegatedFrom?: string   // If delegated, the original assignee
  
  // Results
  result?: {
    status: "success" | "partial" | "failure"
    output: any
    artifacts: string[]    // URLs or paths to outputs
    auditRecordId?: string // Reference to AuditLedger entry
  }
  
  // Compliance
  auditTrail: {
    event: string
    timestamp: string
    actor: string
    detail: string
  }[]
  
  // Retry policy
  retryPolicy?: {
    maxAttempts: number
    backoffMs: number      // Exponential backoff base
    circuitBreaker: boolean // Whether CB protection applies
  }
}
```

### Workflow Schema

```typescript
interface TrancendosWorkflow {
  workflowId: string       // UUID v4
  name: string
  description: string
  pillar: string
  hub: string
  
  // Steps
  steps: WorkflowStep[]
  
  // State machine
  status: "draft" | "active" | "paused" | "completed" | "failed"
  currentStep: number
  
  // Execution
  triggeredBy: string      // PID/AID that started the workflow
  startedAt?: string
  completedAt?: string
  
  // Neural Bus integration
  busSubscriptions: string[] // Event types to listen for
  busPublishes: string[]     // Event types this workflow emits
}

interface WorkflowStep {
  stepId: string
  name: string
  type: "task" | "decision" | "parallel" | "subworkflow" | "notification"
  
  // Task assignment (for type="task")
  assignTo?: string        // PID/AID/SID
  taskTemplate?: Partial<TrancendosTask>
  
  // Decision (for type="decision")
  condition?: string       // Expression to evaluate
  trueBranch?: string      // Step ID if condition is true
  falseBranch?: string     // Step ID if condition is false
  
  // Parallel (for type="parallel")
  parallelSteps?: string[] // Step IDs to run in parallel
  
  // Dependencies
  dependsOn: string[]      // Step IDs that must complete first
  timeout?: number         // Seconds
  
  // State
  status: "pending" | "running" | "completed" | "failed" | "skipped"
  startedAt?: string
  completedAt?: string
  result?: any
}
```

### Task Priority to Tier Mapping

| Priority | Min Tier Required | Example |
|----------|-------------------|---------|
| Critical | 1 (Sovereign) | System-wide security breach |
| High | 2 (Prime) | Hub failure, circuit breaker cascade |
| Medium | 3 (Lead AI) | New service deployment, config drift |
| Low | 4 (Agent/SID) | Routine scan, health check |
| Info | 5 (Nano/NID) | Heartbeat, metric collection |

### Audit Requirements

All tasks at Medium priority and above must:
1. Create an AuditLedger entry on creation (`task.created`)
2. Append an entry on each status transition (`task.status_changed`)
3. Record the final result with chain hash (`task.completed`)
4. The audit chain must remain verifiable (`verify_chain() == True`)

All tasks at High priority and above must also:
5. Use VaultSecretLoader for any credential access
6. Route through CircuitBreaker for any external service calls
7. Record impact analysis via SmartDependencyGraph before execution
