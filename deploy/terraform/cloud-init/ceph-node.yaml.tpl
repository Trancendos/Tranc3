#cloud-config
# ──────────────────────────────────────────────────────────────
# Tranc3 Ceph/MicroCeph Node — Cloud-Init Template
# Bootstraps MicroCeph single-node deployment on OCI A1 Flex (ARM)
# ──────────────────────────────────────────────────────────────

package_update: true
package_upgrade: true

packages:
  - curl
  - wget
  - git
  - htop
  - tmux
  - vim
  - jq
  - lvm2
  - thin-provisioning-tools
  - chrony
  - logrotate
  - prometheus-node-exporter
  - softhsm2

write_files:
  # ── MicroCeph Bootstrap Script ──────────────────────────
  - path: /opt/tranc3/bootstrap-microceph.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      set -euo pipefail

      LOG_TAG="tranc3-microceph"
      logger -t "$LOG_TAG" "Starting MicroCeph bootstrap..."

      # ── Install MicroCeph via snap ──────────────────────
      if ! command -v microceph &>/dev/null; then
          logger -t "$LOG_TAG" "Installing MicroCeph snap..."
          snap install microceph --channel=quincy/stable || {
              logger -t "$LOG_TAG" "Snap install failed, trying apt fallback..."
              apt-get update -qq
              apt-get install -y -qq ceph-mon ceph-osd ceph-mds ceph-mgr ceph-radosgw
          }
      fi

      # ── Initialize MicroCeph Cluster ────────────────────
      if ! microceph status &>/dev/null; then
          logger -t "$LOG_TAG" "Initializing MicroCeph cluster..."
          microceph cluster bootstrap || {
              logger -t "$LOG_TAG" "ERROR: MicroCeph cluster bootstrap failed"
              exit 1
          }
          logger -t "$LOG_TAG" "MicroCeph cluster initialized"
      else
          logger -t "$LOG_TAG" "MicroCeph cluster already running"
      fi

      # ── Configure OSD ───────────────────────────────────
      # Use a loopback device for single-node deployment
      OSD_DIR="/var/lib/microceph/osd"
      OSD_FILE="$$${OSD_DIR}/osd-block.img"
      OSD_SIZE="30G"  # Adjust based on available disk

      mkdir -p "$OSD_DIR"
      if [ ! -f "$OSD_FILE" ]; then
          logger -t "$LOG_TAG" "Creating OSD loopback device..."
          truncate -s "$OSD_SIZE" "$OSD_FILE"
          mkfs.xfs -f "$OSD_FILE" 2>/dev/null || mkfs.ext4 -F "$OSD_FILE"
      fi

      # Add OSD
      if ! microceph.ceph osd ls 2>/dev/null | grep -q "0"; then
          logger -t "$LOG_TAG" "Adding OSD..."
          microceph disk add "$OSD_FILE" --wipe || {
              logger -t "$LOG_TAG" "WARNING: OSD add failed, will retry on next boot"
          }
      fi

      # ── Configure RGW ───────────────────────────────────
      if ! microceph.ceph osd pool ls 2>/dev/null | grep -q ".rgw"; then
          logger -t "$LOG_TAG" "Enabling RGW..."
          microceph enable rgw || {
              logger -t "$LOG_TAG" "WARNING: RGW enable failed"
          }
      fi

      # ── Create S3 User for Tranc3 ───────────────────────
      if ! microceph.radosgw-admin user info --uid=tranc3-nano &>/dev/null; then
          logger -t "$LOG_TAG" "Creating S3 user for Tranc3 nanoservice..."
          microceph.radosgw-admin user create \
              --uid=tranc3-nano \
              --display-name="Tranc3 Nanoservice" \
              --access-key="$(openssl rand -hex 16)" \
              --secret-key="$(openssl rand -hex 32)" \
              --caps="users=read;buckets=read,write;metadata=read" \
              2>/dev/null | tee /etc/tranc3/rgw-user.json || {
                  logger -t "$LOG_TAG" "WARNING: S3 user creation failed"
              }
      fi

      # ── Configure CRUSH Map ─────────────────────────────
      logger -t "$LOG_TAG" "Configuring CRUSH map with ${crush_default_rule} rule..."
      # CRUSH map customization is handled by the Rust nanoservice

      # ── Create Default Pools ────────────────────────────
      for pool in tranc3-hot tranc3-cold tranc3-archive; do
          if ! microceph.ceph osd pool ls 2>/dev/null | grep -q "^$${pool}$"; then
              logger -t "$LOG_TAG" "Creating pool $${pool}..."
              microceph.ceph osd pool create "$pool" 32 32 replicated || true
          fi
      done

      logger -t "$LOG_TAG" "MicroCeph bootstrap completed"

  # ── Ceph Environment Configuration ─────────────────────
  - path: /etc/tranc3/ceph.env
    owner: root:root
    permissions: '0640'
    content: |
      TRANC3_ENVIRONMENT=${environment}
      TRANC3_SYSTEM_MODE=${system_mode}
      CEPH_CLUSTER_NETWORK=${ceph_cluster_network}
      CEPH_PUBLIC_NETWORK=${ceph_cluster_network}
      TRANC3_CRUSH_RULE=${crush_default_rule}
      TRANC3_HSM_PROVIDER=${hsm_provider}
      TRANC3_NANOSERVICE_IP=${nanoservice_private_ip}
      TRANC3_K3S_IP=${k3s_private_ip}

  # ── RGW Configuration ──────────────────────────────────
  - path: /opt/tranc3/rgw-config.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      set -euo pipefail
      # Configure RGW for S3-compatible access
      microceph.radosgw-admin zone set --rgw-zone=default < /opt/tranc3/zone.json 2>/dev/null || true
      microceph.radosgw-admin period update --commit 2>/dev/null || true

  # ── Logrotate ──────────────────────────────────────────
  - path: /etc/logrotate.d/tranc3-ceph
    owner: root:root
    permissions: '0644'
    content: |
      /var/log/ceph/*.log {
          daily
          rotate 14
          compress
          delaycompress
          missingok
          notifempty
          create 0640 ceph ceph
      }

runcmd:
  # ── System Configuration ────────────────────────────────
  - sysctl -w vm.swappiness=1
  - sysctl -w vm.dirty_ratio=10
  - sysctl -w vm.dirty_background_ratio=3
  - sysctl -w net.core.somaxconn=65535

  # ── Create Tranc3 User ──────────────────────────────────
  - useradd -r -s /bin/false -d /var/lib/microceph tranc3 2>/dev/null || true
  - mkdir -p /etc/tranc3 /var/lib/microceph/osd /var/log/ceph

  # ── Initialize SoftHSM2 ─────────────────────────────────
  - |
      if [ "${hsm_provider}" = "softhsm2" ]; then
          if ! softhsm2-util --show-slots 2>/dev/null | grep -q "tranc3-hsm"; then
              softhsm2-util --init-token --slot 0 --label "tranc3-hsm" \
                  --pin "tranc3-hsm-pin" --so-pin "tranc3-hsm-so-pin"
          fi
      fi

  # ── Run MicroCeph Bootstrap ─────────────────────────────
  - /opt/tranc3/bootstrap-microceph.sh

  # ── Enable and Start Services ───────────────────────────
  - systemctl enable prometheus-node-exporter
  - systemctl start prometheus-node-exporter

  # ── Firewall Configuration ──────────────────────────────
  - iptables -A INPUT -p tcp --dport 7480 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 6789 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 3300 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 6800:7300 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 8443 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 9100 -s 10.0.0.0/16 -j ACCEPT
  - netfilter-persistent save 2>/dev/null || true

final_message: "Tranc3 Ceph/MicroCeph node boot complete on $INSTANCE_ID at $TIMESTAMP"
