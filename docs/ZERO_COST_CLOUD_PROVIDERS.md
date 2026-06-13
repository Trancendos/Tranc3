# Zero-Cost Cloud Providers - Tranc3 Ecosystem

**Date**: 2025-06 (Phase 9B Research)
**Mandate**: All cloud services must be zero-cost. No paid tiers, no credit-expiring trials, no hidden fees.
**Scope**: Oracle Cloud, Google Cloud, Microsoft Azure, AWS, HashiCorp - free-tier offerings only

---

## Overview

The Tranc3 ecosystem operates under a strict zero-cost mandate. This document catalogs every usable free-tier resource across the five major cloud/infrastructure providers, identifies what is genuinely "always free" versus time-limited, and maps each resource to its potential role within the Tranc3 architecture.

The SmartStorageOrchestrator already implements ZFS (priority 0) -> MinIO (1) -> Ceph (2) -> Cloudflare R2 (3) -> OCI (4). Phase 9B extends this to include additional zero-cost cloud providers as tertiary fallback layers, ensuring the system auto-modulates across providers to maintain zero cost while maximizing resilience.

### Key Terminology

- **Always Free**: Services that remain free indefinitely with specified monthly limits, no expiration
- **12-Month Free**: Services free for the first 12 months only (new accounts) - NOT suitable for long-term zero-cost
- **Trial Credits**: One-time credits that expire ($200-$300) - NOT zero-cost
- **BSL (Business Source License)**: Source-available but NOT open-source; restricts competitive use

---

## 1. Oracle Cloud Infrastructure (OCI) - Always Free

OCI provides the most generous always-free tier among major cloud providers, including free VMs with no time limit. This makes OCI the primary zero-cost cloud provider for Tranc3.

### Compute

| Resource | Always Free Allowance | Notes |
|---|---|---|
| AMD Micro VMs | 2 instances (1/8 OCPU, 1 GB RAM each) | Equivalent to ~0.25 vCPU + 2 GB total |
| Arm A1 Compute | 4 OCPUs + 24 GB RAM | Can be split across 1-4 instances |
| Total Compute | Up to 4.25 OCPUs + 26 GB RAM | Combined AMD + Arm allocation |

### Storage

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Block Volume | 200 GB total | 2 volumes, VPU 0-10 |
| Object Storage | 20 GB | Standard storage tier |
| Archive Storage | 10 GB | Cheaper tier for cold data |
| File Storage | Not free | N/A |

### Database

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Autonomous DB | 2 instances | 20 GB each, OCPU auto-scaling |
| MySQL HeatWave | 1 instance | 1 OCPU, 8 GB RAM |

### Networking

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Egress | 10 TB per month | Most generous among all providers |
| Load Balancer | 1 instance | 10 Mbps bandwidth |
| VPN (Site-to-Site) | 1 IPSec connection | Connects on-prem NAS to OCI |
| DNS | 1 zone | Zone-level DNS queries |

### Security & Management

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Vault | 150 secrets | 20 keys (HSM or software) |
| Certificates | 5 CAs + 150 certificates | TLS certificate management |
| Resource Manager | 500 jobs/month | Terraform-as-a-Service (managed) |
| Monitoring | 500 million data points/month | Metrics ingestion |
| Notifications | 1 topic, 100 subscriptions | Email/SMS/Push notifications |
| Logging | 10 GB/month | Audit + custom logs |

### Tranc3 Integration

- **OCISmartProvider** (priority 4): Already implemented in `smart_storage.py`
- **Object Storage (20 GB)**: Cold/offsite backup tier for critical configs
- **Autonomous DB**: Metadata catalog, ID registry backup
- **Arm A1 Compute (4 OCPU + 24 GB)**: Agent/nanoservice host (low-priority workers)
- **VPN Site-to-Site**: Connect TRUE_NAS to OCI for hybrid replication
- **Vault (150 secrets)**: Overflow secret storage beyond Infinity Void
- **Resource Manager**: Infrastructure-as-Code for OCI resources
- **10 TB egress**: Unmatched - enables large data transfers without cost

---

## 2. Google Cloud Platform (GCP) - Always Free

GCP provides 20+ always-free products with monthly usage limits. The free tier is per-billing-account and has no expiration date, though Google reserves the right to change offerings with 30 days notice.

