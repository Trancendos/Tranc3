# Trancendos Infrastructure Architecture — Mermaid Diagrams

This document provides Mermaid diagrams for each SYSTEM_MODE deployment topology.

## TrueNAS Mode (TRUE_NAS)

Full local infrastructure — all services run on-premises with TrueNAS DXP4800+ as the primary storage backend.

```mermaid
graph TB
    subgraph "TrueNAS DXP4800+ — Primary Storage"
        TN_ZFS[ZFS Pool<br/>NVMe SSD + HDD]
        TN_APPS[TrueNAS Apps<br/>Docker/Compose]
        TN_SNAP[ZFS Snapshots<br/>Automated Backup]
    end

    subgraph "GEEKOM Mini-PC Cluster"
        GW[Forgejo CI/CD<br/>Runner Node 1]
        GK[Forgejo CI/CD<br/>Runner Node 2]
        GA[API Gateway<br/>FastAPI + Uvicorn]
        GD[Dashboard Server<br/>Vite Dev/Preview]
    end

    subgraph "Local Network Services"
        DNS[DNS Resolver<br/>Pi-hole/AdGuard]
        PROXY[Reverse Proxy<br/>Caddy/Nginx]
        MON[Monitoring<br/>Prometheus + Grafana]
    end

    subgraph "Dimensional Backend"
        SF[StorageFactory<br/>TrueNAS Provider]
        VL[VaultSecretLoader<br/>Memory-Mapped]
        AL[AuditLedger<br/>ZFS-Backed Ledger]
        SN[Sentinel<br/>Continuous Verification]
        RG[EnhancedServiceRegistry<br/>Local Discovery]
        HM[HealthMonitor<br/>Circuit Breaker]
        DG[SmartDependencyGraph<br/>Impact Analysis]
    end

    subgraph "Trancendos AI Tier"
        T1[Tier 1: The Sovereign<br/>Prime AI]
        T2[Tier 2: Primes<br/>Cornelius · Doctor · Guardian]
        T3[Tier 3: Lead AIs<br/>AID-namespaced]
        T4[Tier 4: Agents<br/>SID-namespaced Microservices]
        T5[Tier 5: Nanos<br/>NID-namespaced Bots]
    end

    TN_ZFS --> SF
    SF --> AL
    VL --> GA
    SN --> RG
    RG --> HM
    HM --> DG
    
    GW --> RG
    GK --> RG
    GA --> SF
    GA --> VL
    GA --> HM
    
    PROXY --> GA
    PROXY --> GD
    DNS --> PROXY
    MON --> HM
    
    T1 --> RG
    T2 --> RG
    T3 --> RG
    T4 --> RG
    T5 --> RG
    
    TN_APPS --> GW
    TN_APPS --> GK
    TN_SNAP --> AL

    style TN_ZFS fill:#10B981,stroke:#065F46,color:white
    style SF fill:#10B981,stroke:#065F46,color:white
    style T1 fill:#FFD700,stroke:#92400E,color:black
    style T2 fill:#C0C0C0,stroke:#374151,color:black
```

## Hybrid Mode (HYBRID)

Mixed infrastructure — local TrueNAS for persistent data, free-tier cloud for compute and edge services.

