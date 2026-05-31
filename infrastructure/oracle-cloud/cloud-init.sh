#!/bin/bash
# Cloud-init script for Trancendos production setup on OCI Ubuntu 22.04 ARM64
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# System update
apt-get update -qq
apt-get upgrade -y -qq

# Install essentials
apt-get install -y -qq \
  curl git make unzip jq \
  apt-transport-https ca-certificates gnupg lsb-release

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu

# Install Docker Compose plugin
apt-get install -y -qq docker-compose-plugin

# Format and mount data volume (attached as /dev/sdb)
if [ -b /dev/sdb ] && ! blkid /dev/sdb | grep -q ext4; then
  mkfs.ext4 -L tranc3-data /dev/sdb
fi

mkdir -p /mnt/tranc3-data
if ! grep -q tranc3-data /etc/fstab; then
  echo "LABEL=tranc3-data /mnt/tranc3-data ext4 defaults,nofail 0 2" >> /etc/fstab
fi
mount -a || true

# Clone repo
mkdir -p /mnt/tranc3-data/app
if [ ! -d /mnt/tranc3-data/app/.git ]; then
  git clone https://github.com/Trancendos/Tranc3 /mnt/tranc3-data/app
fi

chown -R ubuntu:ubuntu /mnt/tranc3-data

# Install uv (zero-cost Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh || true

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Configure Docker log rotation
cat > /etc/docker/daemon.json <<'DOCKEREOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
DOCKEREOF

systemctl reload docker || systemctl restart docker

# Set up data directory symlink for Docker volumes
mkdir -p /mnt/tranc3-data/volumes
if [ ! -d /var/lib/docker/volumes ]; then
  ln -sf /mnt/tranc3-data/volumes /var/lib/docker/volumes
fi

echo "Trancendos cloud-init complete — run: cd /mnt/tranc3-data/app && cp .env.example .env"