### Compute

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Compute Engine | 1 e2-micro VM/month | US regions only (us-west1, us-central1, us-east1) |
| Cloud Run | 2M requests, 360K GB-sec memory, 180K vCPU-sec | Serverless containers |
| Cloud Functions | 2M invocations, 400K GB-sec, 200K GHz-sec | Event-driven functions |
| App Engine | 28 F1 hours/day + 9 B1 hours/day | Standard environment only |
| GKE | 1 free Autopilot or zonal Standard cluster/month | Cluster management fee only |

### Storage

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Cloud Storage | 5 GB regional (US only) | 5K Class A + 50K Class B ops/month |
| Egress | 100 GB/month | North America to all regions (excl. China/Australia) |
| Persistent Disk | 30 GB/month | Standard PD with e2-micro |
| Artifact Registry | 0.5 GB | Container image storage |

### Database

| Resource | Always Free Allowance | Notes |
|---|---|---|
| BigQuery | 1 TiB queries + 10 GB storage/month | Data warehouse |
| Firestore | 1 GiB storage, 50K reads/20K writes per day | NoSQL document DB |
| Cloud SQL | Trial only (30 days) | NOT always free |

### AI/ML APIs

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Vision API | 1,000 units/month | Image analysis |
| Natural Language | 5,000 units/month | Text analysis |
| Speech-to-Text | 60 minutes/month | Audio transcription |
| Translation | 500K chars/month (basic) | Language translation |

### Security & Developer Tools

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Secret Manager | 6 active versions + 10K access ops/month | Secret storage |
| Cloud KMS | 100 key versions + 10K crypto ops/month | Key management (Autokey only) |
| Cloud Build | 2,500 build-minutes/month | CI/CD |
| Cloud Shell | Free access + 5 GB persistent disk | Browser-based shell |
| Pub/Sub | 10 GiB messages/month | Messaging |

### Tranc3 Integration

- **GCPStorageProvider** (priority 5): Cloud Storage (5 GB) as additional cold backup
- **Cloud Run**: Host lightweight Tranc3 API endpoints / agent workers
- **Firestore**: Entity metadata cache, session state for agents
- **BigQuery**: Analytics on vault audit logs, storage metrics
- **Secret Manager (6 versions)**: Emergency secret backup (very limited)
- **Cloud KMS (100 keys)**: Key management for encryption at rest
- **Pub/Sub (10 GB)**: Event-driven nanoservice communication
- **Cloud Build (2,500 min)**: CI/CD pipeline for Tranc3 builds

---

## 3. Microsoft Azure - Always Free

Azure provides 65+ always-free services. Many valuable services are free for 12 months only (marked below as 12M), but the always-free tier is substantial.

### Compute

| Resource | Always Free Allowance | Free Period |
|---|---|---|
| App Service | 10 web/API apps, 1 GB storage, 1 hr/day | Always |
| Functions | 1 million requests/month | Always |
| Container Apps | 180K vCPU-sec, 360K GiB-sec, 2M requests | Always |
| AKS | Cluster management free (pay for nodes) | Always |
| Static Web Apps | 100 GB bandwidth, 2 custom domains, 0.5 GB/app | Always |
| Virtual Machines | 750 hrs B2pts/B2ats v2 burstable | 12M only |

### Storage

| Resource | Always Free Allowance | Free Period |
|---|---|---|
| Blob Storage | 5 GB LRS hot | 12M only |
| Azure Files | 100 GB LRS | 12M only |
| Archive Storage | 10 GB LRS | 12M only |
| Managed Disks | 2 x 64 GB P6 SSD | 12M only |
| Bandwidth | 100 GB outbound | Always |
| Cosmos DB | 1K RU/sec + 25 GB storage | Always |
| Azure SQL | 100K vCore-sec serverless + 32 GB/database (up to 10) | Always |

### AI/ML & Integration

| Resource | Always Free Allowance | Free Period |
|---|---|---|
| Language | 5,000 text records/month | Always |
| Translator | 2 million characters/month | Always |
| Speech-to-Text | 5 audio hours/month | Always |
| Text-to-Speech | 0.5 million characters/month | Always |
| AI Bot Service | 10K premium channel messages + unlimited standard | Always |
| Event Grid | 100,000 operations/month | Always |
| Logic Apps | 4,000 built-in actions (Consumption plan) | Always |