```mermaid
graph TB
    subgraph "TrueNAS DXP4800+ — Persistent Storage"
        TN_ZFS[ZFS Pool<br/>Primary Data Store]
        TN_SYNC[Syncthing<br/>Cloud Sync Bridge]
    end

    subgraph "Oracle Cloud Free Tier"
        OCI_COMPUTE[ARM Compute<br/>4 OCPU · 24GB RAM]
        OCI_REGISTRY[Container Registry<br/>Service Images]
        OCI_API[API Gateway<br/>FastAPI Production]
    end

    subgraph "Cloudflare R2 — Free Tier"
        R2_ASSETS[Static Assets<br/>Dashboard Build]
        R2_LOGS[Audit Logs<br/>Cold Storage Archive]
        R2_BACKUP[Backup Snapshots<br/>Disaster Recovery]
    end

    subgraph "Local GEEKOM Nodes"
        GW[Forgejo CI/CD<br/>Primary Runner]
        GA[API Gateway<br/>Staging/Dev]
        GD[Dashboard Server<br/>Dev Preview]
    end

    subgraph "Dimensional Backend"
        SF[StorageFactory<br/>Hybrid Provider]
        VL[VaultSecretLoader<br/>Hybrid Secret Store]
        AL[AuditLedger<br/>Dual-Write Ledger]
        SN[Sentinel<br/>Cross-Env Verification]
        RG[EnhancedServiceRegistry<br/>Federated Discovery]
        HM[HealthMonitor<br/>Adaptive Thresholds]
        CD[ConfigDriftDetector<br/>Cross-Env Baseline]
    end

    subgraph "Trancendos AI Tier"
        T1[Tier 1: The Sovereign]
        T2[Tier 2: Primes]
        T3[Tier 3: Lead AIs]
        T4[Tier 4: Agents<br/>Cloud-Deployed]
        T5[Tier 5: Nanos<br/>Edge-Deployed]
    end

    TN_ZFS --> SF
    TN_SYNC --> R2_BACKUP
    SF --> R2_ASSETS
    SF --> TN_ZFS
    
    OCI_COMPUTE --> OCI_API
    OCI_API --> SF
    OCI_API --> VL
    OCI_REGISTRY --> OCI_COMPUTE
    
    GW --> RG
    GA --> HM
    CD --> HM
    SN --> RG
    
    R2_LOGS --> AL
    TN_ZFS --> AL
    
    T1 --> RG
    T4 --> OCI_API
    T5 --> GA

    style TN_ZFS fill:#F59E0B,stroke:#78350F,color:white
    style OCI_COMPUTE fill:#F59E0B,stroke:#78350F,color:white
    style R2_ASSETS fill:#F59E0B,stroke:#78350F,color:white
    style SF fill:#F59E0B,stroke:#78350F,color:white
    style CD fill:#F59E0B,stroke:#78350F,color:white
```

## Cloud-Only Mode (CLOUD_ONLY)

Fully remote infrastructure — no local hardware. All services run on free-tier cloud providers.

```mermaid
graph TB
    subgraph "Oracle Cloud Free Tier"
        OCI_COMPUTE[ARM Compute<br/>4 OCPU · 24GB RAM]
        OCI_API[API Gateway<br/>FastAPI Production]
        OCI_CI[Forgejo Runner<br/>CI/CD Pipeline]
        OCI_DB[SQLite on<br/>Persistent Volume]
    end

    subgraph "Cloudflare R2 — Free Tier"
        R2_ASSETS[Static Assets<br/>Dashboard + SPA]
        R2_LOGS[Audit Logs<br/>Append-Only Archive]
        R2_BACKUP[Backup Store<br/>Recovery Point]
        R2_SECRETS[Encrypted Secrets<br/>At-Rest Only]
    end

    subgraph "Cloudflare Workers — Free Tier"
        CW_EDGE[Edge Functions<br/>API Proxy / Cache]
        CW_WAF[WAF Rules<br/>Rate Limiting]
    end

    subgraph "GitHub / Forgejo Cloud"
        GH_REPO[Source Repository<br/>Mirror + PR]
        GH_CI[CI/CD Pipeline<br/>Build + Test + Deploy]
    end

    subgraph "Dimensional Backend"
        SF[StorageFactory<br/>Cloud-Only Provider]
        VL[VaultSecretLoader<br/>R2-Backed Secrets]
        AL[AuditLedger<br/>R2 Append-Only]
        SN[Sentinel<br/>Remote Verification]
        RG[EnhancedServiceRegistry<br/>Cloud Discovery]
        HM[HealthMonitor<br/>Conservative Thresholds]
        DG[SmartDependencyGraph<br/>Cloud Topology]
    end

    subgraph "Trancendos AI Tier"
        T1[Tier 1: The Sovereign<br/>OCI-Hosted]
        T3[Tier 3: Lead AIs<br/>OCI-Hosted]
        T4[Tier 4: Agents<br/>Cloud Functions]
        T5[Tier 5: Nanos<br/>Edge Workers]
    end

    OCI_COMPUTE --> OCI_API
    OCI_API --> SF
    OCI_API --> VL
    OCI_CI --> GH_REPO
    
    SF --> R2_ASSETS
    SF --> OCI_DB
    VL --> R2_SECRETS
    AL --> R2_LOGS
    
    CW_EDGE --> OCI_API
    CW_WAF --> CW_EDGE
    
    GH_CI --> R2_ASSETS
    GH_REPO --> GH_CI
    
    RG --> HM
    SN --> RG
    DG --> HM
    
    T1 --> RG
    T3 --> OCI_API
    T4 --> CW_EDGE
    T5 --> CW_EDGE

    style OCI_COMPUTE fill:#3B82F6,stroke:#1E3A5F,color:white
    style R2_ASSETS fill:#3B82F6,stroke:#1E3A5F,color:white
    style SF fill:#3B82F6,stroke:#1E3A5F,color:white
    style CW_EDGE fill:#3B82F6,stroke:#1E3A5F,color:white
```

