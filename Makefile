# TRANC3 Makefile
# Usage: make setup-dev | make dev-api | make test | make doctor | make compliance-check

.PHONY: dev test deploy setup setup-dev setup-env setup-prod bootstrap bootstrap-prod bootstrap-start \
        doctor monitor lint migrate migrate-new clean \
        frontend frontend-check frontend-docker frontend-ci \
        health health-json infra-plan infra-apply infra-oracle-plan \
        swarm-run entity-audit ansible-health production-score \
        dependency-audit compliance-check compliance-report compliance-ci compliance-merged \
        security-scan security-install security-full pre-commit-install \
        gate-check zero-cost-status backup-status backup-all dr-drill dr-verify \
        perf-gate perf-gate-update sbom download-model dev-api dev-web \
        submodules check-env \
        deploy-dev deploy-staging deploy-prod deploy-verify deploy-rollback

# ── First-time setup (single command) ─────────────────────────────────────────
# Recommended entry point for new developers or CI environments.
# Detects running services, generates .env with real secrets, creates data dirs,
# wires submodules, installs Python deps, and applies DB schema.
setup-dev:
	@echo ""
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║        Tranc3 — Local Development Setup         ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@echo ""
	@echo "1/5  Installing Python dependencies..."
	@pip install -r requirements.txt -r requirements-test.txt --quiet --no-warn-script-location
	@echo "2/5  Generating .env (auto-detecting services, generating secrets)..."
	@python scripts/generate_env.py
	@echo "3/5  Wiring git submodules (Magna-Carta + CranBania)..."
	@bash scripts/setup_external_repos.sh 2>/dev/null || true
	@echo "4/5  Applying database schema..."
	@python -m alembic upgrade head 2>/dev/null || echo "     Note: DB migration skipped (no DB running — SQLite will auto-create on first start)"
	@echo "5/5  Validating environment..."
	@python scripts/generate_env.py --check --quiet
	@echo ""
	@echo "✓ Setup complete! Run 'make dev-api' to start the backend."
	@echo ""

# ── Production setup ──────────────────────────────────────────────────────────
setup-prod:
	@echo "Running production environment setup..."
	@pip install -r requirements.txt --quiet --no-warn-script-location
	@python scripts/generate_env.py --prod
	@bash scripts/setup_external_repos.sh
	@python -m alembic upgrade head
	@python scripts/generate_env.py --check

# ── .env generation only ──────────────────────────────────────────────────────
setup-env:
	@python scripts/generate_env.py

setup-env-force:
	@python scripts/generate_env.py --force

# ── Validate .env ─────────────────────────────────────────────────────────────
check-env:
	@python scripts/generate_env.py --check

# ── Submodules ────────────────────────────────────────────────────────────────
submodules:
	@bash scripts/setup_external_repos.sh

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
	@echo "Monitoring P0/P1 workers..."
	@python3 -c "
import asyncio, httpx, time

WORKERS = [
    ('infinity-ws',   'http://localhost:8004/health'),
    ('infinity-auth', 'http://localhost:8005/health'),
    ('users-svc',     'http://localhost:8006/health'),
    ('monitoring',    'http://localhost:8007/health'),
    ('notifications', 'http://localhost:8008/health'),
    ('infinity-ai',   'http://localhost:8009/health'),
]

async def check():
    async with httpx.AsyncClient(timeout=2.0) as c:
        for name, url in WORKERS:
            try:
                r = await c.get(url)
                status = 'UP  ' if r.status_code == 200 else f'ERR {r.status_code}'
            except Exception as e:
                status = f'DOWN ({type(e).__name__})'
            print(f'  {status}  {name} ({url})')

asyncio.run(check())
"

# ── Legacy setup (kept for compatibility — prefer make setup-dev) ─────────────
setup:
	@$(MAKE) setup-dev

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