### Security & Identity

| Resource | Always Free Allowance | Free Period |
|---|---|---|
| Key Vault | 10K transactions (RSA 2048) | 12M only |
| Entra ID (Azure AD) | 50,000 stored objects + SSO | Always |
| Security Center | Free policy assessment + recommendations | Always |
| Azure Attestation | Free | Always |
| Azure Policy | Free configuration/change tracking | Always |

### Management & DevOps

| Resource | Always Free Allowance | Free Period |
|---|---|---|
| Azure DevOps | 5 users, unlimited private Git repos | Always |
| Monitor | Free amounts per feature | Always |
| Advisor | Unlimited | Always |
| Automation | 500 minutes job runtime/month | Always |
| Cost Management | Free | Always |
| Cloud Shell | 5 GB Azure Files storage | Always |

### Tranc3 Integration

- **AzureStorageProvider** (priority 6): Limited - Blob Storage is 12M only; Cosmos DB always free
- **Cosmos DB (1K RU/sec + 25 GB)**: Document store for entity metadata, ID registry backup
- **Azure SQL (100K vCore-sec + 32 GB)**: Relational DB for structured data
- **Functions (1M requests)**: Serverless event processing for Tranc3 nanoservices
- **Container Apps**: Lightweight agent/nanoservice hosting
- **Entra ID (50K objects)**: Identity management for multi-user scenarios
- **Azure DevOps (5 users)**: Alternative CI/CD pipeline
- **Event Grid (100K ops)**: Event-driven architecture for agent communication

---

## 4. Amazon Web Services (AWS) - Always Free

AWS provides 30+ always-free services. The always-free tier is distinct from the 12-month free tier. AWS now offers new customers $200 in credits, but credits expire - this does not count as zero-cost.

### Compute

| Resource | Always Free Allowance | Notes |
|---|---|---|
| Lambda | 1M requests + 400K GB-sec/month | Serverless functions |
| Step Functions | 4,000 state transitions/month | Workflow orchestration |
| SWF | 1,000 AWS-hosted domains + 10K tasks | Legacy workflow |

### Storage

| Resource | Always Free Allowance | Notes |
|---|---|---|
| S3 | 5 GB (12-month only) | NOT always free |
| Glacier | 10 GB (12-month only) | NOT always free |
| EBS | 30 GB (12-month only) | NOT always free |

**Important**: AWS does NOT offer always-free object storage. S3, Glacier, and EBS are only free for 12 months. This is a critical limitation for the Tranc3 zero-cost storage strategy.

### Database

| Resource | Always Free Allowance | Notes |
|---|---|---|
| DynamoDB | 25 GB + 25 WCUs + 25 RCUs | NoSQL key-value/document |
| Aurora Serverless | Limited trial | NOT always free |
| SimpleDB | 25 machine hours + 1 GB | Legacy NoSQL |

### Application Integration

| Resource | Always Free Allowance | Notes |
|---|---|---|
| SQS | 1 million requests/month | Message queuing |
| SNS | 1 million publishes + 100K HTTP deliveries | Pub/sub messaging |
| EventBridge | 100M custom events + 3M custom events (bus) | Event routing |
| Cognito | 50,000 MAU | User authentication |
| API Gateway | 1M REST API calls (12-month only) | NOT always free |

### Security

| Resource | Always Free Allowance | Notes |
|---|---|---|
| KMS | 10K requests/month (not CMKs) | Key management |
| Certificate Manager | Free public certificates | SSL/TLS for CloudFront/Elastic LB |
| Shield Standard | Free DDoS protection | Automatic for all AWS customers |
| WAF Bot Control | Free tier available | Bot mitigation |
| CloudTrail | 1 trail + 90 days read-only | API audit logging |

### Networking

| Resource | Always Free Allowance | Notes |
|---|---|---|
| CloudFront | 1 TB egress + 10M requests/month (12-month only) | NOT always free |
| Route 53 | No free tier | DNS only |

### Management & Developer Tools

| Resource | Always Free Allowance | Notes |
|---|---|---|
| CloudWatch | 10 custom metrics + 10 alarms | Monitoring |
| CloudFormation | Free | Infrastructure as Code |
| Systems Manager | Free (parameter store) | Ops management |
| CodePipeline | 1 active pipeline/month | CI/CD |
| CodeBuild | 100 build minutes/month | Build service |
| X-Ray | 100K traces/month | Distributed tracing |
| Managed Prometheus | 40M active time series + 50 GB write | Metrics |

