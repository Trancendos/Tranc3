# Oracle Cloud Always Free — Trancendos Production Deployment

Oracle Cloud Infrastructure (OCI) Always Free Tier: **zero cost, forever**.

## Free Resources Available

| Resource | Spec | Notes |
|----------|------|-------|
| Ampere A1 Compute | 4 OCPU + 24 GB RAM | ARM64 — runs all Docker services |
| Block Storage | 200 GB total | For volumes |
| Networking | 10 TB egress/month | More than enough |
| Load Balancer | 1× flexible (10 Mbps) | Free forever |
| Object Storage | 20 GB | For IPFS/artifacts |
| Autonomous Database | 2× 20 GB | Optional — use instead of self-hosted Postgres |

The 4 OCPU / 24 GB ARM instance easily runs the entire Trancendos stack
(tranc3-net stack = ~8 GB peak RAM on a production workload).

## Quick Setup

```bash
# 1. Create OCI account at cloud.oracle.com (no credit card billing if Always Free)
# 2. Create an Ampere A1 instance:
#    - Shape: VM.Standard.A1.Flex  (up to 4 OCPU / 24 GB)
#    - Image: Oracle Linux 9 or Ubuntu 22.04
#    - Boot volume: 50 GB (free)
#    - Block volume: 150 GB additional (free, attach as /dev/sdb)

# 3. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 4. Install Docker Compose
sudo apt-get install -y docker-compose-plugin  # Ubuntu
# or
sudo dnf install -y docker-compose-plugin       # Oracle Linux

# 5. Format and mount the block volume
sudo mkfs.ext4 /dev/sdb
sudo mkdir -p /mnt/tranc3-data
echo "/dev/sdb /mnt/tranc3-data ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a

# 6. Clone repo and configure
git clone https://github.com/Trancendos/Tranc3 /mnt/tranc3-data/app
cd /mnt/tranc3-data/app
cp .env.example .env
# Edit .env with production secrets

# 7. Deploy
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
```

## OCI CLI Configuration (for automation)

```bash
# Install OCI CLI
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"

# Configure (run interactively)
oci setup config

# List instances
oci compute instance list --compartment-id $OCI_COMPARTMENT_ID

# SSH into instance
oci compute instance-console-connection create --instance-id $INSTANCE_ID
```

## Environment Variables (add to .env)

```bash
# OCI Credentials (optional — only needed for CLI automation)
OCI_CLI_USER=ocid1.user.oc1..xxx
OCI_CLI_TENANCY=ocid1.tenancy.oc1..xxx
OCI_CLI_FINGERPRINT=xx:xx:xx:...
OCI_CLI_KEY_FILE=~/.oci/oci_api_key.pem
OCI_CLI_REGION=uk-london-1   # or eu-frankfurt-1, us-ashburn-1

# OCI Object Storage (replaces local file storage if desired)
OCI_OBJECT_STORAGE_NAMESPACE=your-namespace
OCI_OBJECT_STORAGE_BUCKET=tranc3-artifacts
```

## Resource Sizing Recommendations

With 4 OCPU / 24 GB RAM, recommended resource allocations:

| Service Group | OCPU | RAM |
|---|---|---|
| P0 workers (tranc3-ai, api-gateway, infinity-ws, infinity-auth) | 1.0 | 4 GB |
| P1 workers (users, monitoring, notifications, infinity-ai) | 0.5 | 2 GB |
| Infrastructure (Traefik, NATS, Valkey, Qdrant) | 0.5 | 3 GB |
| Observability (Prometheus, Grafana, VictoriaMetrics, Loki) | 0.5 | 4 GB |
| Databases (Postgres, pgvector) | 0.5 | 3 GB |
| AI (Ollama with llama3.2:1b) | 1.0 | 6 GB |
| **Total** | **4.0** | **22 GB** |

## Networking

- Open ports 80, 443 (Traefik TLS) in OCI Security List
- Open port 4222 (NATS) internally only
- Traefik handles all TLS via Let's Encrypt

## Cost

**$0/month** — Oracle Cloud Always Free resources never expire and are never charged.
