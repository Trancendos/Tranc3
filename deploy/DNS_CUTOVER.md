# Tranc3 — DNS Cutover Procedure
> Zero-downtime DNS migration: Cloudflare Workers → self-hosted Citadel

Run this procedure **after** `./scripts/provision-citadel.sh --status` confirms all
P0/P1 workers healthy and Traefik is issuing TLS certificates.

---

## Pre-Cutover Checklist

Complete every item before changing DNS. Failed checks = abort and fix.

### 1. Citadel health (run from your workstation)

```bash
CITADEL_IP=$(cd deploy/terraform && terraform output -raw citadel_public_ip)

# All P0/P1 workers must return HTTP 200
for port in 8000 8004 8005 8006 8007 8040 8042 8043 8044 8060 8070; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    "http://${CITADEL_IP}:${port}/health" 2>/dev/null || echo "000")
  [[ "$code" == "200" ]] && echo "✔ :${port}/health" || echo "✘ :${port}/health → ${code}"
done
```

### 2. Traefik is running and processing requests

```bash
# Traefik dashboard should return 200 (from admin IP)
curl -s -o /dev/null -w '%{http_code}' "http://${CITADEL_IP}:8888/dashboard/" || echo "FAIL"

# Traefik should be listening on 80 and 443
ssh tranc3@${CITADEL_IP} 'ss -tlnp | grep -E ":80 |:443 "'
```

### 3. TLS certificate is issued

Traefik must have obtained a Let's Encrypt certificate before DNS cutover.
Because the Cloudflare proxy is still active, you cannot use HTTP-01 challenge
yet. Use the staging check first:

```bash
# Check Traefik has a certificate for the domain
ssh tranc3@${CITADEL_IP} \
  'cat /opt/tranc3/deploy/traefik/data/acme.json 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
for r,v in data.items():
  for cert in v.get(\"Certificates\",[]):
    print(r, cert[\"domain\"][\"main\"])
" || echo "No certificates yet — DNS must resolve to Citadel IP first"'
```

> **Note:** Traefik issues the certificate via HTTP-01 ACME challenge *after*
> DNS points at Citadel with `proxied=false`. The certificate appears within
> ~60 seconds of a valid DNS resolution.

### 4. Existing Cloudflare Worker routes

Note which CF Worker routes are still active (to remove them post-cutover):

```bash
# List active CF Worker routes (requires wrangler auth)
cd cloudflare/trancendos-api-gateway && npx wrangler routes list 2>/dev/null || true
```

---

## Cutover Strategy: Blue/Green DNS Swap

The strategy is a single atomic DNS swap with a short TTL period, allowing
immediate rollback by re-enabling the Cloudflare proxy.

| Phase | Traffic goes to | Rollback time |
|-------|----------------|---------------|
| Before | Cloudflare Workers (orange cloud) | N/A |
| During (TTL window) | Split: some CF, some Citadel | Instant CF re-enable |
| After | Citadel direct (grey cloud) | Disable CF proxy = instant rollback |

---

## Step-by-Step Cutover

### Step 1: Lower DNS TTL (30 minutes before cutover)

Cloudflare's minimum TTL for proxied records is 1 second. For un-proxied
records (grey cloud), minimum is 60 seconds. Lower TTL now so propagation
is fast at swap time.

**Terraform (preferred — apply the oci-citadel-dns.tf records):**

```bash
cd deploy/terraform
terraform apply -target=cloudflare_record.apex \
                -target=cloudflare_record.www \
                -target=cloudflare_record.api \
                -target=cloudflare_record.the_workshop
```

**Manual via Cloudflare dashboard (alternative):**

1. Cloudflare Dashboard → trancendos.com → DNS → Records
2. For each A record (`trancendos.com`, `www`, `api`):
   - Click Edit → set TTL to **Auto** (60s when un-proxied)

### Step 2: Disable Cloudflare proxy (orange → grey cloud)

> This is the point of no return for the traffic shift.
> Requests will flow directly to Citadel.

**Via Terraform (oci-citadel-dns.tf has `proxied = false` — already applied above):**

```bash
# Verify records are grey-cloud (proxied=false) in CF dashboard
dig +short trancendos.com
# Should return: the Citadel IP (e.g. 140.238.x.x)
# NOT a Cloudflare anycast IP (104.x.x.x or 172.x.x.x)
```

**Manual:** In Cloudflare Dashboard, click the orange cloud icon → turns grey.

### Step 3: Verify DNS propagation

```bash
# Check from multiple vantage points
dig +short trancendos.com @1.1.1.1
dig +short trancendos.com @8.8.8.8
dig +short api.trancendos.com @1.1.1.1

# Should all return the Citadel IP
CITADEL_IP=$(cd deploy/terraform && terraform output -raw citadel_public_ip)
echo "Expected: ${CITADEL_IP}"
```

### Step 4: Wait for TLS certificate issuance

Traefik polls ACME every 90 seconds after DNS resolves. Watch the log:

```bash
ssh tranc3@${CITADEL_IP} \
  'docker compose -f /opt/tranc3/docker-compose.production.yml logs traefik -f --tail=30'
# Look for: "Successfully obtained certificate"
```

