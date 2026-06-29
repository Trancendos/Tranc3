#!/bin/bash
# Cloud-init script for Trancendos production setup on OCI Ubuntu 22.04 ARM64
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# System update
apt-get update -qq
apt-get upgrade -y -qq

# Install essentials
apt-get install -y -qq \
  curl git make unzip jq ufw \
  apt-transport-https ca-certificates gnupg lsb-release

# Add swap (2 GB) — ARM64 OCI free tier has limited RAM
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Firewall — allow SSH, HTTP, HTTPS only
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Install Docker (pinned to latest stable via get.docker.com — reproducible on Ubuntu 22.04)
DOCKER_VERSION="5:26.1.4-1~ubuntu.22.04~jammy"
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=arm64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq \
  docker-ce="${DOCKER_VERSION}" \
  docker-ce-cli="${DOCKER_VERSION}" \
  containerd.io \
  docker-compose-plugin
usermod -aG docker ubuntu

# Configure Docker log rotation and storage driver BEFORE first start
cat > /etc/docker/daemon.json <<'DOCKEREOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "data-root": "/mnt/tranc3-data/docker"
}
DOCKEREOF

# Format and mount data volume (attached as /dev/sdb)
if [ -b /dev/sdb ] && ! blkid /dev/sdb | grep -q ext4; then
  mkfs.ext4 -L tranc3-data /dev/sdb
fi

mkdir -p /mnt/tranc3-data
if ! grep -q tranc3-data /etc/fstab; then
  echo "LABEL=tranc3-data /mnt/tranc3-data ext4 defaults,nofail 0 2" >> /etc/fstab
fi
mount -a || true

# Pre-create Docker data-root and volumes on persistent disk before Docker starts
mkdir -p /mnt/tranc3-data/docker
mkdir -p /mnt/tranc3-data/volumes

# Enable and start Docker (data-root already set to persistent disk via daemon.json)
systemctl enable docker
systemctl start docker

# Clone repo (main branch)
mkdir -p /mnt/tranc3-data/app
if [ ! -d /mnt/tranc3-data/app/.git ]; then
  git clone --branch main --depth 1 https://github.com/Trancendos/Tranc3 /mnt/tranc3-data/app
fi

chown -R ubuntu:ubuntu /mnt/tranc3-data

# Install uv (pinned version — zero-cost Python package manager)
UV_VERSION="0.4.30"
curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-aarch64-unknown-linux-gnu.tar.gz" \
  | tar -xz -C /usr/local/bin --strip-components=1 uv-aarch64-unknown-linux-gnu/uv
chmod +x /usr/local/bin/uv

echo "Trancendos cloud-init complete — run: cd /mnt/tranc3-data/app && cp .env.example .env"