### Tranc3 Integration

- **AWSStorageProvider** (priority 7): Extremely limited - no always-free object storage
- **DynamoDB (25 GB)**: Key-value store for entity data, session tokens
- **Lambda (1M requests)**: Serverless nanoservice execution
- **SQS (1M requests)**: Message queue for agent communication
- **SNS (1M publishes)**: Notification system for alerts
- **EventBridge (100M events)**: Event-driven architecture backbone
- **Cognito (50K MAU)**: User identity/authentication
- **CloudTrail (1 trail)**: API audit logging
- **CloudFormation**: IaC for AWS resource provisioning
- **CloudWatch (10 metrics)**: Basic monitoring
- **Managed Prometheus**: Compatible with existing Prometheus monitoring

**Critical Gap**: AWS has NO always-free object storage. S3/Glacier are 12-month only. For zero-cost cloud storage, OCI (20 GB) and GCP (5 GB) are superior choices. Cloudflare R2 (10 GB) remains the best zero-cost S3-compatible option.

---

## 5. HashiCorp - Source-Available (BSL 1.1)

HashiCorp products are NOT open-source since August 2023. They use the Business Source License (BSL 1.1), which is source-available but restricts competitive use. However, internal/self-hosted use remains free under BSL.

### Product Status

| Product | License | Self-Hosted Free? | Tranc3 Use Case |
|---|---|---|---|
| Terraform | BSL 1.1 (since v1.6+) | Yes (internal use) | Infrastructure as Code |
| Vault | BSL 1.1 (since v1.15+) | Yes (internal use) | Secret management (reference arch) |
| Consul | BSL 1.1 (since v1.17+) | Yes (internal use) | Service mesh / discovery |
| Nomad | BSL 1.1 (since v1.7+) | Yes (internal use) | Workload orchestration |
| Boundary | BSL 1.1 | Yes (internal use) | Access broker / SSH proxy |
| Vagrant | BSL 1.1 | Yes (internal use) | Dev environment management |
| Packer | BSL 1.1 | Yes (internal use) | Image building |
| Waypoint | BSL 1.1 | Yes (internal use) | Application deployment |

### BSL 1.1 Key Provisions for Tranc3

1. **Internal use is always free**: Running HashiCorp products for your own infrastructure, even at enterprise scale, is permitted under BSL at no cost
2. **No competitive hosting**: You cannot offer HashiCorp products as a managed service to third parties
3. **No competitive embedded use**: You cannot embed HashiCorp products in a competitive offering
4. **Source code is visible**: You can inspect, modify, and redistribute under BSL terms
5. **No commercial redistribution**: Modified versions cannot be sold as competing products

### Open-Source Alternatives (FOSS)

Since the BSL license change, the community has created fully open-source forks:

| Product | Open-Source Fork | License | Status |
|---|---|---|---|
| Terraform | **OpenTofu** | MPL 2.0 | CNCF incubating, production-ready, 1.8+ |
| Vault | **OpenBao** | MPL 2.0 | LF Edge project, v2.x in development |
| Consul | **GLHC** (community fork) | MPL 2.0 | Early stage |
| Nomad | No established fork yet | N/A | Still BSL only |
| Boundary | No established fork yet | N/A | Still BSL only |

### Tranc3 Integration

- **OpenTofu** (MPL 2.0): Replace Terraform for IaC. Fully compatible with existing Terraform configurations. Can provision OCI, GCP, Azure, and AWS resources through providers.
- **OpenBao** (MPL 2.0): Replace HashiCorp Vault reference with open-source alternative. Compatible with Vault API for secret management.
- **Terraform/BSL** (internal use): Acceptable for internal IaC since Tranc3 does not offer competitive hosting. However, OpenTofu is preferred for license clarity.
- **Nomad** (BSL): Consider for workload orchestration on OCI Arm A1 instances. Internal use is free.
- **Consul** (BSL): Service mesh for multi-provider networking. Internal use is free.

**Recommendation**: Use OpenTofu over Terraform, and OpenBao over Vault, to maintain full FOSS compliance. The BSL products are acceptable for internal use but the MPL 2.0 forks provide stronger license guarantees and community governance.

