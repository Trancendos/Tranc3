# TRANC3 Makefile
# Usage: make bootstrap | make dev | make test | make deploy | make doctor

.PHONY: dev test deploy setup bootstrap doctor monitor lint migrate clean frontend health health-json infra-plan swarm-run entity-audit ansible-health production-score dependency-audit

# ── Bootstrap (single-command platform setup) ─────────────────────────────────
bootstrap:
	@echo "Running Tranc3 platform bootstrap..."
	@bash scripts/bootstrap.sh --env dev

bootstrap-prod:
	@echo "Running Tranc3 production bootstrap..."
	@bash scripts/bootstrap.sh --env production --skip-deps

bootstrap-start:
	@echo "Bootstrapping and starting P0 workers..."
	@bash scripts/bootstrap.sh --env dev --start

# ── Doctor (validate platform health) ─────────────────────────────────────────
doctor:
	@echo "Tranc3 Platform Doctor"
	@echo "========================"
	@python3 -c "import sys; sys.path.insert(0,'.');  \
		pkgs = ['fastapi','pydantic','httpx','structlog','uvicorn'];  \
		[print(f'  OK  {p}') if __import__(p) else None for p in pkgs]"
	@echo "--- Advanced systems ---"
	@python3 -c "import sys; sys.path.insert(0,'.');  \
		opts = [('ncps','Liquid NNs'),('deap','Genetic GA'),('pygad','Simple GA'),  \
			('pyswarms','PSO'),('prometheus_client','Prometheus'),  \
			('opentelemetry.api','OTel API'),('cachetools','Cachetools'),  \
			('nats','NATS'),('diskcache','DiskCache')];  \
		[print(f'  OK  {l}') if __import__(p) is not None else None for p,l in opts if __import__(p,*(None,None,['']))is not None]" 2>/dev/null || true
	@echo "--- Worker requirements ---"
	@for d in workers/*/; do \
		if [ ! -f "$$d/requirements-worker.txt" ]; then \
			echo "  MISS $$d requirements-worker.txt"; \
		else \
			echo "  OK   $$d"; \
		fi; \
	done
	@echo "Doctor complete."

# ── Monitor (live worker health dashboard in terminal) ────────────────────────
monitor:
	@python3 scripts/monitor_p0_workers.py

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

# ── Platform Health Check ─────────────────────────────────────────────────────
health:
	@python3 scripts/health_check.py

health-json:
	@python3 scripts/health_check.py --json

swarm-run:
	@python3 scripts/swarm_runner.py --manifest config/swarm/manifests/platform-health.yaml

entity-audit:
	@python3 scripts/entity_registry_audit.py

ansible-health:
	@ansible-playbook -i deploy/ansible/inventory/workers.yml deploy/ansible/playbooks/health-probe.yml

deploy-citadel:
	@bash deploy/citadel/deploy-production.sh

citadel-preflight:
	@python3 scripts/citadel_preflight.py

branch-audit:
	@python3 scripts/branch_benefit_audit.py

pr-hygiene:
	@python3 scripts/pr_hygiene.py

pr-hygiene-apply:
	@python3 scripts/pr_hygiene.py --apply

zero-cost-audit:
	@python3 scripts/zero_cost_audit.py

production-score:
	@python3 scripts/production_readiness_score.py

dependency-audit:
	@python3 scripts/dependency_audit.py

# ── Infrastructure (OpenTofu) ─────────────────────────────────────────────────
infra-plan:
	@cd infrastructure/opentofu && tofu init -upgrade && tofu plan

infra-apply:
	@cd infrastructure/opentofu && tofu apply

infra-oracle-plan:
	@cd infrastructure/oracle-cloud && tofu init -upgrade && tofu plan

# ── SBOM ──────────────────────────────────────────────────────────────────────
sbom:
	@mkdir -p logs
	@syft . -o cyclonedx-json=logs/sbom-cyclonedx.json && echo "SBOM written to logs/sbom-cyclonedx.json"

# ── Model ─────────────────────────────────────────────────────────────────────
download-model:
	@echo "Downloading phi-3-mini base model..."
	python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
		m = AutoModelForCausalLM.from_pretrained('microsoft/phi-3-mini-4k-instruct'); \
		t = AutoTokenizer.from_pretrained('microsoft/phi-3-mini-4k-instruct'); \
		m.save_pretrained('./models/phi3-base'); t.save_pretrained('./models/phi3-base'); \
		print('Model downloaded to ./models/phi3-base')"

# ── Security ──────────────────────────────────────────────────────────────────
security-scan:
	bash scripts/security_scan.sh

security-install:
	pip install pip-audit==2.9.0 bandit==1.8.3 safety==3.5.1 semgrep==1.100.0 pre-commit==3.7.1 --quiet

pre-commit-install:
	pre-commit install
	pre-commit install --hook-type commit-msg

security-full: security-install security-scan
