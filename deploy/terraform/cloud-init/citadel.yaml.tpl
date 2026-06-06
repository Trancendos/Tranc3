#cloud-config
# ──────────────────────────────────────────────────────────────
# Tranc3 Citadel — Cloud-Init Bootstrap
# Primary production server: Docker Compose + 38 workers
# Ubuntu 22.04 LTS ARM64 (VM.Standard.A1.Flex)
#
# Template variables (passed from Terraform templatefile()):
#   domain               - e.g. trancendos.com
#   environment          - production | staging | development
#   system_mode          - true_nas | hybrid | cloud_only
#   admin_cidr_block     - CIDR that may reach admin endpoints
#   ssh_authorized_keys  - PEM public key string
#   github_repo_url      - https://github.com/Trancendos/Tranc3.git
#   git_branch           - main | claude/... etc.
#   idle_defense_enabled - true | false
# ──────────────────────────────────────────────────────────────

package_update: true
package_upgrade: true

packages:
  - git
  - curl
  - wget
  - vim
  - htop
  - jq
  - chrony
  - fail2ban
  - ufw
  - unattended-upgrades
  - python3
  - python3-pip
  - python3-venv
  - prometheus-node-exporter
  - logrotate
  - ca-certificates
  - gnupg
  - lsb-release
  - apt-transport-https
  - software-properties-common

write_files:
  # ── Deployment environment ──────────────────────────────────
  - path: /etc/tranc3/deployment.env
    owner: root:root
    permissions: '0640'
    content: |
      # Tranc3 Citadel — deployment environment
      # Written by cloud-init on first boot. Do not edit manually.
      TRANC3_DOMAIN=${domain}
      TRANC3_ENVIRONMENT=${environment}
      TRANC3_SYSTEM_MODE=${system_mode}
      TRANC3_ADMIN_CIDR=${admin_cidr_block}
      TRANC3_GIT_BRANCH=${git_branch}
      TRANC3_GIT_REPO=${github_repo_url}
      TRANC3_IDLE_DEFENSE=${idle_defense_enabled}

  # ── Fail2ban SSH jail override ───────────────────────────────
  - path: /etc/fail2ban/jail.d/sshd-citadel.conf
    owner: root:root
    permissions: '0644'
    content: |
      [sshd]
      enabled   = true
      port      = 22
      logpath   = %(sshd_log)s
      backend   = %(sshd_backend)s
      maxretry  = 5
      bantime   = 3600
      findtime  = 600

  # ── Traefik systemd access journal ──────────────────────────
  - path: /etc/logrotate.d/tranc3
    owner: root:root
    permissions: '0644'
    content: |
      /opt/tranc3/logs/*.log {
          daily
          missingok
          rotate 14
          compress
          delaycompress
          notifempty
          create 0640 tranc3 tranc3
          sharedscripts
          postrotate
              /usr/bin/systemctl reload-or-restart tranc3-citadel || true
          endscript
      }

  # ── tranc3-citadel systemd service ──────────────────────────
  - path: /etc/systemd/system/tranc3-citadel.service
    owner: root:root
    permissions: '0644'
    content: |
      [Unit]
      Description=Tranc3 Citadel — Docker Compose Production Stack
      Documentation=https://github.com/Trancendos/Tranc3
      After=network-online.target docker.service
      Wants=network-online.target
      Requires=docker.service

      [Service]
      Type=oneshot
      RemainAfterExit=yes
      User=tranc3
      WorkingDirectory=/opt/tranc3
      # 60-second delay lets Docker daemon and network fully settle
      ExecStartPre=/bin/sleep 60
      ExecStartPre=/usr/bin/git -C /opt/tranc3 pull --ff-only origin ${git_branch}
      ExecStart=/usr/bin/docker compose -f /opt/tranc3/docker-compose.production.yml up -d --remove-orphans
      ExecStop=/usr/bin/docker compose -f /opt/tranc3/docker-compose.production.yml down
      # Allow 5 minutes for all containers to start
      TimeoutStartSec=300
      TimeoutStopSec=120
      Restart=on-failure
      RestartSec=30

      [Install]
      WantedBy=multi-user.target

  # ── UFW application profile for Traefik ─────────────────────
  - path: /etc/ufw/applications.d/traefik
    owner: root:root
    permissions: '0644'
    content: |
      [Traefik Web]
      title=Traefik HTTP
      description=Traefik reverse proxy HTTP entrypoint
      ports=80/tcp

      [Traefik HTTPS]
      title=Traefik HTTPS
      description=Traefik reverse proxy HTTPS entrypoint
      ports=443/tcp

  # ── unattended-upgrades config ───────────────────────────────
  - path: /etc/apt/apt.conf.d/20auto-upgrades
    owner: root:root
    permissions: '0644'
    content: |
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Unattended-Upgrade "1";
      APT::Periodic::AutocleanInterval "7";
      APT::Periodic::Download-Upgradeable-Packages "1";

  # ── Docker daemon config ─────────────────────────────────────
  - path: /etc/docker/daemon.json
    owner: root:root
    permissions: '0644'
    content: |
      {
        "log-driver": "json-file",
        "log-opts": {
          "max-size": "50m",
          "max-file": "5"
        },
        "storage-driver": "overlay2",
        "live-restore": true,
        "userland-proxy": false,
        "metrics-addr": "127.0.0.1:9323",
        "experimental": true
      }

  # ── Idle defense cron (OCI reclamation prevention) ───────────
  - path: /etc/cron.d/tranc3-idle-defense
    owner: root:root
    permissions: '0644'
    content: |
      # Prevents OCI from reclaiming Always Free instances that appear idle.
      # OCI reclaims instances with CPU/net below 20% for 7 consecutive days.
      # This burst script keeps average utilisation above the threshold.
      # Enabled: ${idle_defense_enabled}
      %{ if idle_defense_enabled ~}
      */5 * * * * tranc3 /usr/local/bin/tranc3-idle-burst.sh >> /var/log/tranc3-idle-defense.log 2>&1
      %{ endif ~}

  # ── Idle defense burst script ────────────────────────────────
  - path: /usr/local/bin/tranc3-idle-burst.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      # Tranc3 Idle Defense — CPU burst to prevent OCI reclamation
      # Runs for 30 seconds, targeting ~25% CPU across all 4 cores
      CPU_CORES=$(nproc)
      DURATION=30
      # Use yes piped to /dev/null — zero memory, pure CPU
      for i in $(seq 1 "$CPU_CORES"); do
        timeout "$DURATION" yes > /dev/null 2>&1 &
      done
      wait
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) idle-defense burst completed (${CPU_CORES} cores, ${DURATION}s)"

