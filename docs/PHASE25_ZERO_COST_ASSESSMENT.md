# TRANC3 INFINITY — Phase 25: Zero-Cost Infrastructure Assessment

## Container/Podman vs Terraform/GitHub — Comparative Analysis

This document provides a comprehensive assessment of infrastructure deployment strategies for the Tranc3 Infinity Ecosystem, evaluating Container/Podman approaches against Terraform/GitHub-based provisioning, all within the zero-cost constraint model.

---

## 1. Executive Summary

The Tranc3 Infinity Ecosystem currently operates under a strict zero-cost mandate: all infrastructure, tooling, and deployment must use free-tier services and open-source software. The two primary infrastructure strategies under consideration are:

1. **Container/Podman Stack** — Rootless container orchestration with Podman Compose, running on Oracle Cloud Always Free compute
2. **Terraform/GitHub Stack** — Infrastructure-as-Code with Terraform/OpenTofu, provisioned via GitHub Actions CI/CD on free-tier runners

**Recommendation**: Adopt a hybrid approach. Use Terraform/OpenTofu for infrastructure provisioning (network, compute, storage) and Podman for container runtime on the provisioned hosts. GitHub Actions provides the CI/CD glue at zero cost for public repositories.

---

## 2. Current Infrastructure State

### 2.1 Existing Terraform Configuration

The Tranc3 repo already contains a Terraform root module (`deploy/terraform/`) that provisions:

| Resource | Provider | Free Tier |
|---|---|---|
| 4 OCPU Arm (A1 Flex) | Oracle Cloud | Always Free |
| 2 Micro AMD compute | Oracle Cloud | Always Free |
| 200 GB Block Volume | Oracle Cloud | Always Free |
| 20 GB Object Storage | Oracle Cloud | Always Free |
| 10 TB outbound/month | Oracle Cloud | Always Free |
| DNS/CDN | Cloudflare | Free Tier |
| TLS Certificates | Cloudflare | Free Tier |

Terraform providers: `oracle/oci`, `cloudflare/cloudflare`, `hashicorp/random`, `hashicorp/tls`, `hashicorp/local`

### 2.2 Existing Docker Compose Configuration

The Tranc3 repo also contains Docker Compose files (`docker-compose.yml`, `docker-compose.production.yml`, `docker-compose.storage.yml`, `docker-compose.self-hosted.yml`) defining:

- **api** service (Python FastAPI)
- **web** service (nginx frontend)
- **redis** service (Redis 7 Alpine)
- **otel-collector** service (OpenTelemetry)
- Additional production services (PostgreSQL, monitoring, etc.)

### 2.3 Existing GitHub Actions CI/CD

Phase 24 added three CI/CD pipelines:
- `.github/workflows/rust.yml` — Rust check, test, maturin-build
- `.github/workflows/go.yml` — Go lint, build, test with protobuf
- `.github/workflows/python.yml` — Python lint (ruff), test (3.10/3.11/3.12), coverage

---

## 3. Strategy A: Container/Podman Stack

### 3.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Oracle Cloud Always Free                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │               A1 Flex (4 OCPU Arm, 24GB RAM)         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │  │
│  │  │ Podman   │  │ Podman   │  │ Podman   │           │  │
│  │  │ K3s Pod  │  │ AeonMind │  │ Tranc3   │           │  │
│  │  │ (control)│  │ gRPC Go  │  │ API Pod  │           │  │
│  │  └──────────┘  └──────────┘  └──────────┘           │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │  │
│  │  │ Podman   │  │ Podman   │  │ Podman   │           │  │
│  │  │ Redis    │  │ OTel     │  │ Workers  │           │  │
│  │  │ Pod      │  │ Pod      │  │ Pod(s)   │           │  │
│  │  └──────────┘  └──────────┘  └──────────┘           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Podman Advantages for Zero-Cost Model

| Feature | Podman | Docker |
|---|---|---|
| **Rootless execution** | ✅ Native | ❌ Requires root daemon |
| **No daemon** | ✅ Fork-exec model | ❌ Docker daemon required |
| **systemd integration** | ✅ `podman generate systemd` | ❌ Requires separate setup |
| **Pods (K8s-like)** | ✅ Native pod concept | ❌ Requires Kubernetes |
| **Docker Compose compat** | ✅ `podman-compose` | ✅ Native |
| **Kubernetes YAML** | ✅ `podman generate kube` | ❌ Not available |
| **Free desktop** | ✅ Fully open source | ⚠️ Docker Desktop license |
| **Security** | ✅ Rootless + SELinux | ⚠️ Daemon attack surface |
| **Image compat** | ✅ OCI standard | ✅ OCI standard |
| **Resource usage** | ✅ Lower overhead | ⚠️ Daemon overhead |

