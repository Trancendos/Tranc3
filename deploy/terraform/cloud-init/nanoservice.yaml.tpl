#cloud-config
# ──────────────────────────────────────────────────────────────
# Tranc3 Nanoservice — Cloud-Init Template
# Bootstraps the Rust nanoservice on OCI A1 Flex (ARM)
# ──────────────────────────────────────────────────────────────

package_update: true
package_upgrade: true

packages:
  - build-essential
  - pkg-config
  - libssl-dev
  - libdevmapper-dev
  - libsodium-dev
  - curl
  - wget
  - git
  - htop
  - tmux
  - vim
  - jq
  - socat
  - conntrack
  - iptables
  - chrony
  - logrotate
  - prometheus-node-exporter
  - softhsm2

write_files:
  # ── Nanoservice Environment Configuration ───────────────
  - path: /etc/tranc3/nanoservice.env
    owner: root:root
    permissions: '0640'
    content: |
      # Tranc3 Nanoservice Runtime Configuration
      TRANC3_ENVIRONMENT=${environment}
      TRANC3_SYSTEM_MODE=${system_mode}
      TRANC3_CRUSH_RULE=${crush_default_rule}
      TRANC3_HSM_PROVIDER=${hsm_provider}
      TRANC3_HSM_PIN=${hsm_pin}
      TRANC3_HTTP_PORT=8080
      TRANC3_METRICS_PORT=9090
      TRANC3_LOG_LEVEL=info
      TRANC3_OCI_REGION=${oci_region}
      TRANC3_OCI_NAMESPACE=${object_namespace}
      TRANC3_CEPH_ENDPOINT=http://${ceph_private_ip}:7480
      TRANC3_K3S_ENDPOINT=https://${k3s_private_ip}:6443
      RUST_LOG=tranc3_nanoservice=info
      RUST_BACKTRACE=1

  # ── Nanoservice Systemd Service ─────────────────────────
  - path: /etc/systemd/system/tranc3-nanoservice.service
    owner: root:root
    permissions: '0644'
    content: |
      [Unit]
      Description=Tranc3 Nanoservice — Adaptive Storage Router
      After=network-online.target
      Wants=network-online.target

      [Service]
      Type=simple
      EnvironmentFile=/etc/tranc3/nanoservice.env
      ExecStartPre=/opt/tranc3/pre-start.sh
      ExecStart=/opt/tranc3/tranc3-nano
      ExecReload=/bin/kill -HUP $MAINPID
      Restart=always
      RestartSec=5
      StartLimitIntervalSec=60
      StartLimitBurst=3

      # Security hardening
      NoNewPrivileges=true
      ProtectSystem=strict
      ProtectHome=true
      PrivateTmp=true
      ReadWritePaths=/var/lib/tranc3 /var/log/tranc3 /run/tranc3
      ReadOnlyPaths=/etc/tranc3

      # Resource limits (free-tier aware)
      LimitNOFILE=65536
      MemoryMax=4G
      CPUQuota=100%

      [Install]
      WantedBy=multi-user.target

  # ── Idle Defense Script ─────────────────────────────────
  - path: /opt/tranc3/idle-defense.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      # Tranc3 Idle Defense — Prevents OCI reclamation of Always Free instances
      # OCI reclaims instances with <20% CPU/network/memory for 7+ days.
      # This script generates periodic CPU bursts to stay above the threshold.
      set -euo pipefail

      CPU_TARGET=${idle_defense_cpu_target}
      BURST_DURATION=${idle_defense_duration}
      LOG_TAG="tranc3-idle-defense"

      logger -t "$LOG_TAG" "Starting idle defense burst: target=$$${CPU_TARGET}% duration=$$${BURST_DURATION}s"

      END_TIME=$(( SECONDS + BURST_DURATION ))
      while [ $SECONDS -lt $END_TIME ]; do
          # Generate CPU load using sha256sum (lightweight, no external deps)
          for i in $(seq 1 "$(nproc)"); do
              dd if=/dev/zero bs=1M count=10 2>/dev/null | sha256sum > /dev/null &
          done
          wait
          sleep 0.5
      done

      logger -t "$LOG_TAG" "Idle defense burst completed"

  # ── Idle Defense Cron ───────────────────────────────────
  - path: /etc/cron.d/tranc3-idle-defense
    owner: root:root
    permissions: '0644'
    content: |
      ${idle_defense_enabled}  *  *  *  *  root  /opt/tranc3/idle-defense.sh >> /var/log/tranc3/idle-defense.log 2>&1

  # ── Pre-start Health Check ──────────────────────────────
  - path: /opt/tranc3/pre-start.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      set -euo pipefail

      # Ensure data directories exist
      mkdir -p /var/lib/tranc3/data
      mkdir -p /var/lib/tranc3/cache
      mkdir -p /var/log/tranc3
      mkdir -p /run/tranc3

      # Check Ceph RGW connectivity (non-blocking)
      timeout 5 bash -c 'echo > /dev/tcp/${ceph_private_ip}/7480' 2>/dev/null && \
          echo "Ceph RGW reachable" || \
          echo "WARNING: Ceph RGW not reachable at ${ceph_private_ip}:7480"

      # Initialize SoftHSM2 token if HSM provider is softhsm2
      if [ "${hsm_provider}" = "softhsm2" ]; then
          if ! softhsm2-util --show-slots 2>/dev/null | grep -q "tranc3-hsm"; then
              softhsm2-util --init-token --slot 0 --label "tranc3-hsm" \
                  --so-pin "${hsm_pin}" --pin "${hsm_pin}"
              echo "SoftHSM2 token initialized"
          fi
      fi

  # ── Logrotate Configuration ─────────────────────────────
  - path: /etc/logrotate.d/tranc3
    owner: root:root
    permissions: '0644'
    content: |
      /var/log/tranc3/*.log {
          daily
          rotate 14
          compress
          delaycompress
          missingok
          notifempty
          create 0640 root root
      }

  # ── Node Exporter Configuration ─────────────────────────
  - path: /etc/default/prometheus-node-exporter
    owner: root:root
    permissions: '0644'
    content: |
      ARGS="--collector.systemd --collector.processes --web.listen-address=0.0.0.0:9100"

runcmd:
  # ── System Configuration ────────────────────────────────
  - sysctl -w vm.swappiness=10
  - sysctl -w vm.dirty_ratio=15
  - sysctl -w vm.dirty_background_ratio=5
  - sysctl -w net.core.somaxconn=65535
  - sysctl -w net.ipv4.tcp_max_syn_backlog=65535

  # ── Create Tranc3 User ──────────────────────────────────
  - useradd -r -s /bin/false -d /var/lib/tranc3 tranc3 2>/dev/null || true
  - chown -R tranc3:tranc3 /var/lib/tranc3 /var/log/tranc3

  # ── Download Nanoservice Binary ─────────────────────────
  - mkdir -p /opt/tranc3
  - |
      if [ -f /opt/tranc3/tranc3-nano ]; then
          echo "Nanoservice binary already present"
      else
          echo "Downloading Tranc3 nanoservice binary..."
          # In production, download from Forgejo releases or OCI Object Storage
          # curl -fSL -o /opt/tranc3/tranc3-nano "https://releases.tranc3.io/nanoservice/latest/tranc3-nano-aarch64"
          echo "Binary download skipped — deploy manually or via CI/CD"
      fi
  - chmod +x /opt/tranc3/tranc3-nano 2>/dev/null || true

  # ── Enable and Start Services ───────────────────────────
  - systemctl daemon-reload
  - systemctl enable prometheus-node-exporter
  - systemctl start prometheus-node-exporter
  - systemctl enable tranc3-nanoservice
  - systemctl start tranc3-nanoservice

  # ── Firewall Configuration ──────────────────────────────
  - iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 9090 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 9100 -s 10.0.0.0/16 -j ACCEPT
  - netfilter-persistent save 2>/dev/null || true

final_message: "Tranc3 Nanoservice boot complete on $INSTANCE_ID at $TIMESTAMP"
