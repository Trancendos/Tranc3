#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# Tranc3 Platform — Citadel Provisioning Orchestrator
# ══════════════════════════════════════════════════════════════════
#
# Single entry-point for all Citadel lifecycle operations:
#   --init    First-time: terraform init+apply, then ansible setup
#   --deploy  Subsequent: git pull + docker compose up via ansible
#   --plan    Terraform plan only (dry run)
#   --destroy Terraform destroy (requires --confirm)
#   --status  SSH to Citadel and report docker ps + health
#   --ssh     Open interactive SSH session to Citadel
#
# Prerequisites (checked at startup):
#   terraform, ansible, ansible-playbook, jq, ssh-keygen
#
# Usage:
#   ./scripts/provision-citadel.sh --init
#   ./scripts/provision-citadel.sh --deploy
#   ./scripts/provision-citadel.sh --plan
#   ./scripts/provision-citadel.sh --status
#   ./scripts/provision-citadel.sh --ssh
#   ./scripts/provision-citadel.sh --destroy --confirm
#
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${REPO_ROOT}/deploy/terraform"
ANSIBLE_DIR="${REPO_ROOT}/deploy/ansible"
INVENTORY="${ANSIBLE_DIR}/inventory/citadel.yml"
SETUP_PLAYBOOK="${ANSIBLE_DIR}/playbooks/citadel-setup.yml"
DEPLOY_PLAYBOOK="${ANSIBLE_DIR}/playbooks/citadel-deploy.yml"
SSH_KEY="${HOME}/.ssh/tranc3_citadel"

# ── Colour helpers ────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

step()  { echo -e "\n${BOLD}${BLUE}▶ $*${RESET}"; }
ok()    { echo -e "${GREEN}✔ $*${RESET}"; }
warn()  { echo -e "${YELLOW}⚠ $*${RESET}"; }
error() { echo -e "${RED}✘ $*${RESET}" >&2; exit 1; }
info()  { echo -e "${CYAN}  $*${RESET}"; }

# ── Usage ─────────────────────────────────────────────────────
usage() {
  cat <<EOF
${BOLD}Tranc3 Citadel Provisioning Orchestrator${RESET}

Usage: $(basename "$0") [OPTION]

Options:
  --init          First-time provision: terraform init → plan → apply → ansible setup
  --deploy        Rolling deploy: git pull + docker compose up via ansible
  --plan          Terraform plan only (dry run, no changes)
  --destroy       Terraform destroy (DANGEROUS — requires --confirm)
  --confirm       Required alongside --destroy to execute destruction
  --status        SSH to Citadel and report docker ps + health endpoints
  --ssh           Open interactive SSH session to Citadel
  --help          Show this help

Environment variables:
  TF_VAR_*        Pass any Terraform variable (see terraform.tfvars.example)
  ANSIBLE_EXTRA   Extra args to pass to ansible-playbook
  SSH_KEY         Override SSH key path (default: ~/.ssh/tranc3_citadel)

Examples:
  # First-time setup from scratch:
  ./scripts/provision-citadel.sh --init

  # Deploy latest code to Citadel:
  ./scripts/provision-citadel.sh --deploy

  # Plan only — review changes before applying:
  ./scripts/provision-citadel.sh --plan

  # Check what's running on Citadel:
  ./scripts/provision-citadel.sh --status

  # Open a shell on Citadel:
  ./scripts/provision-citadel.sh --ssh

  # Destroy ALL infrastructure (destructive — requires confirmation):
  ./scripts/provision-citadel.sh --destroy --confirm

SSH key setup (one time):
  ssh-keygen -t ed25519 -C "tranc3-citadel" -f ~/.ssh/tranc3_citadel
  # Then add the public key to terraform.tfvars:
  echo "ssh_public_key = \"\$(cat ~/.ssh/tranc3_citadel.pub)\""
EOF
}

# ── Prerequisite check ────────────────────────────────────────
check_prerequisites() {
  step "Checking prerequisites"
  local missing=()

  for cmd in terraform ansible ansible-playbook jq ssh; do
    if command -v "$cmd" &>/dev/null; then
      ok "$cmd found: $(command -v "$cmd")"
    else
      missing+=("$cmd")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing required tools: ${missing[*]}
Install them with:
  sudo apt-get install -y ansible jq openssh-client
  # Terraform: https://developer.hashicorp.com/terraform/install"
  fi

  # Check Terraform version
  TF_VERSION=$(terraform version -json 2>/dev/null | jq -r '.terraform_version' 2>/dev/null || echo "unknown")
  info "Terraform version: ${TF_VERSION}"

  # Check Ansible version
  ANSIBLE_VERSION=$(ansible --version 2>/dev/null | head -1 || echo "unknown")
  info "Ansible: ${ANSIBLE_VERSION}"
}

