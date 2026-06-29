# OCI Citadel — Provisioning Guide

Step-by-step guide to bring up the Tranc3 Citadel on OCI Always Free ARM.
Everything here is zero-cost. No paid services.

---

## What gets provisioned

- **1× VM.Standard.A1.Flex** — 4 OCPU, 24 GB RAM, 100 GB boot volume (Citadel)
- **Reserved public IP** — stable across reboots/recreations
- **VCN + subnets** — public (10.0.1.0/24), private (10.0.2.0/24), ceph (10.0.3.0/24)
- **OCI Object Storage** — hot / cold / archive buckets (20 GB total free)
- **OCI KMS Vault** — secrets management (150 secrets free)
- **Cloudflare DNS** — A record pointing trancendos.com → Citadel public IP
- **Cloud-init bootstrap** — installs Docker, Traefik, Vault, Prometheus/Grafana, all 80+ workers

> The ancillary instances (nanoservice, ceph_node, k3s_edge) are set to 0 OCPU/RAM
> in `terraform.tfvars`. The Citadel uses the entire A1 allocation.

---

## Prerequisites (one-time, ~10 minutes)

### 1. Install Terraform

```bash
# macOS
brew install terraform

# Linux (Ubuntu/Debian)
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# Windows
choco install terraform
```

Verify: `terraform --version` (need >= 1.6.0)

### 2. Create OCI Account

Go to https://www.oracle.com/cloud/free/ and sign up.
- Choose your home region (e.g. `uk-london-1`) — **cannot be changed later**
- Credit card required for verification but you will NOT be charged
- Always Free resources never expire

### 3. Generate OCI API Key

In the OCI Console:
1. Click your profile avatar (top-right) → **My Profile**
2. Scroll down → **API Keys** → **Add API Key**
3. Choose **Generate API Key Pair**
4. Download the **private key** → save as `~/.oci/oci_api_key.pem`
5. Copy the **fingerprint** shown (format: `xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx`)
6. Click **Close** — the config preview shown is not needed

```bash
# Lock down the key file permissions
chmod 600 ~/.oci/oci_api_key.pem
```

### 4. Collect your OCIDs

| Value | Where to find it |
|---|---|
| **Tenancy OCID** | Profile avatar → **Tenancy: \<name\>** → click tenancy name → copy OCID |
| **User OCID** | Profile avatar → **My Profile** → copy OCID |
| **Compartment OCID** | Identity & Security → Compartments → your compartment → copy OCID |
| | *(Use tenancy OCID here if using the root compartment)* |
| **Region** | Administration → Region Management → Home Region identifier |
| | Common: `uk-london-1`, `us-ashburn-1`, `eu-frankfurt-1`, `ap-sydney-1` |

### 5. Collect Cloudflare credentials

| Value | Where to find it |
|---|---|
| **Zone ID** | Cloudflare dashboard → trancendos.com → Overview → right sidebar → Zone ID |
| **API Token** | My Profile → API Tokens → Create Token → "Edit zone DNS" template → restrict to Zone: trancendos.com |

### 6. Generate SSH key for Citadel

```bash
ssh-keygen -t ed25519 -C "tranc3-citadel" -f ~/.ssh/tranc3_citadel
# Press Enter twice (no passphrase, or add one for extra security)
cat ~/.ssh/tranc3_citadel.pub
# Copy the full output — needed in terraform.tfvars
```

---

## Provisioning (~5 minutes)

### Step 1 — Create your tfvars file

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — fill in every value marked with `XXXX`:

```hcl
# Section 1 — OCI Authentication
oci_tenancy_ocid     = "ocid1.tenancy.oc1..aaa..."      # from step 4
oci_user_ocid        = "ocid1.user.oc1..aaa..."          # from step 4
oci_fingerprint      = "xx:xx:xx:xx:xx:xx:xx:xx:..."     # from step 3
oci_private_key_path = "~/.oci/oci_api_key.pem"          # from step 3
oci_region           = "uk-london-1"                      # your home region
oci_compartment_ocid = "ocid1.compartment.oc1..aaa..."   # from step 4

# Section 2 — Citadel (uses full A1 allocation)
citadel_ocpus           = 4
citadel_memory_gbs      = 24
citadel_boot_volume_gbs = 100

# Section 5 — Cloudflare DNS
cloudflare_zone_id   = "your-32-char-zone-id"
cloudflare_api_token = "your-cloudflare-api-token"

# Section 7 — SSH
ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAA... tranc3-citadel"

# Section 8 — Idle defense (prevents OCI reclaiming idle instances)
idle_defense_enabled                = true
idle_defense_burst_cron             = "*/5 * * * *"
idle_defense_burst_duration_seconds = 30
idle_defense_cpu_target_percent     = 25

# Ancillary nodes — MUST be 0 when Citadel is active
nanoservice_ocpus      = 0
nanoservice_memory_gbs = 0
ceph_node_ocpus        = 0
ceph_node_memory_gbs   = 0
k3s_edge_ocpus         = 0
k3s_edge_memory_gbs    = 0
```

