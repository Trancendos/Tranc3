#!/usr/bin/env bash
# swarm-init.sh — Bootstrap a Docker Swarm cluster for Trancendos
#
# Run on the manager node FIRST, then follow the printed join command
# on each worker node.
#
# Usage:
#   ./deploy/swarm/swarm-init.sh               # single-node (dev)
#   MANAGER_IP=10.0.0.1 ./deploy/swarm/swarm-init.sh  # multi-node

set -euo pipefail

MANAGER_IP="${MANAGER_IP:-}"
REGISTRY="${REGISTRY:-ghcr.io/trancendos}"
TAG="${TAG:-latest}"
STACK_NAME="${STACK_NAME:-tranc3}"

if [ -z "${SECRET_KEY:-}" ]; then
    echo "ERROR: SECRET_KEY is required but not set. Aborting." >&2
    exit 1
fi

echo "=== Trancendos Docker Swarm Init ==="

# ── 1. Init or join swarm ──────────────────────────────────────────────────────
if ! docker info --format '{{.Swarm.LocalNodeState}}' | grep -q "active"; then
    if [ -n "$MANAGER_IP" ]; then
        docker swarm init --advertise-addr "$MANAGER_IP"
    else
        docker swarm init
    fi
    echo "Swarm initialised."
else
    echo "Already in a swarm."
fi

# ── 2. Create secrets (idempotent) ────────────────────────────────────────────
_create_secret() {
    local name="$1"
    local value="${2:-}"
    local file="${3:-}"

    if docker secret inspect "$name" &>/dev/null; then
        echo "  Secret '$name' already exists — skipping"
        return
    fi

    if [ -n "$file" ] && [ -f "$file" ]; then
        docker secret create "$name" "$file"
    elif [ -n "$value" ]; then
        printf "%s" "$value" | docker secret create "$name" -
    else
        echo "  WARNING: Secret '$name' has no value — set ${name^^} env var"
        return
    fi
    echo "  Created secret: $name"
}

echo ""
echo "Creating Docker Swarm secrets..."
_create_secret "secret_key"             "${SECRET_KEY:-}" ""
_create_secret "jwt_secret"             "${JWT_SECRET:-}" ""
_create_secret "database_url"           "${DATABASE_URL:-}" ""
_create_secret "redis_url"              "${REDIS_URL:-}" ""
_create_secret "grafana_admin_password" "${GRAFANA_ADMIN_PASSWORD:-changeme}" ""

# ── 3. Create overlay network (idempotent) ────────────────────────────────────
if ! docker network inspect tranc3_net &>/dev/null; then
    docker network create --driver overlay --attachable tranc3_net
    echo "Created overlay network: tranc3_net"
fi

# ── 4. Deploy stack ───────────────────────────────────────────────────────────
echo ""
echo "Deploying stack '$STACK_NAME'..."
REGISTRY="$REGISTRY" TAG="$TAG" docker stack deploy \
    --compose-file "$(dirname "$0")/docker-stack.yml" \
    --with-registry-auth \
    "$STACK_NAME"

echo ""
echo "=== Stack deployed. Monitor with: ==="
echo "  docker stack ps $STACK_NAME"
echo "  docker service ls"
echo ""
echo "Worker join command:"
docker swarm join-token worker
