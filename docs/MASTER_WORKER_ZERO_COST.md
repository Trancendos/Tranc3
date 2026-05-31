# Master Worker / Bot Swarm — Zero-Cost Architecture

## Your question: Ansible free tier?

**Yes.** Use **Ansible Core** (open source, GPL) — free forever for testing and production.

| Tool | Cost | Use case |
|---|---|---|
| **Ansible Core** | $0 | Push config, deploy workers, run health playbooks from a control node |
| **AWX** | $0 (upstream of Ansible Automation Platform) | Web UI + job templates + credentials vault integration |
| **Semaphore** | $0 (MIT) | Lighter UI alternative to AWX |
| **OpenTofu** | $0 | Already in repo (`infrastructure/opentofu/`) — provision VMs, not configure them |

Ansible complements (does not replace) your Python workers: **provision with OpenTofu/OCI free tier → configure with Ansible → run apps with Docker Compose / K3s**.

Example test playbook layout:

```yaml
# deploy/ansible/playbooks/workers.yml
- hosts: citadel
  tasks:
    - name: Ensure worker env file
      template:
        src: templates/worker.env.j2
        dest: /etc/tranc3/workers/{{ item.name }}.env
      loop: "{{ tranc3_workers }}"  # from group_vars/all.yml
    - name: Health check worker
      uri:
        url: "http://127.0.0.1:{{ item.port }}/health"
        status_code: 200
      loop: "{{ tranc3_workers }}"
```

Define workers in **YAML** (`deploy/ansible/inventory/workers.yml`) — same pattern you described for task association.

---

## Master Worker / Master Bot concept

A **Master Orchestrator** (Tier 1 — Cornelius MacIntyre domain) dispatches **task manifests** to Tier 5 bots:

```yaml
# config/swarm/manifests/nightly-health.yaml
manifest_version: "1"
orchestrator: cornelius-macintyre
tasks:
  - id: probe-all-p0-workers
    bot: health-probe-bot
    targets: "@inventory/p0_workers"
    schedule: "0 */6 * * *"
  - id: dependency-audit
    bot: n1-checker-bot
    script: scripts/n1_checker.py
    notify: sentinel:platform
```

**Implementation path (already partially in repo):**

| Piece | Location | Status |
|---|---|---|
| Task queue | `workers/queue-service` (The HIVE) | Deployed pattern |
| Cron | `workers/cron-service` (ChronosSphere) | P3 worker |
| Event bus | `src/event_bus/` + optional NATS | On consolidation branch |
| Sentinel events | `Dimensional/infinity/sentinel_station.py` | Wired in Admin |
| Health probe script | `scripts/health_check.py` | Added PR #84 |

**Master scraper** = Tier 5 bot at The Dutchy (`Scraper-Bot`, `Crawler-Bot`) — already in `PLATFORM_ENTITIES.md`. Manifest-driven runs avoid a monolithic scraper.

---

## JSON/YAML task association

Recommended files:

```
config/swarm/
  manifests/          # what to run
  inventory/          # where (hosts, worker ports)
  policies/           # RBAC, rate limits
workers/
  swarm-coordinator/  # future: reads manifests, enqueues to queue-service
```

**Do not** build one mega-process — use **nanoservice swarm** (many small bots + queue) per your architecture principles.

---

## Zero-cost proactive automation stack

| Layer | Technology | Cost |
|---|---|---|
| CI/CD | Forgejo + act-runner | $0 self-hosted |
| CVE scan | OSV-Scanner, pip-audit, Renovate | $0 |
| Metrics | Prometheus + VictoriaMetrics (consolidation) | $0 |
| Logs | Loki + Promtail | $0 |
| Traces | Tempo / SigNoz config in repo | $0 self-host |
| Alerts | Prometheus alert rules + Sentinel | $0 |
| Config | Infinity-Admin + Ansible | $0 |
| AI inference | Ollama local → OpenRouter :free | $0 tier |

---

## Honest gaps

- **No `swarm-coordinator` worker yet** — manifests are a design, not fully implemented.
- **NATS optional** — event bus works in-process without `NATS_URL`.
- **Ansible playbooks not in repo** — add under `deploy/ansible/` as next increment.

Proceed: merge consolidation → add Ansible playbooks → implement manifest reader in `cron-service` or new P3 worker.