## ── Deployment modes ─────────────────────────────────────────────────────────
# dev: local development stack (hot-reload, debug logging, no TLS)
deploy-dev:
	@echo "==> Starting dev stack (docker-compose.yml)..."
	docker compose -f docker-compose.yml up -d --build --remove-orphans
	@echo "==> Verifying P0 services..."
	@python3 scripts/post_deploy_verify.py --tier P0 --base http://localhost --soft || true
	@echo "==> Dev stack ready. API: http://localhost:8000"

# staging: production-like stack on local machine (production compose, no live traffic)
deploy-staging:
	@echo "==> Starting staging stack (docker-compose.production.yml)..."
	docker compose -f docker-compose.production.yml up -d --build --remove-orphans
	@echo "==> Waiting 20s for services to initialise..."
	@sleep 20
	@python3 scripts/post_deploy_verify.py --tier P0 --retries 3
	@echo "==> Staging stack ready."

# prod: full production deploy with pre-deploy gate, deploy, post-deploy verify
deploy-prod:
	@echo "==> [1/4] Pre-deploy quality gate..."
	@python3 scripts/pre_deploy_quality_gate.py || (echo "Quality gate failed — aborting"; exit 1)
	@echo "==> [2/4] Pulling latest images..."
	@docker compose -f docker-compose.production.yml pull --quiet
	@echo "==> [3/4] Starting production stack..."
	@docker compose -f docker-compose.production.yml up -d --remove-orphans
	@echo "==> [4/4] Post-deploy verification..."
	@python3 scripts/post_deploy_verify.py --retries 5 --report logs/deploy_verify.json
	@echo "==> Production deploy complete."

# verify: run post-deploy health check against running stack
# Usage: make deploy-verify [TIER=P0] [BASE=http://localhost]
deploy-verify:
	@python3 scripts/post_deploy_verify.py \
		--tier "$${TIER:-all}" \
		--base "$${BASE:-http://localhost}" \
		--retries "$${RETRIES:-3}" \
		--report logs/deploy_verify.json

# rollback: stop current stack and restore previous git-tagged compose snapshot
# Usage: make deploy-rollback [TAG=v1.2.3]
deploy-rollback:
	@bash scripts/rollback.sh $${TAG:-}

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

# ── DEFSTAN Compliance ────────────────────────────────────────────────────────
compliance-check:
	@echo "Running DEFSTAN compliance check..."
	python -m src.compliance.checker

compliance-report:
	@echo "Generating DEFSTAN compliance report..."
	python -m src.compliance.checker --report

compliance-ci:
	@echo "Running DEFSTAN compliance CI gate (threshold: 70%)..."
	python -m src.compliance.checker --ci

compliance-merged:
	@echo "Running full merged compliance check (DEFSTAN + Magna Carta)..."
	python -m src.compliance.checker --magna-carta compliance/magna-carta/compliance/magna_carta_register.yaml --report

compliance-mc:
	@echo "Running Magna Carta compliance check only..."
	python -c "
from pathlib import Path
from src.compliance.checker import load_and_check_merged, REGISTER_PATH
from src.compliance.report_generator import generate_markdown
mc = Path('compliance/magna-carta/compliance/magna_carta_register.yaml')
report = load_and_check_merged(REGISTER_PATH, mc)
print(generate_markdown(report))
"

gate-check:
	@echo "Running 13-Gate lifecycle compliance check..."
	python -m src.compliance.gate_lifecycle

zero-cost-status:
	python -c "from src.monitoring.zero_cost_tracker import tracker; import json; print(json.dumps(tracker.get_summary(), indent=2))"

# ── Disaster Recovery ─────────────────────────────────────────────────────────
backup-status:
	python scripts/dr_restore.py rpo-status

backup-all:
	python scripts/dr_restore.py list

dr-drill:
	@echo "Running DR drill (verify + dry-run restore all workers)..."
	python scripts/dr_restore.py dr-drill

dr-verify:
	python scripts/dr_restore.py verify

# ── Performance Regression Gate (REQ-QA-007) ──────────────────────────────────
perf-gate:
	python -m src.benchmark.perf_gate

perf-gate-update:
	python -m src.benchmark.perf_gate --update