### 3.3 Podman Deployment Workflow

```bash
# 1. Build images on Oracle Cloud A1 (Arm64)
podman build -t tranc3-api:latest -f docker/Dockerfile.api .
podman build -t tranc3-web:latest -f docker/Dockerfile.web .

# 2. Create a pod (shared network namespace)
podman pod create --name tranc3 -p 8000:8000 -p 3000:3000

# 3. Run services in the pod
podman run -d --pod tranc3 --name api tranc3-api:latest
podman run -d --pod tranc3 --name web tranc3-web:latest
podman run -d --pod tranc3 --name redis redis:7-alpine

# 4. Generate systemd units for persistence
podman generate systemd --name --files --restart-policy=always api

# 5. Generate Kubernetes YAML for K3s migration
podman generate kube tranc3 > tranc3-pod.yaml
```

### 3.4 Podman Cost Analysis

| Item | Cost | Notes |
|---|---|---|
| Podman CLI | **$0** | Open source, Red Hat sponsored |
| podman-compose | **$0** | pip install podman-compose |
| Oracle Cloud A1 (host) | **$0** | Always Free tier |
| Container images | **$0** | All from public registries |
| systemd service mgmt | **$0** | Built into Oracle Linux |
| K3s orchestration | **$0** | CNCF certified Kubernetes |
| **Total** | **$0/month** | Zero-cost achieved |

---

## 4. Strategy B: Terraform/GitHub Stack

### 4.1 Architecture

```
┌──────────────┐    ┌──────────────┐    ┌────────────────────────┐
│ GitHub Repo  │───▶│ GitHub       │───▶│ Terraform/OpenTofu     │
│ (Tranc3)     │    │ Actions      │    │ Apply to Oracle Cloud  │
│              │    │ (CI/CD)      │    │ + Cloudflare           │
└──────────────┘    └──────────────┘    └────────────────────────┘
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │ GitHub       │
       │            │ Runners      │
       │            │ (free tier)  │
       │            └──────────────┘
       │
       ▼
┌──────────────┐
│ GitHub Pages │
│ (docs site)  │
└──────────────┘
```

### 4.2 GitHub Actions Free Tier Analysis

| Plan | Private Minutes | Public Minutes | Storage |
|---|---|---|---|
| **GitHub Free** | 2,000 min/month | Unlimited | 500 MB |
| **GitHub Pro** | 3,000 min/month | Unlimited | 1 GB |
| **GitHub Team** | 3,000 min/month | Unlimited | 2 GB |

**For the Trancendos organization (51 repos, all public):**
- ✅ **Unlimited** GitHub Actions minutes for all public repositories
- ✅ **Free** GitHub-hosted runners (ubuntu-latest, windows-latest, macos-latest)
- ✅ **Free** GitHub Pages for documentation
- ✅ **Free** GitHub Packages (container registry, npm registry)
- ✅ **Free** GitHub Codespaces (120 core-hours/month)

### 4.3 Terraform vs OpenTofu

| Feature | Terraform | OpenTofu |
|---|---|---|
| **License** | BSL 1.1 (non-open since 1.7) | MPL 2.0 (fully open) |
| **Cost** | Free CLI / Paid Cloud | Free CLI / No paid cloud |
| **State backend** | Local, S3, OCI, Cloud | Local, S3, OCI, Cloud |
| **Provider compat** | All providers | All providers (registry compat) |
| **GitHub Actions** | `hashicorp/setup-terraform` | `opentofu/setup-tofu` |
| **Community** | Larger | Growing (Linux Foundation) |
| **Zero-cost** | ✅ CLI is free | ✅ Fully free |

**Recommendation**: Use **OpenTofu** for zero-cost purity (fully open-source MPL 2.0 license), with Terraform as a fallback if any provider compatibility issues arise.

### 4.4 GitHub Actions CI/CD Pipeline for Infrastructure

```yaml
# .github/workflows/infrastructure.yml
name: Infrastructure
on:
  push:
    paths: ['deploy/terraform/**']
    branches: [main]

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: opentofu/setup-tofu@v1
      - run: tofu init
        working-directory: deploy/terraform
      - run: tofu plan
        working-directory: deploy/terraform

  apply:
    needs: plan
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: opentofu/setup-tofu@v1
      - run: tofu apply -auto-approve
        working-directory: deploy/terraform
```