runcmd:
  # ── 1. Create tranc3 system user ───────────────────────────
  - useradd --system --create-home --shell /bin/bash --groups sudo tranc3
  - echo 'tranc3 ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/tranc3
  - chmod 440 /etc/sudoers.d/tranc3

  # ── 2. Add SSH authorized key for tranc3 user ──────────────
  - mkdir -p /home/tranc3/.ssh
  - echo "${ssh_authorized_keys}" > /home/tranc3/.ssh/authorized_keys
  - chmod 700 /home/tranc3/.ssh
  - chmod 600 /home/tranc3/.ssh/authorized_keys
  - chown -R tranc3:tranc3 /home/tranc3/.ssh

  # ── 3. Install Docker CE (official ARM64 apt repo) ─────────
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  - chmod a+r /etc/apt/keyrings/docker.gpg
  - |
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update -y
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  - systemctl enable docker
  - systemctl start docker

  # ── 4. Add tranc3 user to docker group ─────────────────────
  - usermod -aG docker tranc3

  # ── 5. Verify Docker Compose v2 ────────────────────────────
  - docker compose version

  # ── 6. Create directory structure ──────────────────────────
  - mkdir -p /opt/tranc3/{logs,data,backups,secrets}
  - mkdir -p /etc/tranc3
  - chown -R tranc3:tranc3 /opt/tranc3

  # ── 7. Clone the Tranc3 repository ─────────────────────────
  - |
    sudo -u tranc3 git clone --branch "${git_branch}" --depth 1 \
      "${github_repo_url}" /opt/tranc3
  - chown -R tranc3:tranc3 /opt/tranc3

  # ── 8. Configure UFW firewall ───────────────────────────────
  - ufw --force reset
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow 22/tcp comment 'SSH'
  - ufw allow 80/tcp comment 'HTTP (Traefik ACME + redirect)'
  - ufw allow 443/tcp comment 'HTTPS (Traefik TLS)'
  - ufw allow from ${admin_cidr_block} to any port 8888 proto tcp comment 'Traefik dashboard'
  - ufw allow 9100/tcp comment 'Prometheus node-exporter (internal)'
  - ufw --force enable

  # ── 9. Configure fail2ban ───────────────────────────────────
  - systemctl enable fail2ban
  - systemctl start fail2ban

  # ── 10. Enable chrony (time sync) ──────────────────────────
  - systemctl enable chrony
  - systemctl start chrony

  # ── 11. Enable unattended-upgrades ─────────────────────────
  - systemctl enable unattended-upgrades
  - systemctl start unattended-upgrades

  # ── 12. Enable prometheus-node-exporter ────────────────────
  - systemctl enable prometheus-node-exporter
  - systemctl start prometheus-node-exporter

  # ── 13. Enable and start tranc3-citadel service ────────────
  - systemctl daemon-reload
  - systemctl enable tranc3-citadel.service

  # ── 14. Set correct permissions on config dir ──────────────
  - chmod 750 /etc/tranc3
  - chown -R root:tranc3 /etc/tranc3
  - chmod 640 /etc/tranc3/deployment.env

  # ── 15. Docker daemon config applied ───────────────────────
  - systemctl restart docker

  # ── 16. Signal completion and reboot ───────────────────────
  - |
    echo "=== Tranc3 Citadel cloud-init completed at $(date -u) ===" \
      >> /var/log/tranc3-bootstrap.log
  - reboot

# Increase cloud-init timeout for large package install + git clone
datasource:
  Oracle:
    get_root_password: false

final_message: |
  Tranc3 Citadel bootstrap complete.
  Domain:      ${domain}
  Environment: ${environment}
  Branch:      ${git_branch}
  The tranc3-citadel systemd service will start Docker Compose on next boot.
