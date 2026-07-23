"""
Worker Integration Tests — P2 Workers (the-grid, products-service, orders-service, payments-service, files-service, identity-service)
=======================================================================================================================================
Tests the six P2 workers end-to-end using FastAPI TestClient with temporary SQLite databases.

P2 Workers:
- the-grid (The Digital Grid): Workflow orchestration engine with DAG-based execution
- products-service: Product catalog CRUD API
- orders-service: Order management CRUD API
- payments-service: Payment processing CRUD API
- files-service: File metadata CRUD API
- identity-service: Identity and access CRUD API
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker as _import_worker

# ─── Import helpers for hyphenated package names ────────────────────────────────────────────────────────────────────────────────

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


grid_mod = _import_worker("the_grid_worker", _TRANC3_ROOT / "workers" / "the-grid" / "worker.py")
# worker.py is a thin `from main import app` shim (see its own docstring) and
# does not re-export models.py's Pydantic classes or database.py's GridDatabase
# — import them directly for the model/database-level tests below. No isinstance
# checks exist in database.py's methods (verified: plain attribute/dict access),
# so it's safe that this is a separate import session from grid_mod's above.
grid_models_mod = _import_worker(
    "the_grid_models", _TRANC3_ROOT / "workers" / "the-grid" / "models.py"
)
grid_database_mod = _import_worker(
    "the_grid_database", _TRANC3_ROOT / "workers" / "the-grid" / "database.py"
)
products_mod = _import_worker(
    "products_service_worker", _TRANC3_ROOT / "workers" / "products-service" / "worker.py"
)
orders_mod = _import_worker(
    "orders_service_worker", _TRANC3_ROOT / "workers" / "orders-service" / "worker.py"
)
payments_mod = _import_worker(
    "payments_service_worker", _TRANC3_ROOT / "workers" / "payments-service" / "worker.py"
)
files_mod = _import_worker(
    "files_service_worker", _TRANC3_ROOT / "workers" / "files-service" / "worker.py"
)
identity_mod = _import_worker(
    "identity_service_worker", _TRANC3_ROOT / "workers" / "identity-service" / "worker.py"
)


# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# the-grid (The Digital Grid) — Workflow Orchestration
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


class TestGridModels:
    """Test Pydantic models for the grid service."""

    def test_workflow_step_model(self):
        step = grid_models_mod.WorkflowStep(
            name="Test Step",
            action="http_call",
            config={"url": "https://example.com"},
        )
        assert step.name == "Test Step"
        assert step.action == "http_call"
        assert step.step_id is not None

    def test_workflow_definition_model(self):
        wf = grid_models_mod.WorkflowDefinition(
            name="Test Workflow",
            steps=[
                grid_models_mod.WorkflowStep(name="Step 1", action="delay"),
                grid_models_mod.WorkflowStep(name="Step 2", action="notify"),
            ],
        )
        assert wf.name == "Test Workflow"
        assert len(wf.steps) == 2
        assert wf.workflow_id is not None

    def test_workflow_execution_model(self):
        execn = grid_models_mod.WorkflowExecution(
            workflow_id="wf-123",
            input_data={"key": "value"},
        )
        assert execn.workflow_id == "wf-123"
        assert execn.status == grid_models_mod.WorkflowStatus.pending
        assert execn.execution_id is not None

    def test_workflow_status_enum(self):
        assert grid_models_mod.WorkflowStatus.pending == "pending"
        assert grid_models_mod.WorkflowStatus.running == "running"
        assert grid_models_mod.WorkflowStatus.completed == "completed"
        assert grid_models_mod.WorkflowStatus.failed == "failed"

    def test_step_status_enum(self):
        assert grid_models_mod.StepStatus.pending == "pending"
        assert grid_models_mod.StepStatus.running == "running"
        assert grid_models_mod.StepStatus.completed == "completed"
        assert grid_models_mod.StepStatus.failed == "failed"


class TestGridDatabase:
    """Test the GridDatabase class with temporary database."""

    @pytest.fixture
    def grid_db(self, tmp_path):
        db_path = tmp_path / "test_grid.db"
        db = grid_database_mod.GridDatabase(db_path=db_path)
        yield db

    def test_tables_created(self, grid_db):
        """Verify workflow tables are created."""
        conn = grid_db._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "workflow_definitions" in tables
        assert "workflow_executions" in tables

    def test_save_and_get_definition(self, grid_db):
        """Save a workflow definition and retrieve it."""
        wf = grid_models_mod.WorkflowDefinition(
            name="Test Workflow",
            steps=[grid_models_mod.WorkflowStep(name="Step 1", action="delay")],
        )
        saved = grid_db.save_definition(wf)
        assert saved.workflow_id == wf.workflow_id

        retrieved = grid_db.get_definition(wf.workflow_id)
        assert retrieved is not None
        assert retrieved["name"] == "Test Workflow"

    def test_list_definitions(self, grid_db):
        """List workflow definitions."""
        grid_db.save_definition(grid_models_mod.WorkflowDefinition(name="WF 1", steps=[]))
        grid_db.save_definition(grid_models_mod.WorkflowDefinition(name="WF 2", steps=[]))

        defs = grid_db.list_definitions()
        assert len(defs) >= 2

    def test_save_and_get_execution(self, grid_db):
        """Save a workflow execution and retrieve it."""
        execn = grid_models_mod.WorkflowExecution(
            workflow_id="wf-123",
            status=grid_models_mod.WorkflowStatus.running,
        )
        saved = grid_db.save_execution(execn)
        assert saved.execution_id == execn.execution_id

        retrieved = grid_db.get_execution(execn.execution_id)
        assert retrieved is not None
        assert retrieved["status"] == "running"

    def test_list_executions(self, grid_db):
        """List workflow executions."""
        grid_db.save_execution(grid_models_mod.WorkflowExecution(workflow_id="wf-1"))
        grid_db.save_execution(grid_models_mod.WorkflowExecution(workflow_id="wf-2"))

        execs = grid_db.list_executions()
        assert len(execs) >= 2


class TestGridHTTPEndpoints:
    """Test HTTP endpoints for the grid service."""

    @pytest.fixture
    def grid_client(self):
        """TestClient against grid_mod.app.

        the-grid's GridDatabase/WorkflowEngineRouter are constructed once
        inside main.create_app() at module-import time and captured by the
        router's route-handler closures (see workers/the-grid/main.py) —
        there's no module-level `db`/`engine` attribute on worker.py to
        monkeypatch, so (unlike simpler single-file workers) per-test DB
        isolation isn't available here. Share one grid.db for the session,
        matching the working pattern already used by
        tests/test_workers_p3.py::TestTheGrid.
        """
        secret = os.environ.get("INTERNAL_SECRET", "")
        headers = {"X-Internal-Secret": secret} if secret else {}
        yield TestClient(grid_mod.app, headers=headers)

    def test_health_endpoint(self, grid_client):
        response = grid_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "the-grid-api"
        assert "uptime_seconds" in data

    def test_create_workflow(self, grid_client):
        response = grid_client.post(
            "/workflows",
            json={
                "name": "Test Workflow",
                "description": "A test workflow",
                "steps": [
                    {"name": "Step 1", "action": "delay", "config": {"seconds": 0.1}},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "workflow_id" in data

    def test_list_workflows(self, grid_client):
        grid_client.post("/workflows", json={"name": "WF 1", "steps": []})
        grid_client.post("/workflows", json={"name": "WF 2", "steps": []})

        response = grid_client.get("/workflows")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workflows"]) >= 2

    def test_get_workflow(self, grid_client):
        create = grid_client.post("/workflows", json={"name": "Get Me", "steps": []})
        workflow_id = create.json()["workflow_id"]

        response = grid_client.get(f"/workflows/{workflow_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Me"

    def test_get_nonexistent_workflow(self, grid_client):
        response = grid_client.get("/workflows/nonexistent-id")
        assert response.status_code == 404

    def test_delete_workflow(self, grid_client):
        create = grid_client.post("/workflows", json={"name": "Delete Me", "steps": []})
        workflow_id = create.json()["workflow_id"]

        response = grid_client.delete(f"/workflows/{workflow_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["deleted"] == workflow_id

    def test_execute_workflow(self, grid_client):
        # Create a simple workflow
        create = grid_client.post(
            "/workflows",
            json={
                "name": "Simple Workflow",
                "steps": [
                    {"name": "Delay Step", "action": "delay", "config": {"seconds": 0.1}},
                ],
            },
        )
        workflow_id = create.json()["workflow_id"]

        # Execute it
        response = grid_client.post(f"/workflows/{workflow_id}/execute", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "execution_id" in data
        assert data["status"] in ["pending", "running", "completed"]

    def test_execute_nonexistent_workflow(self, grid_client):
        response = grid_client.post("/workflows/nonexistent/execute", json={})
        assert response.status_code == 404

    def test_list_executions(self, grid_client):
        # Create and execute a workflow
        create = grid_client.post(
            "/workflows",
            json={
                "name": "Exec Test",
                "steps": [{"name": "Step 1", "action": "delay", "config": {"seconds": 0.05}}],
            },
        )
        workflow_id = create.json()["workflow_id"]
        grid_client.post(f"/workflows/{workflow_id}/execute", json={})

        response = grid_client.get("/executions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) >= 1

    def test_get_execution(self, grid_client):
        # Create and execute a workflow
        create = grid_client.post(
            "/workflows",
            json={
                "name": "Get Exec",
                "steps": [{"name": "Step 1", "action": "delay", "config": {"seconds": 0.05}}],
            },
        )
        workflow_id = create.json()["workflow_id"]
        exec_resp = grid_client.post(f"/workflows/{workflow_id}/execute", json={})
        execution_id = exec_resp.json()["execution_id"]

        response = grid_client.get(f"/executions/{execution_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == execution_id

    def test_list_executions_with_filters(self, grid_client):
        # Create workflow and execute it
        create = grid_client.post(
            "/workflows",
            json={
                "name": "Filter Test",
                "steps": [{"name": "Step 1", "action": "delay", "config": {"seconds": 0.05}}],
            },
        )
        workflow_id = create.json()["workflow_id"]
        grid_client.post(f"/workflows/{workflow_id}/execute", json={})

        # Filter by workflow_id
        response = grid_client.get(f"/executions?workflow_id={workflow_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) >= 1


# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# Generic CRUD Workers (products-service, orders-service, payments-service, files-service, identity-service)
# ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────


class TestGenericCRUDWorker:
    """Base test class for generic CRUD workers."""

    @pytest.fixture
    def products_client(self, tmp_path):
        db_path = tmp_path / "test_products.db"
        test_db = products_mod.ProductsDatabase(db_path=db_path)
        with patch.object(products_mod, "db", test_db):
            secret = getattr(products_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(products_mod.app, headers=headers)
            yield client

    @pytest.fixture
    def orders_client(self, tmp_path):
        # orders-service (Arcadian Exchange) is a single-file worker with a
        # module-level DB_PATH global read fresh by _get_conn() on every call
        # (no OrdersDatabase class exists) — patch that global directly and
        # (re)initialize the schema against it, rather than a nonexistent class.
        db_path = tmp_path / "test_orders.db"
        with patch.object(orders_mod, "DB_PATH", db_path):
            orders_mod.init_db()
            secret = getattr(orders_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(orders_mod.app, headers=headers)
            yield client

    @pytest.fixture
    def payments_client(self, tmp_path):
        # payments-service (Royal Bank of Arcadia) is likewise a single-file
        # worker with a module-level DB_PATH global, not a PaymentsDatabase class.
        db_path = tmp_path / "test_payments.db"
        with patch.object(payments_mod, "DB_PATH", db_path):
            payments_mod.init_db()
            secret = getattr(payments_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(payments_mod.app, headers=headers)
            yield client

    @pytest.fixture
    def files_client(self, tmp_path):
        db_path = tmp_path / "test_files.db"
        test_db = files_mod.FilesDatabase(db_path=db_path)
        with patch.object(files_mod, "db", test_db):
            secret = getattr(files_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(files_mod.app, headers=headers)
            yield client

    @pytest.fixture
    def identity_client(self, tmp_path):
        db_path = tmp_path / "test_identity.db"
        test_db = identity_mod.IdentitiesDatabase(db_path=db_path)
        with patch.object(identity_mod, "db", test_db):
            secret = getattr(identity_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(identity_mod.app, headers=headers)
            yield client

    # Products Service Tests

    def test_products_health(self, products_client):
        response = products_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "products-service"

    def test_products_create(self, products_client):
        response = products_client.post(
            "/",
            json={
                "name": "Test Product",
                "description": "A test product",
                "price": 99.99,
                "category": "electronics",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "product_id" in data

    def test_products_list(self, products_client):
        products_client.post("/", json={"name": "Product 1", "price": 10.0})
        products_client.post("/", json={"name": "Product 2", "price": 20.0})

        response = products_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2

    def test_products_get(self, products_client):
        create = products_client.post("/", json={"name": "Get Me", "price": 15.0})
        product_id = create.json()["product_id"]

        response = products_client.get(f"/{product_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Me"

    def test_products_update(self, products_client):
        create = products_client.post("/", json={"name": "Update Me", "price": 10.0})
        product_id = create.json()["product_id"]

        response = products_client.patch(f"/{product_id}", json={"price": 19.99})
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_products_delete(self, products_client):
        create = products_client.post("/", json={"name": "Delete Me", "price": 5.0})
        product_id = create.json()["product_id"]

        response = products_client.delete(f"/{product_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    # Orders Service Tests (Arcadian Exchange — resource marketplace, not
    # generic CRUD: listings/purchases, no PATCH/DELETE routes exist)

    def test_orders_health(self, orders_client):
        response = orders_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "arcadian-exchange"

    def test_orders_create(self, orders_client):
        response = orders_client.post(
            "/listings",
            json={
                "seller_id": "seller-123",
                "resource_type": "compute_time",
                "quantity": 10,
                "price_per_unit": 2.5,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert "id" in data

    def test_orders_list(self, orders_client):
        orders_client.post(
            "/listings",
            json={
                "seller_id": "s1",
                "resource_type": "storage_gb",
                "quantity": 5,
                "price_per_unit": 1.0,
            },
        )
        orders_client.post(
            "/listings",
            json={
                "seller_id": "s2",
                "resource_type": "storage_gb",
                "quantity": 5,
                "price_per_unit": 1.0,
            },
        )

        response = orders_client.get("/listings")
        assert response.status_code == 200
        data = response.json()
        assert len(data["listings"]) >= 2

    def test_orders_get(self, orders_client):
        """Purchase from a listing, then verify it shows in the buyer's order history."""
        create = orders_client.post(
            "/listings",
            json={
                "seller_id": "seller-1",
                "resource_type": "api_credits",
                "quantity": 100,
                "price_per_unit": 0.5,
            },
        )
        listing_id = create.json()["id"]

        purchase = orders_client.post(
            "/orders", json={"buyer_id": "buyer-1", "listing_id": listing_id, "quantity": 10}
        )
        assert purchase.status_code == 201
        assert purchase.json()["buyer_id"] == "buyer-1"

        response = orders_client.get("/orders/buyer-1")
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    def test_orders_update(self, orders_client):
        """No PATCH route exists — a partial purchase is the exchange's only way a listing mutates."""
        create = orders_client.post(
            "/listings",
            json={
                "seller_id": "seller-2",
                "resource_type": "bandwidth_gb",
                "quantity": 20,
                "price_per_unit": 1.0,
            },
        )
        listing_id = create.json()["id"]

        orders_client.post(
            "/orders", json={"buyer_id": "buyer-2", "listing_id": listing_id, "quantity": 5}
        )

        response = orders_client.get("/listings", params={"resource_type": "bandwidth_gb"})
        listing = next(entry for entry in response.json()["listings"] if entry["id"] == listing_id)
        assert listing["quantity"] == 15
        assert listing["status"] == "active"

    def test_orders_delete(self, orders_client):
        """No DELETE route exists — fully purchasing a listing marks it sold and drops it from browsing."""
        create = orders_client.post(
            "/listings",
            json={
                "seller_id": "seller-3",
                "resource_type": "training_tokens",
                "quantity": 5,
                "price_per_unit": 1.0,
            },
        )
        listing_id = create.json()["id"]

        orders_client.post(
            "/orders", json={"buyer_id": "buyer-3", "listing_id": listing_id, "quantity": 5}
        )

        response = orders_client.get("/listings", params={"resource_type": "training_tokens"})
        assert all(entry["id"] != listing_id for entry in response.json()["listings"])

    # Payments Service Tests (Royal Bank of Arcadia — accounts ledger, not
    # generic CRUD: accounts/transfers/deposits, no PATCH/DELETE routes exist)

    def test_payments_health(self, payments_client):
        response = payments_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "royal-bank-of-arcadia"

    def test_payments_create(self, payments_client):
        response = payments_client.post(
            "/accounts", json={"user_id": "user-123", "initial_balance": 99.99}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert "id" in data

    def test_payments_list(self, payments_client):
        payments_client.post("/accounts", json={"user_id": "user-1", "initial_balance": 10.0})
        payments_client.post("/accounts", json={"user_id": "user-1", "initial_balance": 20.0})

        response = payments_client.get("/accounts/user-1")
        assert response.status_code == 200
        assert len(response.json()["accounts"]) >= 2

    def test_payments_get(self, payments_client):
        create = payments_client.post(
            "/accounts", json={"user_id": "user-123", "initial_balance": 50.0}
        )
        account_id = create.json()["id"]

        response = payments_client.get(f"/transactions/{account_id}")
        assert response.status_code == 200
        assert response.json()["account_id"] == account_id

    def test_payments_update(self, payments_client):
        """No PATCH route exists — a deposit is the ledger's way of changing an account's balance."""
        create = payments_client.post(
            "/accounts", json={"user_id": "user-123", "initial_balance": 10.0}
        )
        account_id = create.json()["id"]

        response = payments_client.post(
            "/transactions/deposit", json={"account_id": account_id, "amount": 25.0}
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["balance_after"] == 35.0

    def test_payments_delete(self, payments_client):
        """No account-deletion route exists — transferring the full balance out is the closest removal."""
        from_acct = payments_client.post(
            "/accounts", json={"user_id": "user-a", "initial_balance": 5.0}
        ).json()
        to_acct = payments_client.post(
            "/accounts", json={"user_id": "user-b", "initial_balance": 0.0}
        ).json()

        response = payments_client.post(
            "/transactions/transfer",
            json={
                "from_account_id": from_acct["id"],
                "to_account_id": to_acct["id"],
                "amount": 5.0,
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["from_balance_after"] == 0.0

    # Files Service Tests

    def test_files_health(self, files_client):
        response = files_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "files-service"

    def test_files_create(self, files_client):
        """DocUtari's real API is upload-specific (multipart), not a generic POST /."""
        response = files_client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.pdf"
        assert "id" in data

    def test_files_list(self, files_client):
        files_client.post(
            "/api/documents/upload", files={"file": ("file1.txt", b"hello", "text/plain")}
        )
        files_client.post(
            "/api/documents/upload", files={"file": ("file2.txt", b"world", "text/plain")}
        )

        response = files_client.get("/api/documents")
        assert response.status_code == 200
        assert len(response.json()) >= 2

    def test_files_get(self, files_client):
        create = files_client.post(
            "/api/documents/upload", files={"file": ("getme.pdf", b"content", "application/pdf")}
        )
        doc_id = create.json()["id"]

        response = files_client.get(f"/api/documents/{doc_id}")
        assert response.status_code == 200
        assert response.json()["filename"] == "getme.pdf"

    def test_files_update(self, files_client):
        """size_bytes isn't in update_document's allowed-fields set — title is."""
        create = files_client.post(
            "/api/documents/upload", files={"file": ("update.pdf", b"content", "application/pdf")}
        )
        doc_id = create.json()["id"]

        response = files_client.patch(f"/api/documents/{doc_id}", json={"title": "Updated Title"})
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_files_delete(self, files_client):
        create = files_client.post(
            "/api/documents/upload", files={"file": ("delete.pdf", b"content", "application/pdf")}
        )
        doc_id = create.json()["id"]

        response = files_client.delete(f"/api/documents/{doc_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    # Identity Service Tests

    def test_identity_health(self, identity_client):
        response = identity_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "identity-service"

    def test_identity_create(self, identity_client):
        response = identity_client.post(
            "/",
            json={
                "user_id": "user-123",
                "provider": "local",
                "provider_id": "local-123",
                "email": "test@example.com",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "identity_id" in data

    def test_identity_list(self, identity_client):
        identity_client.post(
            "/", json={"user_id": "user-1", "provider": "local", "provider_id": "local-1"}
        )
        identity_client.post(
            "/", json={"user_id": "user-2", "provider": "local", "provider_id": "local-2"}
        )

        response = identity_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2

    def test_identity_get(self, identity_client):
        create = identity_client.post(
            "/", json={"user_id": "user-123", "provider": "local", "provider_id": "local-123"}
        )
        identity_id = create.json()["identity_id"]

        response = identity_client.get(f"/{identity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"

    def test_identity_update(self, identity_client):
        create = identity_client.post(
            "/",
            json={
                "user_id": "user-123",
                "provider": "local",
                "provider_id": "local-123",
                "email": "old@example.com",
            },
        )
        identity_id = create.json()["identity_id"]

        response = identity_client.patch(f"/{identity_id}", json={"email": "new@example.com"})
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_identity_delete(self, identity_client):
        create = identity_client.post(
            "/", json={"user_id": "user-123", "provider": "local", "provider_id": "local-123"}
        )
        identity_id = create.json()["identity_id"]

        response = identity_client.delete(f"/{identity_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True
