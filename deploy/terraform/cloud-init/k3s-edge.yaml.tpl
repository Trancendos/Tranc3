#cloud-config
# ──────────────────────────────────────────────────────────────
# Tranc3 K3s Edge Node — Cloud-Init Template
# Bootstraps K3s lightweight Kubernetes on OCI A1 Flex (ARM)
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
  - socat
  - conntrack
  - iptables
  - chrony
  - logrotate
  - prometheus-node-exporter
  - softhsm2

write_files:
  # ── K3s Environment Configuration ──────────────────────
  - path: /etc/tranc3/k3s.env
    owner: root:root
    permissions: '0640'
    content: |
      TRANC3_ENVIRONMENT=${environment}
      TRANC3_SYSTEM_MODE=${system_mode}
      TRANC3_CRUSH_RULE=${crush_default_rule}
      TRANC3_HSM_PROVIDER=${hsm_provider}
      TRANC3_NANOSERVICE_IP=${nanoservice_private_ip}
      TRANC3_CEPH_IP=${ceph_private_ip}
      K3S_KUBECONFIG_MODE=644
      K3S_NODE_LABELS=tranc3.io/role=edge,tranc3.io/environment=${environment}

  # ── K3s Install Script ─────────────────────────────────
  - path: /opt/tranc3/install-k3s.sh
    owner: root:root
    permissions: '0755'
    content: |
      #!/bin/bash
      set -euo pipefail

      LOG_TAG="tranc3-k3s"
      logger -t "$LOG_TAG" "Starting K3s installation..."

      # ── Install K3s ────────────────────────────────────
      export K3S_KUBECONFIG_MODE="644"
      export INSTALL_K3S_EXEC="server \
        --cluster-init \
        --tls-san=$(hostname -I | awk '{print $1}') \
        --tls-san=tranc3-k3s.local \
        --write-kubeconfig-mode=644 \
        --kubelet-arg='max-pods=50' \
        --kubelet-arg='eviction-hard=memory.available<256Mi,nodefs.available<10%' \
        --kube-apiserver-arg='enable-admission-plugins=NodeRestriction,LimitRanger' \
        --disable=traefik \
        --disable=servicelb \
        --flannel-backend=wireguard-native \
        --node-label=tranc3.io/role=edge \
        --node-label=tranc3.io/environment=${environment} \
        --node-label=tranc3.io/system-mode=${system_mode}"

      curl -sfL https://get.k3s.io | sh -

      # ── Wait for K3s API ───────────────────────────────
      echo "Waiting for K3s API server..."
      for i in $(seq 1 60); do
          if k3s kubectl get nodes &>/dev/null; then
              echo "K3s API server is ready"
              break
          fi
          sleep 5
      done

      # ── Install Helm ───────────────────────────────────
      if ! command -v helm &>/dev/null; then
          logger -t "$LOG_TAG" "Installing Helm..."
          curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
      fi

      # ── Deploy Tranc3 Operator ─────────────────────────
      logger -t "$LOG_TAG" "Deploying Tranc3 operator..."
      if [ -d /opt/tranc3/helm/tranc3-operator ]; then
          helm upgrade --install tranc3-operator /opt/tranc3/helm/tranc3-operator \
              --namespace tranc3-system \
              --create-namespace \
              --set systemMode=${system_mode} \
              --set crushRule=${crush_default_rule} \
              --set hsm.provider=${hsm_provider} \
              --set nanoservice.endpoint="http://${nanoservice_private_ip}:8080" \
              --set ceph.rgwEndpoint="http://${ceph_private_ip}:7480" \
              --wait --timeout=300s
      else
          logger -t "$LOG_TAG" "Helm chart not found at /opt/tranc3/helm/tranc3-operator — deploy manually"
      fi

      logger -t "$LOG_TAG" "K3s installation completed"

  # ── K3s Service Override ───────────────────────────────
  - path: /etc/systemd/system/k3s.service.d/override.conf
    owner: root:root
    permissions: '0644'
    content: |
      [Service]
      EnvironmentFile=/etc/tranc3/k3s.env
      LimitNOFILE=65536
      CPUQuota=100%
      MemoryMax=3G

  # ── Tranc3 CRD Manifests ───────────────────────────────
  # Applied during bootstrap so the operator can reconcile immediately
  - path: /opt/tranc3/manifests/crds.yaml
    owner: root:root
    permissions: '0644'
    content: |
      # CRDs are deployed via Helm chart — this is a fallback
      # See: deploy/k3s/templates/crd.yaml

  # ── Logrotate ──────────────────────────────────────────
  - path: /etc/logrotate.d/tranc3-k3s
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

runcmd:
  # ── System Configuration ────────────────────────────────
  - sysctl -w vm.swappiness=10
  - sysctl -w net.core.somaxconn=65535
  - sysctl -w net.ipv4.tcp_max_syn_backlog=65535
  - sysctl -w net.bridge.bridge-nf-call-iptables=1 2>/dev/null || true

  # ── Create Tranc3 User ──────────────────────────────────
  - useradd -r -s /bin/false -d /var/lib/tranc3 tranc3 2>/dev/null || true
  - mkdir -p /etc/tranc3 /var/lib/tranc3 /var/log/tranc3 /opt/tranc3/helm /opt/tranc3/manifests

  # ── Initialize SoftHSM2 ─────────────────────────────────
  - |
      if [ "${hsm_provider}" = "softhsm2" ]; then
          if ! softhsm2-util --show-slots 2>/dev/null | grep -q "tranc3-hsm"; then
              softhsm2-util --init-token --slot 0 --label "tranc3-hsm" \
                  --pin "tranc3-hsm-pin" --so-pin "tranc3-hsm-so-pin"
          fi
      fi

  # ── Run K3s Installation ────────────────────────────────
  - /opt/tranc3/install-k3s.sh

  # ── Enable and Start Services ───────────────────────────
  - systemctl enable prometheus-node-exporter
  - systemctl start prometheus-node-exporter

  # ── Firewall Configuration ──────────────────────────────
  - iptables -A INPUT -p tcp --dport 6443 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 10250 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 8080 -s 10.0.0.0/16 -j ACCEPT
  - iptables -A INPUT -p tcp --dport 9100 -s 10.0.0.0/16 -j ACCEPT
  - netfilter-persistent save 2>/dev/null || true

  # ── Copy Kubeconfig for Remote Access ───────────────────
  - mkdir -p /home/ubuntu/.kube
  - cp /etc/rancher/k3s/k3s.yaml /home/ubuntu/.kube/config 2>/dev/null || true
  - chown -R ubuntu:ubuntu /home/ubuntu/.kube 2>/dev/null || true

final_message: "Tranc3 K3s Edge node boot complete on $INSTANCE_ID at $TIMESTAMP"