### 4.5 Terraform/GitHub Cost Analysis

| Item | Cost | Notes |
|---|---|---|
| GitHub Actions (public) | **$0** | Unlimited minutes |
| GitHub-hosted runners | **$0** | ubuntu-latest included |
| OpenTofu CLI | **$0** | MPL 2.0 open source |
| Oracle Cloud resources | **$0** | Always Free tier |
| Cloudflare DNS/CDN | **$0** | Free tier |
| GitHub Container Registry | **$0** | ghcr.io for public images |
| GitHub Pages | **$0** | Static site hosting |
| **Total** | **$0/month** | Zero-cost achieved |

---

## 5. Comparative Matrix

### 5.1 Feature Comparison

| Dimension | Container/Podman | Terraform/GitHub | Hybrid (Recommended) |
|---|---|---|---|
| **Infrastructure provisioning** | Manual | Automated IaC | ✅ Terraform/OpenTofu |
| **Container runtime** | ✅ Podman (rootless) | N/A | ✅ Podman (rootless) |
| **CI/CD** | Manual/scripts | ✅ GitHub Actions | ✅ GitHub Actions |
| **Reproducibility** | Low | ✅ High (IaC) | ✅ High (IaC + containers) |
| **State management** | Ad-hoc | ✅ Terraform state | ✅ Terraform state |
| **Rollback** | Manual | ✅ `tofu apply` previous | ✅ Both mechanisms |
| **Security** | ✅ Rootless | Standard | ✅ Rootless + IaC audit |
| **K8s migration** | ✅ podman generate kube | Separate manifests | ✅ Pod → K3s YAML |
| **Zero-cost** | ✅ | ✅ | ✅ |
| **Operational complexity** | Low | Medium | Medium |
| **Audit trail** | Limited | ✅ Git-based IaC | ✅ Git-based IaC |

### 5.2 Suitability for Tranc3 Components

| Component | Best Strategy | Rationale |
|---|---|---|
| Oracle Cloud VCN, compute | Terraform/OpenTofu | Stateful resource with dependencies |
| Cloudflare DNS/CDN | Terraform/OpenTofu | External provider integration |
| K3s cluster bootstrap | Terraform + cloud-init | Infra + init script synergy |
| Tranc3 API container | Podman/K3s | Application workload |
| AeonMind gRPC server | Podman/K3s | Application workload |
| Redis, PostgreSQL | Podman/K3s (stateful sets) | Database workloads |
| CI/CD pipelines | GitHub Actions | Free for public repos |
| WASM edge deployment | Cloudflare Workers | Free tier (100K req/day) |
| Monitoring (OTel) | Podman/K3s sidecar | Observability stack |

---

## 6. Recommended Hybrid Architecture

### 6.1 The Zero-Cost Tranc3 Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                      ZERO-COST TRANC3 STACK                     │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐    │
│  │ GitHub      │  │ OpenTofu     │  │ Oracle Cloud         │    │
│  │ Actions     │  │ (IaC)        │  │ Always Free          │    │
│  │ (CI/CD)     │──│ (provision)  │──│ (4 OCPU + 24GB)     │    │
│  │ Free: ∞     │  │ Free: MPL2.0 │  │ Free: Always        │    │
│  └──────┬──────┘  └──────────────┘  └───────────┬─────────┘    │
│         │                                        │               │
│         │  ┌──────────────┐  ┌──────────────┐    │               │
│         │  │ Podman       │  │ K3s          │    │               │
│         └─▶│ (runtime)    │──│ (orchestrate)│◀───┘               │
│            │ Free: GPLv3  │  │ Free: Apache2│                    │
│            └──────┬───────┘  └──────────────┘                    │
│                   │                                               │
│  ┌────────────┐   │   ┌──────────────┐  ┌──────────────────┐   │
│  │ Cloudflare │   │   │ AeonMind     │  │ Tranc3 Services  │   │
│  │ (CDN/DNS)  │◀──┘───│ gRPC (Go)    │  │ API + Workers    │   │
│  │ Free tier  │       │ Free: MIT    │  │ Free: MIT/Apache │   │
│  └────────────┘       └──────────────┘  └──────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ WASM Edge Layer                                         │    │
│  │ Cloudflare Workers (Free: 100K req/day)                  │    │
│  │ AeonMind WASM agents deployed to edge                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Deployment Flow

