# Clone & setup
git clone <repo>
cd tranc3
chmod +x setup.sh
./setup.sh

# Local development
docker compose up --build

# Run tests
pytest --cov=src

# Deploy to K8s
kubectl apply -f deploy/k8s-baseline.yaml

# Monitor
open http://localhost:3001  # Grafana

# Load test
locust -f tests/test_load.py --host=http://localhost:8000