## System Mode Transition Flow

```mermaid
stateDiagram-v2
    [*] --> CLOUD_ONLY: Default Boot
    
    CLOUD_ONLY --> HYBRID: TrueNAS Detected
    HYBRID --> TRUE_NAS: Full Local Available
    TRUE_NAS --> HYBRID: Partial Cloud Failover
    HYBRID --> CLOUD_ONLY: TrueNAS Lost
    TRUE_NAS --> CLOUD_ONLY: Full Cloud Failover
    CLOUD_ONLY --> TRUE_NAS: Direct Full Local
    
    state CLOUD_ONLY {
        [*] --> CloudProvisioning
        CloudProvisioning --> CloudRunning
        CloudRunning --> CloudDegraded: High Latency
        CloudDegraded --> CloudRunning: Recovered
    }
    
    state HYBRID {
        [*] --> HybridSync
        HybridSync --> HybridBalanced
        HybridBalanced --> HybridLocalPreferred: Local Fast
        HybridBalanced --> HybridCloudPreferred: Cloud Fast
    }
    
    state TRUE_NAS {
        [*] --> NasBoot
        NasBoot --> NasFull
        NasFull --> NasMaintenance: Scheduled
        NasMaintenance --> NasFull: Complete
    }
```

## Neural Bus Protocol — AI-to-AI Communication

```mermaid
graph LR
    subgraph "Neural Bus /v1"
        NB[Neural Bus<br/>Message Router]
    end
    
    subgraph "Tier 1 — Sovereign"
        S1[The Sovereign<br/>PID-SOVEREIGN-001]
    end
    
    subgraph "Tier 2 — Primes"
        P1[Cornelius<br/>PID-PRIME-002]
        P2[Doctor<br/>PID-PRIME-003]
        P3[Guardian<br/>PID-PRIME-004]
    end
    
    subgraph "Tier 3 — Lead AIs"
        L1[AID-LEAD-001<br/>Architecture Lead]
        L2[AID-LEAD-002<br/>Security Lead]
        L3[AID-LEAD-003<br/>DevOps Lead]
    end
    
    subgraph "Tier 4 — Agents"
        A1[SID-AGENT-001<br/>Scanner Agent]
        A2[SID-AGENT-002<br/>Remediator Agent]
        A3[SID-AGENT-003<br/>Watchdog Agent]
    end
    
    subgraph "Tier 5 — Nanos"
        N1[NID-NANO-001<br/>Heartbeat Bot]
        N2[NID-NANO-002<br/>Log Collector]
    end
    
    S1 <--> NB
    P1 <--> NB
    P2 <--> NB
    P3 <--> NB
    L1 <--> NB
    L2 <--> NB
    L3 <--> NB
    A1 <--> NB
    A2 <--> NB
    A3 <--> NB
    N1 --> NB
    N2 --> NB

    style NB fill:#8B5CF6,stroke:#4C1D95,color:white
    style S1 fill:#FFD700,stroke:#92400E,color:black
```