1. **Provision** — OpenTofu creates Oracle Cloud VCN, compute instances, Cloudflare DNS records
2. **Bootstrap** — cloud-init installs Podman, K3s, and registers with AeonMind gRPC orchestrator
3. **Build** — GitHub Actions builds OCI container images and pushes to ghcr.io
4. **Deploy** — K3s pulls images from ghcr.io and schedules pods
5. **Route** — Cloudflare Tunnel (free) routes traffic to K3s ingress
6. **Monitor** — OpenTelemetry collects metrics, logs, traces
7. **Edge** — AeonMind WASM agents deploy to Cloudflare Workers for edge inference

### 6.3 Cost Summary

| Service | Provider | Tier | Monthly Cost |
|---|---|---|---|
| Compute (4 OCPU Arm + 24GB) | Oracle Cloud | Always Free | **$0** |
| Compute (2 Micro AMD) | Oracle Cloud | Always Free | **$0** |
| Block Storage (200 GB) | Oracle Cloud | Always Free | **$0** |
| Object Storage (20 GB) | Oracle Cloud | Always Free | **$0** |
| Egress (10 TB/month) | Oracle Cloud | Always Free | **$0** |
| DNS + CDN | Cloudflare | Free | **$0** |
| TLS Certificates | Cloudflare | Free | **$0** |
| Tunnel (cloudflared) | Cloudflare | Free | **$0** |
| CI/CD (unlimited) | GitHub Actions | Public Free | **$0** |
| Container Registry | ghcr.io | Public Free | **$0** |
| Static Hosting | GitHub Pages | Free | **$0** |
| Edge Workers | Cloudflare Workers | Free (100K/day) | **$0** |
| K3s Orchestration | K3s | Open Source | **$0** |
| Container Runtime | Podman | Open Source | **$0** |
| IaC Engine | OpenTofu | Open Source | **$0** |
| **TOTAL** | | | **$0/month** |

---

## 7. Migration Path

### Phase A: OpenTofu Adoption (1-2 days)
- Replace `hashicorp/terraform` with `opentofu` in CI/CD
- Update `deploy/terraform/` to use OpenTofu provider registry
- Migrate state to Oracle Cloud Object Storage backend

### Phase B: Podman Runtime (2-3 days)
- Install Podman on Oracle Cloud A1 instances
- Convert `docker-compose.yml` to `podman-compose` or Kubernetes manifests
- Generate systemd units for service persistence
- Test all services under Podman (rootless)

### Phase C: K3s Integration (3-5 days)
- Bootstrap K3s cluster on Oracle Cloud A1
- Deploy Tranc3 services as K3s pods
- Configure Cloudflare Tunnel for ingress
- Deploy AeonMind gRPC orchestrator

### Phase D: GitHub Actions Pipeline (2-3 days)
- Add infrastructure pipeline (`infrastructure.yml`)
- Add container build + push pipeline
- Add deployment pipeline (K3s rollout)
- Propagate CI/CD to all 51 repos

### Phase E: Edge Deployment (1-2 days)
- Build AeonMind WASM for Cloudflare Workers
- Deploy sentinel-ai and iris-ai as edge workers
- Configure AeonMind gRPC ↔ Cloudflare Workers bridge

---

## 8. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Oracle Cloud changes free tier | Low | Critical | Terraform IaC enables rapid migration |
| GitHub Actions limits change | Low | Medium | Self-hosted runner on Oracle Cloud |
| Podman compatibility issues | Medium | Low | Docker fallback path available |
| OpenTofu provider lag | Low | Medium | Terraform binary as fallback |
| Cloudflare Workers limits hit | Medium | Low | Scale to Oracle Cloud compute |
| A1 Flex capacity unavailable | Medium | High | Pre-allocate with Terraform, use micro AMD |

---

## 9. Conclusion

The Container/Podman vs Terraform/GitHub question presents a false dichotomy for the Tranc3 Infinity Ecosystem. The optimal zero-cost architecture combines both:

- **Terraform/OpenTofu** handles infrastructure provisioning (compute, network, storage, DNS)
- **Podman/K3s** handles container runtime and orchestration on provisioned infrastructure
- **GitHub Actions** provides the CI/CD glue, free for all 51 public repositories
- **Cloudflare** provides DNS, CDN, TLS, tunneling, and edge worker deployment
- **Oracle Cloud Always Free** provides the compute, storage, and network foundation

This hybrid approach achieves the zero-cost mandate while maximizing reproducibility, security (rootless Podman), and operational flexibility (IaC + container orchestration). The existing Terraform configuration in the Tranc3 repo provides a solid foundation, and the Phase 24 AeonMind gRPC orchestrator serves as the natural service mesh for the 51-repo ecosystem.