> `terraform.tfvars` is in `.gitignore` — it will never be committed.

### Step 2 — Initialise Terraform

```bash
cd deploy/terraform
terraform init
```

Downloads the OCI and Cloudflare providers (~200 MB, one-time).

### Step 3 — Preview the plan

```bash
terraform plan
```

Review what will be created. Should show ~20-25 resources, all free tier.
No charges. If anything looks wrong, fix `terraform.tfvars` before proceeding.

### Step 4 — Apply

```bash
terraform apply
```

Type `yes` when prompted. Takes ~5-10 minutes.

When complete, Terraform prints outputs including:
- `citadel_public_ip` — the Citadel's IP address
- `citadel_ssh_command` — ready-to-run SSH command

### Step 5 — Monitor cloud-init bootstrap

SSH in and watch the bootstrap:

```bash
# Use the SSH command from terraform output, or:
ssh -i ~/.ssh/tranc3_citadel ubuntu@<citadel_public_ip>

# Watch bootstrap progress
sudo tail -f /var/log/cloud-init-output.log
```

Bootstrap installs: Docker, docker-compose, all workers, Traefik, Vault, Prometheus, Grafana, Forgejo runner.
Takes ~10-15 minutes on first boot.

### Step 6 — Verify services

```bash
# On the Citadel:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | sort

# Check Traefik dashboard (from your machine, with your IP in admin_cidr_block):
curl http://<citadel_public_ip>:8080/dashboard/

# Check backend health:
curl http://<citadel_public_ip>:8000/health
```

---

## Post-provisioning

### Unseal Vault (The Void)

On first boot, Vault is initialised but sealed. Run:

```bash
ssh -i ~/.ssh/tranc3_citadel ubuntu@<citadel_public_ip>
cd /opt/tranc3
./deploy/vault/init-citadel.sh
```

Save the unseal keys and root token in a secure location (password manager).

### Set application secrets

```bash
# On Citadel, set secrets in Vault (The Void):
vault kv put secret/tranc3 \
  SECRET_KEY="$(openssl rand -hex 32)" \
  JWT_SECRET="$(openssl rand -hex 32)" \
  DATABASE_URL="your-db-url" \
  REDIS_URL="your-redis-url"
```

### Point DNS

Terraform automatically creates the Cloudflare A record for `trancendos.com`.
Propagation takes 1-5 minutes. Verify with:

```bash
dig +short trancendos.com
# Should return the citadel_public_ip
```

### Set up Forgejo runner

The Forgejo act-runner is installed by cloud-init. Register it:

```bash
ssh -i ~/.ssh/tranc3_citadel ubuntu@<citadel_public_ip>
cd /opt/tranc3
./deploy/forgejo/runner-setup.sh
```

This connects the Citadel as a self-hosted runner for The Workshop (CI/CD).

---

## Idle defense

OCI reclaims Always Free instances idle for 7 consecutive days (CPU < 20%).
The idle defense cron (configured in tfvars) runs every 5 minutes and generates
a 30-second CPU burst at ~25% load to prevent reclamation.

Check it's running:
```bash
systemctl status tranc3-idle-defense
# or
crontab -l
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `terraform apply` fails: "Out of host capacity" | OCI ARM capacity varies by region/AD. Try a different availability domain or region. |
| `terraform apply` fails: "Limit exceeded" | You may have existing A1 instances using the allocation. Check OCI Console → Compute → Instances. |
| SSH times out | Check NSG rules in OCI Console. Citadel NSG should allow TCP 22 inbound. |
| Cloud-init never finishes | `sudo journalctl -u cloud-init -f` for detailed logs. |
| Workers not starting | `docker-compose -f /opt/tranc3/docker-compose.production.yml logs --tail=50` |
| DNS not resolving | Check Cloudflare dashboard — A record should exist for trancendos.com pointing to citadel IP. |

---

## Destroying (if needed)

> `prevent_destroy = true` is set on compute instances to protect against accidental deletion.
> To destroy, first remove `prevent_destroy` from `oci-citadel.tf`, then:

```bash
terraform destroy
```

This removes all OCI resources but does NOT delete local SSH keys or `terraform.tfvars`.