# ── tfvars validation ─────────────────────────────────────────
check_tfvars() {
  step "Validating Terraform configuration"

  if [[ ! -f "${TF_DIR}/terraform.tfvars" ]]; then
    warn "terraform.tfvars not found at ${TF_DIR}/terraform.tfvars"
    warn "Copy the example and fill in your values:"
    warn "  cp ${TF_DIR}/terraform.tfvars.example ${TF_DIR}/terraform.tfvars"
    warn "  $EDITOR ${TF_DIR}/terraform.tfvars"
    error "Cannot proceed without terraform.tfvars (or TF_VAR_* environment variables)"
  fi
  ok "terraform.tfvars found"
}

# ── Inventory validation ──────────────────────────────────────
check_inventory() {
  if [[ ! -f "${INVENTORY}" ]]; then
    warn "Ansible inventory not found: ${INVENTORY}"
    warn "Run --init first (it auto-generates inventory after terraform apply),"
    warn "or copy the example manually:"
    warn "  cp ${ANSIBLE_DIR}/inventory/citadel.yml.example ${INVENTORY}"
    return 1
  fi
  ok "Ansible inventory found: ${INVENTORY}"
  return 0
}

# ── Read terraform output ─────────────────────────────────────
get_citadel_ip() {
  (cd "${TF_DIR}" && terraform output -raw citadel_public_ip 2>/dev/null) || echo ""
}

get_tf_outputs() {
  (cd "${TF_DIR}" && terraform output -json 2>/dev/null) || echo "{}"
}

# ── Write ansible inventory from terraform outputs ────────────
write_inventory() {
  local ip="$1"
  local branch="${2:-main}"

  if [[ -z "$ip" ]]; then
    warn "Cannot write inventory — citadel_public_ip is empty"
    return
  fi

  step "Writing Ansible inventory → ${INVENTORY}"
  mkdir -p "$(dirname "${INVENTORY}")"

  cat > "${INVENTORY}" <<YAML
# Auto-generated by provision-citadel.sh — do not edit manually.
# Regenerate with: ./scripts/provision-citadel.sh --init
all:
  hosts:
    citadel:
      ansible_host: "${ip}"
      ansible_user: tranc3
      ansible_ssh_private_key_file: ${SSH_KEY}
      ansible_python_interpreter: /usr/bin/python3
  vars:
    domain: trancendos.com
    git_branch: "${branch}"
    deploy_profile: core
    tranc3_root: /opt/tranc3
    compose_file: docker-compose.production.yml
    health_check_timeout_sec: 120
YAML

  ok "Inventory written with Citadel IP: ${ip}"
}

# ── Terraform init ────────────────────────────────────────────
cmd_tf_init() {
  step "Terraform init"
  (cd "${TF_DIR}" && terraform init -upgrade)
  ok "Terraform initialised"
}

# ── Terraform plan ────────────────────────────────────────────
cmd_plan() {
  check_prerequisites
  check_tfvars
  step "Terraform plan (dry run)"
  (cd "${TF_DIR}" && terraform plan -out="${TF_DIR}/citadel.tfplan")
  ok "Plan saved to ${TF_DIR}/citadel.tfplan"
  info "Review the plan above. Run --init to apply."
}