---

## Provider Comparison Matrix

### Always-Free Storage (Object)

| Provider | Storage | Egress | S3-Compatible | Suitability |
|---|---|---|---|---|
| Cloudflare R2 | 10 GB | Free (no egress fees) | Yes | Primary cloud storage |
| OCI Object Storage | 20 GB | 10 TB/month | Yes (S3-compatible API) | Secondary cloud storage |
| GCP Cloud Storage | 5 GB | 100 GB/month | No (GCS API) | Tertiary (API translation) |
| Azure Blob Storage | 5 GB (12M only!) | 100 GB/month | Yes (via interop) | NOT always free |
| AWS S3 | 0 GB always-free | N/A | Yes | No always-free tier |

### Always-Free Compute

| Provider | VM/Instance | Serverless | Containers |
|---|---|---|---|
| OCI | 2 AMD Micro + 4 Arm A1 OCPUs | N/A | N/A |
| GCP | 1 e2-micro | Cloud Run (2M req) + Functions (2M) | GKE (1 cluster) |
| Azure | None always-free | Functions (1M) + Container Apps | AKS (mgmt free) |
| AWS | None always-free | Lambda (1M) | N/A |

### Always-Free Database

| Provider | Relational | NoSQL | Cache |
|---|---|---|---|
| OCI | 2 Autonomous DB + 1 MySQL | N/A | N/A |
| GCP | N/A | Firestore (1 GiB) | N/A |
| Azure | SQL (100K vCore-sec) | Cosmos DB (1K RU/sec + 25 GB) | N/A |
| AWS | N/A | DynamoDB (25 GB) | N/A |

### Always-Free Security/Secrets

| Provider | Secret Storage | Key Management | Identity |
|---|---|---|---|
| OCI | 150 Vault secrets | 20 keys (HSM/software) | IAM (free) |
| GCP | 6 Secret Manager versions | 100 KMS key versions | N/A |
| Azure | Key Vault (12M only!) | N/A | Entra ID (50K objects) |
| AWS | Systems Manager Param Store | 10K KMS requests | Cognito (50K MAU) |

---

## Tranc3 Zero-Cost Cloud Architecture

### Updated Storage Priority Chain

The SmartStorageOrchestrator priority chain is extended with new zero-cost cloud providers:

```
Priority 0: ZFS (Primary - TRUE_NAS local storage)
Priority 1: MinIO (Local S3-compatible, self-hosted)
Priority 2: Ceph (Distributed storage, self-hosted)
Priority 3: Cloudflare R2 (10 GB free, S3-compatible)
Priority 4: OCI Object Storage (20 GB free, S3-compatible)
Priority 5: GCP Cloud Storage (5 GB free, GCS API)
Priority 6: Azure Cosmos DB (25 GB free, document API - not S3)
Priority 7: AWS DynamoDB (25 GB free, key-value API - not S3)
```

### Adaptive Provider Selection Logic

```python
# The orchestrator auto-modulates across providers based on:
# 1. Available capacity in each free tier
# 2. Egress bandwidth remaining in monthly quotas
# 3. API compatibility (S3-compatible preferred)
# 4. Latency from TRUE_NAS to provider region
# 5. Data classification (hot/warm/cold/archive)
#
# Only S3-compatible providers (R2, OCI, GCP-via-interop) are used
# for transparent storage operations. Non-S3 providers (Cosmos DB,
# DynamoDB) are used for metadata, entity data, and caching only.
```

### Monthly Quota Monitoring

Each provider enforces monthly quotas. The SmartStorageOrchestrator must track:

| Provider | Metric | Monthly Limit | Monitoring |
|---|---|---|---|
| Cloudflare R2 | Storage | 10 GB | R2 API head bucket |
| Cloudflare R2 | Class A ops | 1M/month | Cloudflare dashboard API |
| Cloudflare R2 | Class B ops | 10M/month | Cloudflare dashboard API |
| OCI | Object Storage | 20 GB | OCI CLI / API |
| OCI | Egress | 10 TB/month | OCI monitoring |
| GCP | Cloud Storage | 5 GB | GCS API |
| GCP | Egress | 100 GB/month | GCP monitoring |
| Azure | Cosmos DB RU | 1K RU/sec | Azure Monitor |
| AWS | DynamoDB | 25 GB + 25 WCU/RCU | CloudWatch |

