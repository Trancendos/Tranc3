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

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests._worker_import_utils import import_worker as _import_worker

# ─── Import helpers for hyphenated package names ────────────────────────────────────────────────────────────────────────────────

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


grid_mod = _import_worker("the_grid_worker", _TRANC3_ROOT / "workers" / "the-grid" / "worker.py")
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
        step = grid_mod.WorkflowStep(
            name="Test Step",
            action="http_call",
            config={"url": "https://example.com"},
        )
        assert step.name == "Test Step"
        assert step.action == "http_call"
        assert step.step_id is not None

    def test_workflow_definition_model(self):
        wf = grid_mod.WorkflowDefinition(
            name="Test Workflow",
            steps=[
                grid_mod.WorkflowStep(name="Step 1", action="delay"),
                grid_mod.WorkflowStep(name="Step 2", action="notify"),
            ],
        )
        assert wf.name == "Test Workflow"
        assert len(wf.steps) == 2
        assert wf.workflow_id is not None

    def test_workflow_execution_model(self):
        execn = grid_mod.WorkflowExecution(
            workflow_id="wf-123",
            input_data={"key": "value"},
        )
        assert execn.workflow_id == "wf-123"
        assert execn.status == grid_mod.WorkflowStatus.pending
        assert execn.execution_id is not None

    def test_workflow_status_enum(self):
        assert grid_mod.WorkflowStatus.pending == "pending"
        assert grid_mod.WorkflowStatus.running == "running"
        assert grid_mod.WorkflowStatus.completed == "completed"
        assert grid_mod.WorkflowStatus.failed == "failed"

    def test_step_status_enum(self):
        assert grid_mod.StepStatus.pending == "pending"
        assert grid_mod.StepStatus.running == "running"
        assert grid_mod.StepStatus.completed == "completed"
        assert grid_mod.StepStatus.failed == "failed"


class TestGridDatabase:
    """Test the GridDatabase class with temporary database."""

    @pytest.fixture
    def grid_db(self, tmp_path):
        db_path = tmp_path / "test_grid.db"
        db = grid_mod.GridDatabase(db_path=db_path)
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
        wf = grid_mod.WorkflowDefinition(
            name="Test Workflow",
            steps=[grid_mod.WorkflowStep(name="Step 1", action="delay")],
        )
        saved = grid_db.save_definition(wf)
        assert saved.workflow_id == wf.workflow_id

        retrieved = grid_db.get_definition(wf.workflow_id)
        assert retrieved is not None
        assert retrieved["name"] == "Test Workflow"

    def test_list_definitions(self, grid_db):
        """List workflow definitions."""
        grid_db.save_definition(grid_mod.WorkflowDefinition(name="WF 1", steps=[]))
        grid_db.save_definition(grid_mod.WorkflowDefinition(name="WF 2", steps=[]))

        defs = grid_db.list_definitions()
        assert len(defs) >= 2

    def test_save_and_get_execution(self, grid_db):
        """Save a workflow execution and retrieve it."""
        execn = grid_mod.WorkflowExecution(
            workflow_id="wf-123",
            status=grid_mod.WorkflowStatus.running,
        )
        saved = grid_db.save_execution(execn)
        assert saved.execution_id == execn.execution_id

        retrieved = grid_db.get_execution(execn.execution_id)
        assert retrieved is not None
        assert retrieved["status"] == "running"

    def test_list_executions(self, grid_db):
        """List workflow executions."""
        grid_db.save_execution(grid_mod.WorkflowExecution(workflow_id="wf-1"))
        grid_db.save_execution(grid_mod.WorkflowExecution(workflow_id="wf-2"))

        execs = grid_db.list_executions()
        assert len(execs) >= 2


