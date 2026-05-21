# 1. Setup Environment
git clone <repo>
cd tranc3
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Prepare Data
python scripts/prepare_data.py

# 3. Train Tokenizer
python scripts/train_tokenizer.py

# 4. Train Model
python scripts/train.py --config configs/default.yaml

# 5. Interactive Testing
python scripts/chat.py

# 6. Docker Deployment
docker-compose up -d
docker-compose logs -f

# 7. Production (Kubernetes)
kubectl apply -f k8s/deployment.yaml
kubectl scale deployment tranc3 --replicas=3