### Zero-Cost Deployment Strategy

1. **TRUE_NAS Mode (Primary)**: All data lives on local ZFS. Cloud providers are cold backup only.
2. **HYBRID Mode**: Active data on ZFS + MinIO. Cold/archive replicated to R2 + OCI. Metadata cached in GCP Firestore / Azure Cosmos DB.
3. **CLOUD_ONLY Mode**: Active data on R2 + OCI. Compute on OCI Arm A1 + GCP Cloud Run. Metadata in DynamoDB / Cosmos DB. This mode activates only when TRUE_NAS is unavailable.

---

## Implementation Roadmap

### Phase 9B-1: Provider Implementations

| Provider | Implementation | Priority | API Type |
|---|---|---|---|
| OCI | OCISmartProvider (done) | 4 | S3-compatible |
| GCP | GCPStorageProvider | 5 | GCS (google-cloud-storage) |
| Azure | AzureCosmosProvider | 6 | Cosmos DB (azure-cosmos) |
| AWS | AWSDynamoProvider | 7 | DynamoDB (boto3) |

### Phase 9B-2: Infrastructure as Code

| Tool | Purpose | License |
|---|---|---|
| OpenTofu | Provision all cloud resources | MPL 2.0 |
| OCI Resource Manager | Managed Terraform for OCI | Free (500 jobs/month) |
| CloudFormation | AWS resource provisioning | Free |
| Pulumi (optional) | Multi-cloud IaC with Python | Apache 2.0 (core) |

### Phase 9B-3: Monitoring & Auto-Modulation

- Extend SmartStorageOrchestrator with quota-aware provider selection
- Add monthly quota tracking per provider
- Implement automatic provider failover when quotas approach limits
- Add Prometheus metrics for each cloud provider's quota utilization
- Alert when any provider exceeds 80% of monthly free-tier limits

---

## Risk Assessment

### Account Risk

- **OCI**: Free-tier accounts can be reclaimed if inactive. OCI may delete idle compute instances after 7 days of inactivity. Mitigation: Run a lightweight health-check agent on Arm A1 instances.
- **GCP**: Free tier has no inactivity policy, but Google reserves 30-day change notice. Mitigation: Multi-provider strategy prevents single-provider dependency.
- **Azure**: 12-month free services expire. Always-free services are stable but limited. Mitigation: Only rely on "Always" services for zero-cost architecture.
- **AWS**: No always-free object storage is a critical gap. 12-month free services create a false sense of zero-cost. Mitigation: Use AWS only for DynamoDB, Lambda, and messaging - never for storage.

### License Risk

- **HashiCorp BSL**: Acceptable for internal use but not FOSS. OpenTofu and OpenBao are the recommended alternatives. Mitigation: Use MPL 2.0 forks where available.
- **MinIO AGPL**: Maintenance-only since Dec 2025. Future versions may have further restrictions. Mitigation: Monitor SeaweedFS/Garage as alternatives.

### Data Risk

- **Multi-cloud data dispersal**: Data spread across multiple providers increases attack surface. Mitigation: Encryption at rest and in transit for all providers. HSM-bound keys never leave the vault.
- **Provider lock-in**: Using provider-specific APIs (Cosmos DB, DynamoDB) creates migration friction. Mitigation: Use abstraction layer in SmartStorageOrchestrator. S3-compatible providers preferred.

---

## References

- OCI Always Free: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm
- GCP Free Tier: https://cloud.google.com/free/docs/free-cloud-features
- Azure Free Services: https://azure.microsoft.com/en-us/pricing/free-services
- AWS Free Tier: https://aws.amazon.com/free
- HashiCorp Open Source: https://www.hashicorp.com/en/about/open-source
- HashiCorp License FAQ: https://www.hashicorp.com/license-faq
- OpenTofu: https://opentofu.org
- OpenBao: https://openbao.org
- Cloudflare R2 Pricing: https://developers.cloudflare.com/r2/pricing
- ExchangeKB Free Tier Comparison: https://exchangekb.com/2024/11/15/comparing-the-free-forever-tiers-in-azure-gcp-aws-and-oci

*Research synthesized from official provider documentation, pricing pages, and community resources. All data verified as of 2025-06.*
