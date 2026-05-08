# TRANC3 Makefile — RR Round 1 P2 action
# Usage: make dev | make test | make deploy | make setup

.PHONY: dev test deploy setup lint migrate clean frontend

# ── Setup ─────────────────────────────────────────────────────────────────────
setup:
	@echo "Setting up TRANC3..."
	pip install -r requirements.txt
	cp -n .env.example .env || true
	$(MAKE) migrate
	cd web && npm install
	@echo "Setup complete. Run 'make dev' to start."

# ── Development ───────────────────────────────────────────────────────────────
dev:
	@echo "Starting TRANC3 dev stack..."
	docker-compose up --build

dev-api:
	SECRET_KEY=dev-secret-key uvicorn api:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd web && npm run dev

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	@echo "Running database migrations..."
	alembic upgrade head

migrate-new:
	alembic revision --autogenerate -m "$(msg)"

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --cov=src --cov-report=term-missing

test-fast:
	pytest tests/ -v -x

test-load:
	locust -f tests/test_load.py --headless -u 10 -r 2 --run-time 30s --host http://localhost:8000

# ── Linting ───────────────────────────────────────────────────────────────────
lint:
	ruff check src/ api.py auth.py
	mypy src/ api.py --ignore-missing-imports

# ── Frontend ──────────────────────────────────────────────────────────────────
frontend:
	cd web && npm install && npm run build

# ── Deploy ────────────────────────────────────────────────────────────────────
deploy:
	docker-compose -f docker-compose.yml up -d --build

deploy-stop:
	docker-compose down

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

# ── Model ─────────────────────────────────────────────────────────────────────
download-model:
	@echo "Downloading phi-3-mini base model..."
	python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
		m = AutoModelForCausalLM.from_pretrained('microsoft/phi-3-mini-4k-instruct'); \
		t = AutoTokenizer.from_pretrained('microsoft/phi-3-mini-4k-instruct'); \
		m.save_pretrained('./models/phi3-base'); t.save_pretrained('./models/phi3-base'); \
		print('Model downloaded to ./models/phi3-base')"