Typical wait: 60–120 seconds after DNS propagates.

### Step 5: Verify HTTPS is working

```bash
# These must all return HTTP 200 with valid TLS
curl -sv https://trancendos.com/health 2>&1 | grep -E "HTTP|issuer|subject"
curl -sv https://api.trancendos.com/health 2>&1 | grep -E "HTTP|issuer|subject"
curl -sv https://www.trancendos.com/ 2>&1 | grep -E "HTTP|issuer"

# Forgejo / The Workshop
curl -sv https://the-workshop.trancendos.com/ 2>&1 | grep -E "HTTP|issuer" || true
```

### Step 6: Run post-cutover tests

```bash
# UAT suite against production
pytest tests/test_uat.py -v --base-url=https://api.trancendos.com

# Smoke tests
pytest tests/test_smoke.py -v

# Monitor status dashboard
./scripts/provision-citadel.sh --status
```

### Step 7: Disable Cloudflare Worker routes (for migrated paths)

Once traffic is confirmed healthy on Citadel, remove the CF Worker routes to
stop forwarding to the old workers. This prevents double-billing and avoids
stale routing.

```bash
# Disable API gateway CF Worker route
cd cloudflare/trancendos-api-gateway
npx wrangler routes delete <route-id>  # get route-id from: wrangler routes list

# Or disable the worker entirely if all routes migrated
# npx wrangler delete trancendos-api-gateway
```

CF Workers to decommission after full migration:

| Worker | Routes | Migrated to |
|--------|--------|-------------|
| `trancendos-api-gateway` | `api.trancendos.com/*` | Traefik → gateway-service :8040 |
| `trancendos-users-service` | — | users-service :8006 |
| `trancendos-notifications-service` | — | notifications :8008 |
| `trancendos-orders-service` | — | orders-service :8012 |
| `trancendos-payments-service` | — | payments-service :8013 |
| `trancendos-products-service` | — | products-service :8011 |
| `infinity-auth-api` | — | infinity-auth :8005 |
| `infinity-ai-api` | — | infinity-ai :8009 |
| `the-grid-api` | — | the-grid :8010 |
| `infinity-ws-api` | — | infinity-ws :8004 |

> Keep `infinity-void` (The Void) active until the self-hosted vault-service :8038
> is confirmed stable in production with all secrets migrated.

---

## Rollback Procedure

If something goes wrong after the DNS swap:

### Instant rollback (< 1 minute): re-enable Cloudflare proxy

**Terraform:**

```hcl
# In deploy/terraform/oci-citadel-dns.tf, change proxied = false to:
proxied = true  # re-enable CF proxy for apex, www, api records
```

```bash
cd deploy/terraform && terraform apply \
  -target=cloudflare_record.apex \
  -target=cloudflare_record.www \
  -target=cloudflare_record.api
```

**Manual (fastest):** Cloudflare Dashboard → DNS → click grey cloud → turns orange.
Traffic routes back through Cloudflare to the old CF Workers within seconds.

### Verify rollback

```bash
dig +short trancendos.com @1.1.1.1
# Should return Cloudflare anycast IP (104.x.x.x), not Citadel IP
curl -s https://api.trancendos.com/health && echo "Rollback OK"
```

---

## Post-Cutover: Enable Cloudflare Proxy (optional)

After Citadel has been stable for ≥ 24 hours, you can optionally re-enable the
Cloudflare proxy for DDoS protection **while keeping the Citadel as origin**.

This requires configuring an **Origin Certificate** on Traefik:

1. Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate
2. Download `cert.pem` and `key.pem`
3. Place them in `deploy/traefik/certs/`
4. Update Traefik static config to use the origin cert for `*.trancendos.com`
5. Set SSL/TLS mode to **Full (Strict)** in Cloudflare
6. Set `proxied = true` in `oci-citadel-dns.tf` and terraform apply

> Do NOT re-enable proxy with SSL mode "Flexible" — that sends HTTP to
> Citadel origin and breaks the Traefik HTTPS setup.

---

## Verification: dig commands reference

```bash
# Confirm Citadel IP (not Cloudflare)
CITADEL_IP=$(cd deploy/terraform && terraform output -raw citadel_public_ip 2>/dev/null)

# Check all records resolve to Citadel
dig +short trancendos.com          # must == ${CITADEL_IP}
dig +short www.trancendos.com      # must == ${CITADEL_IP}
dig +short api.trancendos.com      # must == ${CITADEL_IP}

# Check CNAME for the-workshop
dig +short the-workshop.trancendos.com  # must resolve to ${CITADEL_IP} (via CNAME)

# Check TLS certificate issuer
echo | openssl s_client -connect trancendos.com:443 -servername trancendos.com 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates
# Issuer should be: Let's Encrypt (via Traefik ACME)
```

---

*Last updated: 2026-06-05*
*Reference: `deploy/terraform/oci-citadel-dns.tf`, `deploy/traefik/`, `CF_WORKER_MIGRATION_ROADMAP.md`*