class TestGridHTTPEndpoints:
    """Test HTTP endpoints for the grid service."""

    @pytest.fixture
    def grid_client(self, tmp_path):
        """Create a TestClient with a temporary database."""
        db_path = tmp_path / "test_grid.db"
        test_db = grid_mod.GridDatabase(db_path=db_path)
        test_engine = grid_mod.WorkflowEngine(test_db)

        with patch.object(grid_mod, "db", test_db), patch.object(grid_mod, "engine", test_engine):
            secret = getattr(grid_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(grid_mod.app, headers=headers)
            yield client

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
        db_path = tmp_path / "test_orders.db"
        test_db = orders_mod.OrdersDatabase(db_path=db_path)
        with patch.object(orders_mod, "db", test_db):
            secret = getattr(orders_mod, "_INTERNAL_SECRET", "")
            headers = {"X-Internal-Secret": secret} if secret else {}
            client = TestClient(orders_mod.app, headers=headers)
            yield client

    @pytest.fixture
    def payments_client(self, tmp_path):
        db_path = tmp_path / "test_payments.db"
        test_db = payments_mod.PaymentsDatabase(db_path=db_path)
        with patch.object(payments_mod, "db", test_db):
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

    # Orders Service Tests

    def test_orders_health(self, orders_client):
        response = orders_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "orders-service"

    def test_orders_create(self, orders_client):
        response = orders_client.post(
            "/",
            json={
                "user_id": "user-123",
                "items": json.dumps([{"product_id": "p1", "quantity": 2}]),
                "total": 199.98,
                "status": "pending",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "order_id" in data

    def test_orders_list(self, orders_client):
        orders_client.post("/", json={"user_id": "user-1", "total": 10.0})
        orders_client.post("/", json={"user_id": "user-2", "total": 20.0})

        response = orders_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2

    def test_orders_get(self, orders_client):
        create = orders_client.post("/", json={"user_id": "user-123", "total": 50.0})
        order_id = create.json()["order_id"]

        response = orders_client.get(f"/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"

    def test_orders_update(self, orders_client):
        create = orders_client.post(
            "/", json={"user_id": "user-123", "total": 10.0, "status": "pending"}
        )
        order_id = create.json()["order_id"]

        response = orders_client.patch(f"/{order_id}", json={"status": "shipped"})
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_orders_delete(self, orders_client):
        create = orders_client.post("/", json={"user_id": "user-123", "total": 5.0})
        order_id = create.json()["order_id"]

        response = orders_client.delete(f"/{order_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    # Payments Service Tests

    def test_payments_health(self, payments_client):
        response = payments_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "payments-service"

    def test_payments_create(self, payments_client):
        response = payments_client.post(
            "/",
            json={
                "order_id": "order-123",
                "user_id": "user-123",
                "amount": 99.99,
                "currency": "USD",
                "status": "pending",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "payment_id" in data

    def test_payments_list(self, payments_client):
        payments_client.post("/", json={"order_id": "order-1", "user_id": "user-1", "amount": 10.0})
        payments_client.post("/", json={"order_id": "order-2", "user_id": "user-2", "amount": 20.0})

        response = payments_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2

    def test_payments_get(self, payments_client):
        create = payments_client.post(
            "/", json={"order_id": "order-123", "user_id": "user-123", "amount": 50.0}
        )
        payment_id = create.json()["payment_id"]

        response = payments_client.get(f"/{payment_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "order-123"

    def test_payments_update(self, payments_client):
        create = payments_client.post(
            "/",
            json={
                "order_id": "order-123",
                "user_id": "user-123",
                "amount": 10.0,
                "status": "pending",
            },
        )
        payment_id = create.json()["payment_id"]

        response = payments_client.patch(f"/{payment_id}", json={"status": "completed"})
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_payments_delete(self, payments_client):
        create = payments_client.post(
            "/", json={"order_id": "order-123", "user_id": "user-123", "amount": 5.0}
        )
        payment_id = create.json()["payment_id"]

        response = payments_client.delete(f"/{payment_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    # Files Service Tests

    def test_files_health(self, files_client):
        response = files_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "files-service"

    def test_files_create(self, files_client):
        response = files_client.post(
            "/",
            json={
                "filename": "test.pdf",
                "size_bytes": 1024,
                "content_type": "application/pdf",
                "path": "/files/test.pdf",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "file_id" in data

    def test_files_list(self, files_client):
        files_client.post(
            "/", json={"filename": "file1.txt", "size_bytes": 100, "path": "/files/file1.txt"}
        )
        files_client.post(
            "/", json={"filename": "file2.txt", "size_bytes": 200, "path": "/files/file2.txt"}
        )

        response = files_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2

    def test_files_get(self, files_client):
        create = files_client.post(
            "/", json={"filename": "getme.pdf", "size_bytes": 512, "path": "/files/getme.pdf"}
        )
        file_id = create.json()["file_id"]

        response = files_client.get(f"/{file_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "getme.pdf"

    def test_files_update(self, files_client):
        create = files_client.post(
            "/", json={"filename": "update.pdf", "size_bytes": 100, "path": "/files/update.pdf"}
        )
        file_id = create.json()["file_id"]

        response = files_client.patch(f"/{file_id}", json={"size_bytes": 2048})
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_files_delete(self, files_client):
        create = files_client.post(
            "/", json={"filename": "delete.pdf", "size_bytes": 50, "path": "/files/delete.pdf"}
        )
        file_id = create.json()["file_id"]

        response = files_client.delete(f"/{file_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True

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