# ── First-time init + apply + ansible setup ───────────────────
cmd_init() {
  check_prerequisites
  check_tfvars

  # SSH key guidance
  if [[ ! -f "${SSH_KEY}" ]]; then
    warn "SSH key not found at ${SSH_KEY}"
    warn "Generate one now:"
    warn "  ssh-keygen -t ed25519 -C 'tranc3-citadel' -f ${SSH_KEY}"
    warn "Then add the public key to terraform.tfvars:"
    warn "  ssh_public_key = \"\$(cat ${SSH_KEY}.pub)\""
    read -rp "Continue without key check? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || error "Aborted. Set up the SSH key first."
  else
    ok "SSH key found: ${SSH_KEY}"
  fi

  # Add host key checking disable for first connection
  SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=30"

  # 1. Terraform init
  cmd_tf_init

  # 2. Terraform plan
  step "Terraform plan"
  (cd "${TF_DIR}" && terraform plan -out="${TF_DIR}/citadel.tfplan")

  # 3. Confirm apply
  echo ""
  warn "This will provision the Citadel instance on Oracle Cloud."
  warn "Estimated time: 5–10 minutes for instance + cloud-init."
  read -rp "Apply Terraform plan? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || error "Aborted."

  # 4. Terraform apply
  step "Terraform apply"
  (cd "${TF_DIR}" && terraform apply "${TF_DIR}/citadel.tfplan")
  ok "Terraform apply complete"

  # 5. Extract outputs
  step "Reading Terraform outputs"
  local citadel_ip
  citadel_ip=$(get_citadel_ip)
  if [[ -z "$citadel_ip" ]]; then
    error "Could not read citadel_public_ip from Terraform outputs"
  fi
  local git_branch
  git_branch=$(cd "${TF_DIR}" && terraform output -raw git_branch 2>/dev/null || echo "main")

  info "Citadel public IP : ${citadel_ip}"
  info "SSH command       : ssh -i ${SSH_KEY} tranc3@${citadel_ip}"

  # 6. Write ansible inventory
  write_inventory "$citadel_ip" "$git_branch"

  # 7. Wait for cloud-init to complete (typically 5–8 min)
  step "Waiting for cloud-init to complete (up to 15 minutes)..."
  info "Cloud-init installs Docker, clones the repo, and configures UFW."
  info "You can monitor it with:"
  info "  ssh -i ${SSH_KEY} ubuntu@${citadel_ip} 'sudo tail -f /var/log/cloud-init-output.log'"
  echo ""
  warn "Sleeping 120 seconds before attempting Ansible connection..."
  sleep 120

  # 8. Run ansible setup
  step "Running Ansible setup playbook"
  ANSIBLE_HOST_KEY_CHECKING=False \
  ansible-playbook \
    -i "${INVENTORY}" \
    "${SETUP_PLAYBOOK}" \
    ${ANSIBLE_EXTRA:-} \
    -v
  ok "Ansible setup complete"

  # 9. Final summary
  echo ""
  echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}${GREEN}║         Tranc3 Citadel — Provisioning Complete!         ║${RESET}"
  echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════╝${RESET}"
  echo ""
  info "Citadel IP    : ${citadel_ip}"
  info "SSH command   : ssh -i ${SSH_KEY} tranc3@${citadel_ip}"
  info "Traefik dash  : http://${citadel_ip}:8888"
  info "API health    : https://api.trancendos.com/health  (after DNS cutover)"
  echo ""
  warn "Next steps:"
  warn "  1. Point DNS: see deploy/DNS_CUTOVER.md"
  warn "  2. Verify TLS: curl https://trancendos.com/health"
  warn "  3. Run UAT: pytest tests/test_uat.py -v"
}

# ── Rolling deployment ────────────────────────────────────────
cmd_deploy() {
  check_prerequisites

  if ! check_inventory; then
    local citadel_ip
    citadel_ip=$(get_citadel_ip)
    if [[ -n "$citadel_ip" ]]; then
      write_inventory "$citadel_ip"
    else
      error "No inventory file and no Terraform state. Run --init first."
    fi
  fi

  step "Rolling deployment via Ansible"
  ANSIBLE_HOST_KEY_CHECKING=False \
  ansible-playbook \
    -i "${INVENTORY}" \
    "${DEPLOY_PLAYBOOK}" \
    ${ANSIBLE_EXTRA:-} \
    -v
  ok "Deployment complete"
}

# ── Status check ──────────────────────────────────────────────
cmd_status() {
  local citadel_ip
  citadel_ip=$(get_citadel_ip)

  if [[ -z "$citadel_ip" ]]; then
    if check_inventory; then
      citadel_ip=$(grep "ansible_host:" "${INVENTORY}" | awk '{print $2}' | tr -d '"' | head -1)
    fi
  fi

  [[ -z "$citadel_ip" ]] && error "Cannot determine Citadel IP. Run --init or check ${INVENTORY}."

  step "Citadel status check — ${citadel_ip}"
  info "Connecting as tranc3@${citadel_ip}..."

  SSH_CMD="ssh -i ${SSH_KEY} -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new tranc3@${citadel_ip}"

  echo ""
  step "Docker Compose services"
  $SSH_CMD "cd /opt/tranc3 && docker compose -f docker-compose.production.yml ps --format table" || \
    warn "Could not retrieve docker ps (is compose stack running?)"

  echo ""
  step "P0/P1 health endpoints"
  local ports=(8000 8004 8005 8006 8007 8042 8043 8044 8040 8060 8070)
  local names=("api-gateway" "infinity-ws" "infinity-auth" "users-service" "monitoring" "infinity-portal" "infinity-one" "infinity-admin" "gateway" "hive" "infinity-bridge")

  for i in "${!ports[@]}"; do
    local port="${ports[$i]}"
    local name="${names[$i]}"
    local result
    result=$($SSH_CMD "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:${port}/health 2>/dev/null || echo '000'")
    if [[ "$result" == "200" ]]; then
      ok "  ${name}:${port}/health → HTTP ${result}"
    else
      warn "  ${name}:${port}/health → HTTP ${result}"
    fi
  done

  echo ""
  step "System resources"
  $SSH_CMD "echo '--- Disk ---'; df -h /opt/tranc3 /; echo '--- Memory ---'; free -h; echo '--- Load ---'; uptime" || true
}

