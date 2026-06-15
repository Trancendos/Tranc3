#!/usr/bin/env bash
# gen-internal-certs.sh — Generate internal CA + server/client certificates for mTLS
# ======================================================================================
# Run once per environment (dev/staging/production) to bootstrap the mTLS PKI.
# Certificates are placed in infra/traefik/certs/ and should NOT be committed to git.
#
# Usage:
#   ./infra/traefik/scripts/gen-internal-certs.sh [output_dir]
#
# Output files:
#   internal-ca.pem          — Internal CA certificate (shared across all services)
#   internal-ca-key.pem      — CA private key (keep secure, never distribute)
#   internal-server.pem      — Traefik server certificate
#   internal-server-key.pem  — Traefik server private key
#   workers/                 — Per-worker client certs (one per worker name)
#     <name>.pem / <name>-key.pem
#
# Dependencies: openssl (stdlib on Linux/macOS)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${1:-${REPO_ROOT}/infra/traefik/certs}"
DAYS=825  # <3 years to comply with modern browser/CA rules

mkdir -p "${OUTPUT_DIR}/workers"

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[gen-certs]${NC} $*"; }
warn() { echo -e "${YELLOW}[gen-certs]${NC} $*"; }

# ── 1. Internal CA ────────────────────────────────────────────────────────────
if [[ ! -f "${OUTPUT_DIR}/internal-ca.pem" ]]; then
    log "Generating internal CA key and certificate..."
    openssl genrsa -out "${OUTPUT_DIR}/internal-ca-key.pem" 4096 2>/dev/null
    openssl req -new -x509 \
        -key "${OUTPUT_DIR}/internal-ca-key.pem" \
        -out "${OUTPUT_DIR}/internal-ca.pem" \
        -days ${DAYS} \
        -subj "/CN=Trancendos Internal CA/O=Trancendos/OU=Infrastructure" \
        -extensions v3_ca \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign"
    log "CA certificate written to ${OUTPUT_DIR}/internal-ca.pem"
else
    warn "CA certificate already exists — skipping (delete to regenerate)"
fi

# ── 2. Traefik server certificate ────────────────────────────────────────────
if [[ ! -f "${OUTPUT_DIR}/internal-server.pem" ]]; then
    log "Generating Traefik internal server certificate..."
    openssl genrsa -out "${OUTPUT_DIR}/internal-server-key.pem" 2048 2>/dev/null
    openssl req -new \
        -key "${OUTPUT_DIR}/internal-server-key.pem" \
        -out "${OUTPUT_DIR}/internal-server.csr" \
        -subj "/CN=traefik.internal.trancendos.local/O=Trancendos/OU=Infrastructure"
    openssl x509 -req \
        -in "${OUTPUT_DIR}/internal-server.csr" \
        -CA "${OUTPUT_DIR}/internal-ca.pem" \
        -CAkey "${OUTPUT_DIR}/internal-ca-key.pem" \
        -CAcreateserial \
        -out "${OUTPUT_DIR}/internal-server.pem" \
        -days ${DAYS} \
        -extfile <(printf "subjectAltName=DNS:traefik.internal.trancendos.local,DNS:localhost,IP:127.0.0.1\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
    rm -f "${OUTPUT_DIR}/internal-server.csr"
    log "Server certificate written to ${OUTPUT_DIR}/internal-server.pem"
fi

# ── 3. Per-worker client certificates ────────────────────────────────────────
WORKERS=(
    infinity-auth infinity-ws users-service monitoring notifications
    infinity-ai the-grid products-service orders-service payments-service
    files-service identity-service hive-service
)

for WORKER in "${WORKERS[@]}"; do
    CERT="${OUTPUT_DIR}/workers/${WORKER}.pem"
    KEY="${OUTPUT_DIR}/workers/${WORKER}-key.pem"
    if [[ ! -f "${CERT}" ]]; then
        log "Generating client cert for worker: ${WORKER}"
        openssl genrsa -out "${KEY}" 2048 2>/dev/null
        openssl req -new \
            -key "${KEY}" \
            -out "${OUTPUT_DIR}/workers/${WORKER}.csr" \
            -subj "/CN=${WORKER}.internal.trancendos.local/O=Trancendos/OU=Workers"
        openssl x509 -req \
            -in "${OUTPUT_DIR}/workers/${WORKER}.csr" \
            -CA "${OUTPUT_DIR}/internal-ca.pem" \
            -CAkey "${OUTPUT_DIR}/internal-ca-key.pem" \
            -CAcreateserial \
            -out "${CERT}" \
            -days ${DAYS} \
            -extfile <(printf "keyUsage=digitalSignature\nextendedKeyUsage=clientAuth\n")
        rm -f "${OUTPUT_DIR}/workers/${WORKER}.csr"
    fi
done

log "Certificate generation complete."
log "Files in: ${OUTPUT_DIR}"
warn "Add ${OUTPUT_DIR} to .gitignore — do NOT commit private keys!"
