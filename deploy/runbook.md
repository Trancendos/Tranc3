# TRANC3 Deployment Runbook

## Local Development

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Redis
- kubectl (for K8s testing)

### Start Stack
```bash
docker compose up --build
```

### Access
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Web: http://localhost:3000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)

### Test
```bash
pytest --cov=src
locust -f tests/test_load.py --host=http://localhost:8000
```

## Kubernetes Deployment

> **Not supported — documentation drift.** This section references
> `deploy/k8s-baseline.yaml`, `deploy/k8s-network-policy.yaml`, and
> `deploy/k8s-rbac.yaml`, none of which exist in this repo. A managed
> EKS/GKE/AKS cluster is also a paid service, contradicting the platform's
> zero-cost, self-hosted Docker Compose + Traefik architecture (see
> `CLAUDE.md`, `docs/DEPLOYMENT_RUNBOOK.md`). Treat this as aspirational/stale
> until the manifests are actually added — see `docker-compose.production.yml`
> and `deploy/DNS_CUTOVER.md` for the supported production path.

### Prerequisites
- EKS/GKE/AKS cluster (1.24+)
- kubectl configured
- Helm 3.x
- Ingress controller (nginx-ingress)

### Deploy
```bash
# Create namespace
kubectl create namespace tranc3

# Apply manifests
kubectl apply -f deploy/k8s-baseline.yaml
kubectl apply -f deploy/k8s-network-policy.yaml
kubectl apply -f deploy/k8s-rbac.yaml

# Verify
kubectl -n tranc3 get pods
kubectl -n tranc3 get svc
kubectl -n tranc3 get ingress
```

### Monitor
```bash
# Watch pods
kubectl -n tranc3 get pods -w

# View logs
kubectl -n tranc3 logs -f deployment/tranc3-api

# Check metrics
kubectl -n tranc3 top pods
```

### Scaling
```bash
# Manual scale
kubectl -n tranc3 scale deployment tranc3-api --replicas=5

# HPA status
kubectl -n tranc3 get hpa
```

### Rollback
```bash
kubectl -n tranc3 rollout history deployment/tranc3-api
kubectl -n tranc3 rollout undo deployment/tranc3-api --to-revision=1
```

## Troubleshooting

### Pod not starting
```bash
kubectl -n tranc3 describe pod <pod-name>
kubectl -n tranc3 logs <pod-name>
```

### High latency
- Check HPA: `kubectl -n tranc3 get hpa`
- Check metrics: http://localhost:3001 (Grafana)
- Check Redis: `redis-cli -h tranc3-redis ping`

### Memory leak
- Check logs for errors
- Restart pod: `kubectl -n tranc3 delete pod <pod-name>`
- Review model loading

## Backup & Recovery

### Backup Redis
```bash
kubectl -n tranc3 exec tranc3-redis -- redis-cli BGSAVE
kubectl -n tranc3 cp tranc3-redis:/data/dump.rdb ./backup.rdb
```

### Restore Redis
```bash
kubectl -n tranc3 cp ./backup.rdb tranc3-redis:/data/dump.rdb
kubectl -n tranc3 delete pod tranc3-redis-0
```

## SLOs & Alerts

### Target SLOs
- Availability: 99.9%
- Latency (p95): <1s
- Error rate: <0.1%
- Cache hit ratio: >70%

### Prometheus Alerts
See `deploy/prometheus-alerts.yaml`