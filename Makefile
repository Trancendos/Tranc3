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
        submodules check-env

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
	@python3 scripts/monitor_p0_workers.py

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
	cd web && npm ci && npm run build
	@echo "✓ Frontend built → web/dist/ ($(shell du -sh web/dist 2>/dev/null | cut -f1) on disk)"

frontend-check:
	cd web && npm ci && npx tsc --noEmit

frontend-docker:
	docker build -t tranc3-web -f docker/Dockerfile.web .
	@echo "✓ tranc3-web Docker image built"

frontend-ci: frontend-check frontend
	@test -f web/dist/index.html || (echo "✗ web/dist/index.html missing — build failed" && exit 1)
	@echo "✓ Frontend CI passed"

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

deploy-live:
	@bash scripts/deploy_live.sh

generate-prod-env:
	@bash scripts/generate_production_env.sh

wait-healthy:
	@python3 scripts/wait_for_healthy.py

citadel-preflight:
	@python3 scripts/citadel_compose_validate.py
	@python3 scripts/citadel_preflight.py

citadel-compose-validate:
	@python3 scripts/citadel_compose_validate.py

branch-audit:
	@python3 scripts/branch_benefit_audit.py

stale-branch-cleanup:
	@python3 scripts/stale_branch_cleanup.py

stale-branch-cleanup-apply:
	@python3 scripts/stale_branch_cleanup.py --apply

integration-plan:
	@python3 scripts/integration_scope_plan.py --branch cursor/production-integration-8d67

fork-audit:
	@python3 scripts/fork_audit.py

pr-audit:
	@python3 scripts/pr_readiness_audit.py --state open --limit 100 --fail-on-unstable

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

pre-deploy-gate:
	@python3 scripts/pre_deploy_quality_gate.py

citadel-deploy-all:
	@python3 scripts/citadel_deploy_all.py

citadel-deploy-all-gate:
	@python3 scripts/citadel_deploy_all.py --gate-only

deploy-cloud:
	@python3 scripts/deploy_cloud.py

deploy-cloud-gate:
	@python3 scripts/deploy_cloud.py --gate-only

pre-deploy-fix:
	@python3 -m ruff check src/ api.py workers/infinity-auth workers/infinity-ws workers/api-gateway workers/tranc3-ai workers/infinity-void workers/users-service workers/products-service workers/orders-service workers/payments-service workers/notifications workers/infinity-ai workers/monitoring --fix || true

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
