# ──────────────────────────────────────────────────────────────
# Tranc3 Ecosystem — Cloudflare DNS Records for Citadel
# Points trancendos.com and subdomains to the Citadel public IP.
#
# proxied = false — DIRECT DNS (grey cloud) is required because:
#   1. Traefik issues Let's Encrypt TLS certificates directly via
#      HTTP-01 challenge; Cloudflare proxying intercepts that.
#   2. WebSocket workers (The Nexus :8004) need pass-through.
#   3. Self-hosted Forgejo SSH clone (git+ssh) must bypass CF.
#
# Enable Cloudflare proxy (orange cloud) only after TLS is
# confirmed working on Citadel and you want CF DDoS protection —
# then switch proxied = true on the www / apex records only.
#
# Prerequisites: cloudflare_zone_id and cloudflare_api_token must
# be set in terraform.tfvars (or TF_VAR_* env vars). The Cloudflare
# provider is configured in main.tf — update the provider block to
# use cloudflare_api_token if you are also using R2 (they share the
# provider instance; see note below).
# ──────────────────────────────────────────────────────────────

# ── Provider alias for DNS (token-scoped) ────────────────────
# The default cloudflare provider in main.tf uses the R2 access
# key. For DNS management we need a Zone:DNS:Edit API token.
# We add an aliased provider here so DNS resources don't conflict.

provider "cloudflare" {
  alias     = "dns"
  api_token = var.cloudflare_api_token
}

# ── Local: resolved Citadel IP ───────────────────────────────
# The reserved public IP is created in oci-citadel.tf.

locals {
  citadel_ip = oci_core_public_ip.citadel.ip_address
}

# ── Apex record: trancendos.com → Citadel ───────────────────

resource "cloudflare_record" "apex" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = var.domain
  type     = "A"
  content  = local.citadel_ip
  proxied  = false  # grey cloud — direct; required for Traefik ACME
  ttl      = 300
  comment  = "Tranc3 Citadel primary — managed by Terraform"

  lifecycle {
    # The IP is stable (reserved); prevent accidental overwrites.
    prevent_destroy = true
  }
}

# ── www subdomain ─────────────────────────────────────────────

resource "cloudflare_record" "www" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = "www"
  type     = "A"
  content  = local.citadel_ip
  proxied  = false
  ttl      = 300
  comment  = "Tranc3 Citadel www — managed by Terraform"
}

# ── API subdomain: api.trancendos.com → Citadel ──────────────
# Traefik routes api.trancendos.com/* to the gateway-service (:8040)
# which proxies to all 38 platform workers.

resource "cloudflare_record" "api" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = "api"
  type     = "A"
  content  = local.citadel_ip
  proxied  = false
  ttl      = 300
  comment  = "Tranc3 API gateway — managed by Terraform"
}

# ── Forgejo / The Workshop: the-workshop.trancendos.com ──────
# Forgejo runs at trancendos.com/the-workshop via Traefik path
# routing, but this CNAME ensures the bare subdomain also works
# (Traefik Host header rule handles the routing internally).

resource "cloudflare_record" "the_workshop" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = "the-workshop"
  type     = "CNAME"
  content  = var.domain
  proxied  = false
  ttl      = 300
  comment  = "Forgejo / The Workshop — managed by Terraform"
}

# ── Email authentication: SPF + DMARC ─────────────────────────
# workers/email-service/worker.py (SMTP_HOST) is the only thing on this
# domain that could send mail, and it's an unconfigured, bring-your-own
# relay by default (SMTP_HOST empty → log-only mode) — there is no fixed,
# known sending IP or provider to authorize yet. Until a real relay is
# chosen, the honest, safe record is "this domain sends no mail":
#   - SPF hard-fails every sender (`-all`, no `include:`/`ip4:` — there's
#     nothing legitimate to allow yet).
#   - DMARC starts at p=none (monitor only, per the standard DMARC rollout
#     playbook), so you can see who's sending mail *as* this domain —
#     spoofing attempts included — before tightening to quarantine/reject.
#
# TWO THINGS MUST HAPPEN TOGETHER, NOT JUST ONE, BEFORE THIS DOMAIN CAN
# ACTUALLY SEND MAIL: setting SMTP_HOST on email-service alone is NOT
# enough — the SPF record below must also gain an `include:`/`ip4:` for
# that relay (still `-all` at the end) or every message it sends will
# fail SPF at the receiving end. There is no automated guard preventing
# someone from setting SMTP_HOST without updating this file; that's a
# deployment-process gap, not a Terraform one — flag it in your PR/deploy
# checklist when SMTP_HOST is finally configured.
#
# No DKIM record here: DKIM is a per-sending-service selector + public key,
# and there's no relay configured yet to generate one — add it (and
# tighten SPF's `include:`) when SMTP_HOST is actually set to something.
#
# No rua/ruf on the DMARC record: they'd point at dmarc-reports@ mailbox
# that doesn't exist yet (nothing provisions it — no MX record, no mailbox
# behind email-service). An aggregate-report URI with no working recipient
# either silently loses every report or bounces at the reporting sender,
# neither of which is useful. Add rua=mailto:dmarc-reports@${var.domain}
# once that mailbox is actually provisioned and receiving mail.
#
# DEF STAN 00-700 (Information Assurance, docs/defstan/) scopes IA "full"
# to all public-facing services — matching that here via 12_dns.csv /
# 12b_dns_records.csv's ComplianceFrameworks column.

resource "cloudflare_record" "spf" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = "@"
  type     = "TXT"
  content  = "v=spf1 -all"
  proxied  = false
  ttl      = 300
  comment  = "SPF — no senders authorized yet; update alongside SMTP_HOST — managed by Terraform"
}

resource "cloudflare_record" "dmarc" {
  provider = cloudflare.dns
  zone_id  = var.cloudflare_zone_id
  name     = "_dmarc"
  type     = "TXT"
  content  = "v=DMARC1; p=none"
  proxied  = false
  ttl      = 300
  comment  = "DMARC — monitor-only (p=none); add rua= once dmarc-reports@ mailbox exists — managed by Terraform"
}

# ── DNS output summary ────────────────────────────────────────

output "dns_records" {
  description = "DNS records created for the Citadel deployment"
  value = {
    apex         = "${var.domain} A → ${local.citadel_ip}"
    www          = "www.${var.domain} A → ${local.citadel_ip}"
    api          = "api.${var.domain} A → ${local.citadel_ip}"
    the_workshop = "the-workshop.${var.domain} CNAME → ${var.domain}"
    spf          = "${var.domain} TXT → v=spf1 -all"
    dmarc        = "_dmarc.${var.domain} TXT → v=DMARC1; p=none"
    note         = "All records are proxied=false (grey cloud / direct DNS)"
  }
}

# ── Citadel public IP output (also used by ansible, scripts) ─

output "citadel_public_ip" {
  description = "Reserved public IP address of the Citadel instance"
  value       = oci_core_public_ip.citadel.ip_address
}

output "citadel_instance_ocid" {
  description = "OCID of the Citadel compute instance"
  value       = oci_core_instance.citadel.id
}

output "citadel_ssh_command" {
  description = "SSH command to connect to Citadel as the tranc3 user"
  value       = "ssh -i ~/.ssh/tranc3_citadel tranc3@${oci_core_public_ip.citadel.ip_address}"
}
