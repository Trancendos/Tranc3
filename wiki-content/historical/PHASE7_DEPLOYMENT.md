# Tranc3 Phase 7 — Deployment Guide

## Prerequisites

### Infrastructure Requirements
- **k3s cluster** — 3+ nodes recommended for production, 1 node for development
- **Forgejo instance** — Self-hosted at `forgejo.local` (or your domain)
- **Ollama** — Running with at least one model (e.g., `ollama pull llama3`)
- **Redpanda** — For DaaS streaming (optional for development)
- **OPA** — For DaaS policy enforcement (optional for development)

### Software Requirements
- Python 3.11+
- Go 1.21+ (for compiling DNF Orchestrator and NSA Client)
- Rust toolchain (for compiling NSA Broker)
- kubectl configured for your k3s cluster
- FluxCD CLI (`flux`)

---

## Step 1: Set Up Forgejo

### 1.1 Deploy Forgejo (if not already running)

```bash
# Using k3s
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: forgejo
  namespace: gitops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: forgejo
  template:
    metadata:
      labels:
        app: forgejo
    spec:
      containers:
        - name: forgejo
          image: codeberg.org/forgejo/forgejo:7.0
          ports:
            - containerPort: 3000
            - containerPort: 22
          volumeMounts:
            - name: forgejo-data
              mountPath: /data
      volumes:
        - name: forgejo-data
          persistentVolumeClaim:
            claimName: forgejo-pvc
EOF
```

### 1.2 Create Repository

1. Navigate to your Forgejo instance
2. Create organization `Trancendos`
3. Create repository `Tranc3` under `Trancendos`
4. Push the Tranc3 codebase:
   ```bash
   git remote add forgejo https://forgejo.local/Trancendos/Tranc3.git
   git push forgejo main
   ```

### 1.3 Create Access Token

1. Go to Settings → Applications → Access Tokens
2. Create a token with `repo` and `workflow` scopes
3. Save the token as a Kubernetes secret:
   ```bash
   kubectl create secret generic forgejo-auth \
     --from-literal=username=fluxcd \
     --from-literal=password=YOUR_TOKEN \
     -n flux-system
   ```

---

## Step 2: Install FluxCD on k3s

```bash
# Install FluxCD
curl -s https://fluxcd.io/install.sh | sudo bash

# Bootstrap FluxCD with Forgejo (NOT GitHub)
flux bootstrap git \
  --url=https://forgejo.local/Trancendos/Tranc3.git \
  --branch=main \
  --path=flux/flux-system.yaml \
  --token-auth

# Verify FluxCD is running
kubectl get pods -n flux-system
```

---

## Step 3: Deploy Base Infrastructure

```bash
# Apply the FluxCD system manifests
kubectl apply -f flux/flux-system.yaml

# Watch FluxCD reconcile
flux get kustomizations --watch

# Verify namespace creation
kubectl get namespace tranc3

# Verify deployments
kubectl get deployments -n tranc3
```

---

## Step 4: Deploy Environment Overlays

### Development
```bash
# Apply development overlay
kubectl apply -k flux/overlays/dev/

# Verify (single replica, debug logging)
kubectl get pods -n tranc3-dev
kubectl logs -n tranc3-dev -l app=nsa-broker --tail=20
```

### Staging
```bash
# Apply staging overlay
kubectl apply -k flux/overlays/staging/

# Verify (2 replicas, info logging)
kubectl get pods -n tranc3-staging
```

### Production
```bash
# Apply production overlay (FluxCD handles this automatically)
# The production Kustomization is defined in flux-system.yaml
flux reconcile kustomization tranc3-production --with-source

# Verify (3 replicas, HA, topology spread)
kubectl get pods -n tranc3
kubectl get pods -n tranc3 -o wide  # Should be across different nodes/zones
```

---

## Step 5: Set Up Ollama for SHI

```bash
# Deploy Ollama to k3s
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: tranc3
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
        - name: ollama
          image: ollama/ollama:latest
          ports:
            - containerPort: 11434
          volumeMounts:
            - name: ollama-data
              mountPath: /root/.ollama
          resources:
            limits:
              nvidia.com/gpu: 1  # If GPU available
      volumes:
        - name: ollama-data
          persistentVolumeClaim:
            claimName: ollama-pvc
EOF

# Pull a model
kubectl exec -it deployment/ollama -n tranc3 -- ollama pull llama3

# Verify SHI Gateway can connect
kubectl exec -it deployment/shi-gateway -n tranc3 -- curl -s http://ollama:11434/api/tags
```

---

## Step 6: Set Up Redpanda for DaaS

```bash
# Deploy Redpanda using Helm
helm repo add redpanda https://charts.redpanda.com
helm repo update
helm install redpanda redpanda/redpanda \
  --namespace tranc3 \
  --set auth.sasl.enabled=false

# Verify Redpanda is running
kubectl exec -it deployment/redpanda -n tranc3 -- rpk cluster info
```

---

## Step 7: Set Up OPA for DaaS