# ── SSH session ───────────────────────────────────────────────
cmd_ssh() {
  local citadel_ip
  citadel_ip=$(get_citadel_ip)

  if [[ -z "$citadel_ip" ]]; then
    if check_inventory 2>/dev/null; then
      citadel_ip=$(grep "ansible_host:" "${INVENTORY}" | awk '{print $2}' | tr -d '"' | head -1)
    fi
  fi

  [[ -z "$citadel_ip" ]] && error "Cannot determine Citadel IP. Run --init first."

  step "Opening SSH session → tranc3@${citadel_ip}"
  exec ssh -i "${SSH_KEY}" \
    -o StrictHostKeyChecking=accept-new \
    -o ServerAliveInterval=60 \
    tranc3@"${citadel_ip}"
}

# ── Destroy ───────────────────────────────────────────────────
cmd_destroy() {
  local confirmed="${1:-no}"

  check_prerequisites
  check_tfvars

  if [[ "$confirmed" != "yes" ]]; then
    error "--destroy requires --confirm flag. This is DESTRUCTIVE and irreversible.
Usage: $(basename "$0") --destroy --confirm"
  fi

  warn "╔══════════════════════════════════════════════════════════╗"
  warn "║  ⚠  DESTRUCTIVE OPERATION — CANNOT BE UNDONE  ⚠       ║"
  warn "╚══════════════════════════════════════════════════════════╝"
  warn ""
  warn "This will PERMANENTLY DESTROY:"
  warn "  - The Citadel compute instance"
  warn "  - Its reserved public IP"
  warn "  - Network Security Groups"
  warn "  - All associated OCI resources"
  warn ""
  warn "The instance has lifecycle { prevent_destroy = true }."
  warn "Terraform will refuse to destroy it unless you first remove"
  warn "or comment out that block in oci-citadel.tf."
  warn ""
  read -rp "Type 'DESTROY CITADEL' to confirm: " final_confirm
  [[ "$final_confirm" == "DESTROY CITADEL" ]] || error "Confirmation mismatch. Aborted."

  step "Terraform destroy (targeting citadel resources only)"
  (cd "${TF_DIR}" && terraform destroy \
    -target=oci_core_instance.citadel \
    -target=oci_core_public_ip.citadel \
    -target=oci_core_network_security_group.citadel)
  ok "Citadel resources destroyed"
}

# ── Main ──────────────────────────────────────────────────────
main() {
  local cmd=""
  local do_confirm="no"

  [[ $# -eq 0 ]] && { usage; exit 0; }

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --init)    cmd="init"    ;;
      --deploy)  cmd="deploy"  ;;
      --plan)    cmd="plan"    ;;
      --destroy) cmd="destroy" ;;
      --status)  cmd="status"  ;;
      --ssh)     cmd="ssh"     ;;
      --confirm) do_confirm="yes" ;;
      --help|-h) usage; exit 0 ;;
      *) error "Unknown option: $1. Use --help for usage." ;;
    esac
    shift
  done

  [[ -z "$cmd" ]] && { usage; exit 1; }

  echo -e "${BOLD}${CYAN}"
  echo "  ████████╗██████╗  █████╗ ███╗   ██╗ ██████╗██████╗"
  echo "  ╚══██╔══╝██╔══██╗██╔══██╗████╗  ██║██╔════╝╚════██╗"
  echo "     ██║   ██████╔╝███████║██╔██╗ ██║██║      █████╔╝"
  echo "     ██║   ██╔══██╗██╔══██║██║╚██╗██║██║      ╚═══██╗"
  echo "     ██║   ██║  ██║██║  ██║██║ ╚████║╚██████╗██████╔╝"
  echo "     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═════╝"
  echo -e "${RESET}"
  echo -e "${BOLD}  Citadel Provisioning — ${cmd}${RESET}"
  echo ""

  case "$cmd" in
    init)    cmd_init ;;
    deploy)  cmd_deploy ;;
    plan)    cmd_plan ;;
    destroy) cmd_destroy "$do_confirm" ;;
    status)  cmd_status ;;
    ssh)     cmd_ssh ;;
  esac
}

main "$@"