```bash
# Deploy OPA
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opa
  namespace: tranc3
spec:
  replicas: 1
  selector:
    matchLabels:
      app: opa
  template:
    metadata:
      labels:
        app: opa
    spec:
      containers:
        - name: opa
          image: openpolicyagent/opa:latest
          args: ["run", "--server", "--addr", ":8181"]
          ports:
            - containerPort: 8181
EOF

# Load DaaS sovereignty policies
# The DaaSService.generate_rego_bundle() method generates the Rego bundle
PYTHONPATH=src python -c "
from nanoservices.daas_stream import DaaSService
service = DaaSService()
bundle = service.generate_rego_bundle()
with open('/tmp/daas-policies.tar.gz', 'wb') as f:
    f.write(bundle)
print(f'Generated Rego bundle: {len(bundle)} bytes')
"

# Upload to OPA
kubectl cp /tmp/daas-policies.tar.gz opa:/policies/ -n tranc3
```

---

## Step 8: Verify the Full Stack

```bash
# Check all deployments are healthy
kubectl get deployments -n tranc3

# Check NSA Broker health
kubectl exec -it deployment/nsa-broker -n tranc3 -- curl -s http://localhost:7780/health

# Check SHI Gateway health
kubectl exec -it deployment/shi-gateway -n tranc3 -- curl -s http://localhost:8000/health

# Check DNF Orchestrator health
kubectl exec -it deployment/dnf-orchestrator -n tranc3 -- curl -s http://localhost:8080/health

# Run Phase 7 integration tests from within the cluster
kubectl exec -it deployment/shi-gateway -n tranc3 -- \
  python -m pytest tests/test_phase7.py -v
```

---

## Step 9: Configure Drift Detection

The IGI Drift Detector runs as part of the GitOps reconciliation loop. To configure:

```python
from nanoservices.igi_gitops import IGIGitOps, DriftDetector, ForgejoConfig

# Configure Forgejo connection
forgejo = ForgejoConfig(
    url="https://forgejo.local",
    repository="Trancendos/Tranc3",
    branch="main",
    flux_path="flux/"
)

# Create drift detector with auto-healing
detector = DriftDetector(
    forgejo_config=forgejo,
    auto_heal=True,
    check_interval_seconds=30
)

# Start monitoring (runs in background)
detector.start()

# Check current drift status
drifts = detector.check_drift()
for drift in drifts:
    print(f"[{drift.severity.value}] {drift.resource_type}/{drift.resource_name}: {drift.drift_type}")
```

---

## Step 10: Set Up CI/CD

The Forgejo CI workflow is already configured at `.forgejo/workflows/phase7-nanoservices.yml`. To enable:

1. Ensure your Forgejo runner is registered:
   ```bash
   # On the runner machine
   forgejo-runner register \
     --instance https://forgejo.local \
     --token YOUR_RUNNER_TOKEN \
     --name tranc3-runner
   ```

2. The workflow automatically triggers on:
   - Push to any branch that touches `src/nanoservices/`, `flux/`, or `tests/test_phase7.py`
   - Pull requests to `main`
   - Manual dispatch via Forgejo UI

3. Verify the CI pipeline:
   - Push a change to `src/nanoservices/`
   - Check the Actions tab in Forgejo
   - All 5 jobs should pass: Import Check, Integration Tests, Go Validation, FluxCD Validation, Zero-Cost Audit

---

## Troubleshooting

### NSA Broker won't start
- Verify `hostIPC: true` is set in the deployment
- Check `/dev/shm` is accessible: `ls -la /dev/shm`
- Ensure no other process is using the `nsa_` prefix: `ls /dev/shm/nsa_*`

### SHI Gateway can't connect to Ollama
- Verify Ollama is running: `curl http://ollama:11434/api/tags`
- Check the `OLLAMA_HOST` environment variable
- Ensure at least one model is pulled: `kubectl exec -it deployment/ollama -- ollama list`

### FluxCD not reconciling
- Check FluxCD logs: `kubectl logs -n flux-system -l app=fluxcd`
- Verify Forgejo authentication: `kubectl get secret forgejo-auth -n flux-system`
- Force reconciliation: `flux reconcile kustomization tranc3-base --with-source`

### Drift detection triggering false positives
- Review drift classification thresholds in `igi_gitops.py`
- Add specific resources to the ignore list
- Adjust the health check interval

### DaaS policies blocking legitimate requests
- Review OPA policies: `curl http://opa:8181/v1/policies`
- Check data classification levels
- Verify jurisdiction settings match your deployment region

---

## Cost Summary

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Forgejo | $0 | Self-hosted |
| k3s | $0 | Open-source |
| FluxCD | $0 | Open-source |
| Ollama | $0 | Self-hosted |
| vLLM | $0 | Open-source |
| Redpanda Community | $0 | BSL-1.1, free for non-production |
| OPA | $0 | Open-source |
| Qiskit | $0 | Open-source |
| PyTorch | $0 | Open-source |
| Python/Go/Rust | $0 | Open-source |
| **Total** | **$0** | **Zero-cost mandate satisfied** |
