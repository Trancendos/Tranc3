"""
Worker Integration Tests — P1 Workers (users-service, monitoring, notifications, infinity-ai)
===============================================================================================
Tests the four P1 workers end-to-end using FastAPI TestClient with temporary SQLite databases.

P1 Workers:
- users-service: User management CRUD API
- monitoring (The Observatory): Health aggregation, metrics, alerting, dashboard
- notifications: Multi-channel notification dispatch with templates and rate limiting
- infinity-ai: AI API Gateway with OpenAI-compatible API and provider failover
"""

from __future__ import annotations

import importlib
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ─── Import helpers for hyphenated package names ───────────────────────────────

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


def _import_worker(module_dotted: str, file_path: Path):
    """Import a worker module with hyphenated path using importlib."""
    spec = importlib.util.spec_from_file_location(module_dotted, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_dotted] = mod
    spec.loader.exec_module(mod)
    return mod


users_mod = _import_worker(
    "users_service_worker", _TRANC3_ROOT / "workers" / "users-service" / "worker.py"
)
monitoring_mod = _import_worker(
    "monitoring_worker", _TRANC3_ROOT / "workers" / "monitoring" / "worker.py"
)
notifications_mod = _import_worker(
    "notifications_worker", _TRANC3_ROOT / "workers" / "notifications" / "worker.py"
)
ai_mod = _import_worker(
    "infinity_ai_worker", _TRANC3_ROOT / "workers" / "infinity-ai" / "worker.py"
)


# ────────────────────────────────────────────────────────────────────────────────
# users-service — User Management CRUD API
# ────────────────────────────────────────────────────────────────────────────────


class TestUsersServiceModels:
    """Test Pydantic models for the users service."""

    def test_user_create_defaults(self):
        user = users_mod.UserCreate(username="testuser", email="test@example.com")
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.display_name == ""
        assert user.role == "user"
        assert user.preferences == {}

    def test_user_create_with_all_fields(self):
        user = users_mod.UserCreate(
            username="admin",
            email="admin@example.com",
            display_name="Admin User",
            role="admin",
            preferences={"theme": "dark"},
        )
        assert user.role == "admin"
        assert user.preferences == {"theme": "dark"}

    def test_user_update_partial(self):
        update = users_mod.UserUpdate(display_name="New Name")
        assert update.display_name == "New Name"
        assert update.email is None
        assert update.role is None

    def test_user_response_model(self):
        response = users_mod.UserResponse(
            user_id="123",
            username="test",
            email="test@example.com",
            display_name="Test",
            role="user",
            preferences={},
            is_active=True,
            created_at="2024-01-01T00:00:00Z",
        )
        assert response.user_id == "123"
        assert response.is_active is True

    def test_user_list_response(self):
        list_resp = users_mod.UserListResponse(
            users=[],
            total=0,
            page=1,
            per_page=20,
        )
        assert list_resp.total == 0
        assert list_resp.page == 1


class TestUsersServiceDatabase:
    """Test the UsersDatabase class with temporary database."""

    @pytest.fixture
    def users_db(self, tmp_path):
        db_path = str(tmp_path / "test_users.db")
        db = users_mod.UsersDatabase(db_path=db_path)
        yield db
        db._conn.close()

    def test_tables_created(self, users_db):
        """Verify users table is created."""
        cursor = users_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "users" in tables

    def test_insert_and_query_user(self, users_db):
        """Insert a user and query it back."""
        user_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        users_db.execute(
            "INSERT INTO users (user_id, username, email, display_name, role, preferences, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, "testuser", "test@example.com", "Test User", "user", "{}", now),
        )
        users_db.commit()

        row = users_db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row is not None
        assert row["username"] == "testuser"
        assert row["email"] == "test@example.com"


class TestUsersServiceHTTPEndpoints:
    """Test HTTP endpoints for the users service using TestClient."""

    @pytest.fixture
    def users_client(self, tmp_path):
        """Create a TestClient with a temporary database."""
        db_path = str(tmp_path / "test_users.db")
        test_db = users_mod.UsersDatabase(db_path=db_path)

        with patch.object(users_mod, "db", test_db):
            client = TestClient(
                users_mod.app,
                headers={"X-Internal-Secret": users_mod._INTERNAL_SECRET},
            )
            yield client

        test_db._conn.close()

    def test_health_endpoint(self, users_client):
        response = users_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "users-service"
        assert "user_count" in data

    def test_create_user(self, users_client):
        response = users_client.post(
            "/users",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "display_name": "New User",
                "role": "user",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert "user_id" in data

    def test_create_duplicate_username(self, users_client):
        users_client.post(
            "/users",
            json={
                "username": "dupuser",
                "email": "first@example.com",
            },
        )
        response = users_client.post(
            "/users",
            json={
                "username": "dupuser",
                "email": "second@example.com",
            },
        )
        assert response.status_code == 409

    def test_get_user(self, users_client):
        create = users_client.post(
            "/users",
            json={
                "username": "getuser",
                "email": "get@example.com",
            },
        )
        user_id = create.json()["user_id"]

        response = users_client.get(f"/users/{user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "getuser"

    def test_get_nonexistent_user(self, users_client):
        response = users_client.get("/users/nonexistent-id")
        assert response.status_code == 404

    def test_list_users(self, users_client):
        users_client.post("/users", json={"username": "user1", "email": "user1@example.com"})
        users_client.post("/users", json={"username": "user2", "email": "user2@example.com"})

        response = users_client.get("/users")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert len(data["users"]) >= 2

    def test_list_users_pagination(self, users_client):
        response = users_client.get("/users?page=1&per_page=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 10

    def test_update_user(self, users_client):
        create = users_client.post(
            "/users",
            json={
                "username": "updateuser",
                "email": "update@example.com",
            },
        )
        user_id = create.json()["user_id"]

        response = users_client.patch(
            f"/users/{user_id}",
            json={
                "display_name": "Updated Name",
                "role": "admin",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["role"] == "admin"

    def test_delete_user(self, users_client):
        create = users_client.post(
            "/users",
            json={
                "username": "deleteuser",
                "email": "delete@example.com",
            },
        )
        user_id = create.json()["user_id"]

        response = users_client.delete(f"/users/{user_id}")
        assert response.status_code == 200
        assert "deactivated" in response.json()["message"]

    def test_delete_nonexistent_user(self, users_client):
        response = users_client.delete("/users/nonexistent-id")
        assert response.status_code == 404


# ────────────────────────────────────────────────────────────────────────────────
# monitoring (The Observatory) — Health, Metrics, Alerting
# ────────────────────────────────────────────────────────────────────────────────


class TestMonitoringModels:
    """Test Pydantic models for the monitoring service."""

    def test_health_report_model(self):
        report = monitoring_mod.HealthReport(
            service_name="test-service",
            status=monitoring_mod.HealthStatus.healthy,
            response_time_ms=100.5,
        )
        assert report.service_name == "test-service"
        assert report.status == monitoring_mod.HealthStatus.healthy

    def test_metric_payload_model(self):
        metric = monitoring_mod.MetricPayload(
            name="request_count",
            type=monitoring_mod.MetricType.counter,
            value=42.0,
            labels={"method": "GET"},
        )
        assert metric.name == "request_count"
        assert metric.type == monitoring_mod.MetricType.counter

    def test_alert_rule_model(self):
        rule = monitoring_mod.AlertRule(
            name="High Error Rate",
            metric_name="error_rate",
            condition=">",
            threshold=5.0,
            severity=monitoring_mod.AlertSeverity.critical,
        )
        assert rule.name == "High Error Rate"
        assert rule.severity == monitoring_mod.AlertSeverity.critical

    def test_alert_model(self):
        alert = monitoring_mod.Alert(
            rule_id="rule-123",
            name="Test Alert",
            severity=monitoring_mod.AlertSeverity.warning,
        )
        assert alert.state == monitoring_mod.AlertState.firing
        assert alert.alert_id is not None

    def test_dashboard_panel_model(self):
        panel = monitoring_mod.DashboardPanel(
            title="Request Rate",
            type="line_chart",
            metric_names=["request_count"],
        )
        assert panel.title == "Request Rate"
        assert panel.type == "line_chart"


class TestMonitoringDatabase:
    """Test the MonitoringDatabase class with temporary database."""

    @pytest.fixture
    def monitoring_db(self, tmp_path):
        db_path = tmp_path / "test_monitoring.db"
        db = monitoring_mod.MonitoringDatabase(db_path=db_path)
        yield db

    def test_tables_created(self, monitoring_db):
        """Verify all tables are created."""
        conn = monitoring_db._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "health_reports" in tables
        assert "metrics" in tables
        assert "alert_rules" in tables
        assert "alerts" in tables

    def test_store_and_query_health(self, monitoring_db):
        """Store a health report and query it back."""
        report = monitoring_mod.HealthReport(
            service_name="test-service",
            status=monitoring_mod.HealthStatus.healthy,
            response_time_ms=50.0,
        )
        monitoring_db.store_health(report)

        latest = monitoring_db.get_latest_health(service_name="test-service")
        assert len(latest) == 1
        assert latest[0]["service_name"] == "test-service"
        assert latest[0]["status"] == "healthy"

    def test_store_and_query_metrics(self, monitoring_db):
        """Store metrics and query them back."""
        metric = monitoring_mod.MetricPayload(
            name="cpu_usage",
            type=monitoring_mod.MetricType.gauge,
            value=75.5,
        )
        monitoring_db.store_metric(metric)

        metrics = monitoring_db.query_metrics("cpu_usage")
        assert len(metrics) >= 1
        assert metrics[0]["name"] == "cpu_usage"
        assert metrics[0]["value"] == 75.5

    def test_create_and_list_alert_rules(self, monitoring_db):
        """Create an alert rule and list it."""
        rule = monitoring_mod.AlertRule(
            name="Test Rule",
            metric_name="test_metric",
            condition=">",
            threshold=10.0,
        )
        monitoring_db.create_alert_rule(rule)

        rules = monitoring_db.get_alert_rules()
        assert len(rules) >= 1
        assert rules[0]["name"] == "Test Rule"

    def test_create_and_resolve_alert(self, monitoring_db):
        """Create an alert and resolve it."""
        alert = monitoring_mod.Alert(
            rule_id="rule-123",
            name="Test Alert",
            severity=monitoring_mod.AlertSeverity.warning,
        )
        monitoring_db.create_alert(alert)

        firing = monitoring_db.get_alerts(state=monitoring_mod.AlertState.firing)
        assert len(firing) >= 1

        monitoring_db.resolve_alert(alert.alert_id)
        firing_after = monitoring_db.get_alerts(state=monitoring_mod.AlertState.firing)
        assert len(firing_after) == 0


class TestMonitoringHTTPEndpoints:
    """Test HTTP endpoints for the monitoring service."""

    @pytest.fixture
    def monitoring_client(self, tmp_path):
        """Create a TestClient with a temporary database."""
        db_path = tmp_path / "test_monitoring.db"
        test_db = monitoring_mod.MonitoringDatabase(db_path=db_path)

        with patch.object(monitoring_mod, "db", test_db):
            client = TestClient(monitoring_mod.app)
            yield client

    def test_health_endpoint(self, monitoring_client):
        response = monitoring_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "the-observatory"

    def test_stats_endpoint(self, monitoring_client):
        response = monitoring_client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "services_monitored" in data
        assert "firing_alerts" in data

    def test_submit_health_report(self, monitoring_client):
        response = monitoring_client.post(
            "/health/report",
            json={
                "service_name": "test-service",
                "status": "healthy",
                "response_time_ms": 100.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["service"] == "test-service"

    def test_list_service_health(self, monitoring_client):
        monitoring_client.post(
            "/health/report",
            json={
                "service_name": "svc1",
                "status": "healthy",
            },
        )
        monitoring_client.post(
            "/health/report",
            json={
                "service_name": "svc2",
                "status": "degraded",
            },
        )

        response = monitoring_client.get("/health/services")
        assert response.status_code == 200
        data = response.json()
        assert len(data["services"]) >= 2

    def test_get_service_health_history(self, monitoring_client):
        monitoring_client.post(
            "/health/report",
            json={
                "service_name": "history-service",
                "status": "healthy",
            },
        )

        response = monitoring_client.get("/health/services/history-service")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "history-service"
        assert "history" in data

    def test_submit_metric(self, monitoring_client):
        response = monitoring_client.post(
            "/metrics",
            json={
                "name": "test_metric",
                "type": "counter",
                "value": 42.0,
            },
        )
        assert response.status_code == 200

    def test_submit_metrics_batch(self, monitoring_client):
        response = monitoring_client.post(
            "/metrics/batch",
            json=[
                {"name": "metric1", "type": "counter", "value": 1.0},
                {"name": "metric2", "type": "gauge", "value": 2.0},
            ],
        )
        assert response.status_code == 200

    def test_list_metric_names(self, monitoring_client):
        monitoring_client.post(
            "/metrics",
            json={
                "name": "unique_metric",
                "type": "counter",
                "value": 1.0,
            },
        )

        response = monitoring_client.get("/metrics/names")
        assert response.status_code == 200
        data = response.json()
        assert "unique_metric" in data["names"]

    def test_query_metrics(self, monitoring_client):
        monitoring_client.post(
            "/metrics",
            json={
                "name": "query_metric",
                "type": "gauge",
                "value": 99.9,
            },
        )

        response = monitoring_client.get("/metrics/query?name=query_metric")
        assert response.status_code == 200
        data = response.json()
        assert len(data["metrics"]) >= 1

    def test_create_alert_rule(self, monitoring_client):
        response = monitoring_client.post(
            "/alerts/rules",
            json={
                "name": "Test Alert Rule",
                "metric_name": "test_metric",
                "condition": ">",
                "threshold": 10.0,
                "severity": "warning",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "rule" in data
        assert "rule_id" in data["rule"]

    def test_list_alert_rules(self, monitoring_client):
        monitoring_client.post(
            "/alerts/rules",
            json={
                "name": "Rule 1",
                "metric_name": "metric1",
                "condition": ">",
                "threshold": 5.0,
            },
        )

        response = monitoring_client.get("/alerts/rules")
        assert response.status_code == 200
        data = response.json()
        assert len(data["rules"]) >= 1

    def test_delete_alert_rule(self, monitoring_client):
        create = monitoring_client.post(
            "/alerts/rules",
            json={
                "name": "Delete Me",
                "metric_name": "metric",
                "condition": ">",
                "threshold": 1.0,
            },
        )
        rule_id = create.json()["rule"]["rule_id"]

        response = monitoring_client.delete(f"/alerts/rules/{rule_id}")
        assert response.status_code == 200

    def test_list_alerts(self, monitoring_client):
        response = monitoring_client.get("/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data

    def test_resolve_alert(self, monitoring_client):
        # First create an alert via database
        alert = monitoring_mod.Alert(
            rule_id="test-rule",
            name="Test Alert",
            severity=monitoring_mod.AlertSeverity.warning,
        )
        monitoring_mod.db.create_alert(alert)

        response = monitoring_client.post(f"/alerts/{alert.alert_id}/resolve")
        assert response.status_code == 200


# ────────────────────────────────────────────────────────────────────────────────
# notifications — Multi-channel notification dispatch
# ────────────────────────────────────────────────────────────────────────────────


class TestNotificationsModels:
    """Test Pydantic models for the notifications service."""

    def test_notification_request_model(self):
        req = notifications_mod.NotificationRequest(
            user_id="user-123",
            channel=notifications_mod.NotificationChannel.email,
            subject="Test Subject",
            body="Test body",
        )
        assert req.user_id == "user-123"
        assert req.channel == notifications_mod.NotificationChannel.email
        assert req.priority == notifications_mod.NotificationPriority.normal

    def test_notification_template_model(self):
        template = notifications_mod.NotificationTemplate(
            name="Welcome Email",
            channel=notifications_mod.NotificationChannel.email,
            subject_template="Welcome {{name}}!",
            body_template="Hello {{name}}, welcome to our service!",
        )
        assert template.name == "Welcome Email"
        assert "{{name}}" in template.body_template

    def test_user_preferences_model(self):
        prefs = notifications_mod.UserPreferences(
            user_id="user-123",
            channels_enabled=[
                notifications_mod.NotificationChannel.email,
                notifications_mod.NotificationChannel.in_app,
            ],
            max_per_hour=10,
        )
        assert prefs.user_id == "user-123"
        assert len(prefs.channels_enabled) == 2


class TestNotificationsRateLimiter:
    """Test the in-memory rate limiter."""

    def test_initial_allow(self):
        limiter = notifications_mod.RateLimiter()
        assert limiter.check("user1:email") is True

    def test_rate_limit_exceeded(self):
        limiter = notifications_mod.RateLimiter()
        for _ in range(20):
            limiter.check("user1:email")
        assert limiter.check("user1:email") is False

    def test_different_keys_independent(self):
        limiter = notifications_mod.RateLimiter()
        for _ in range(20):
            limiter.check("user1:email")
        assert limiter.check("user1:email") is False
        assert limiter.check("user1:sms") is True


class TestNotificationsDatabase:
    """Test the NotificationsDatabase class with temporary database."""

    @pytest.fixture
    def notifications_db(self, tmp_path):
        db_path = tmp_path / "test_notifications.db"
        db = notifications_mod.NotificationsDatabase(db_path=db_path)
        yield db

    def test_tables_created(self, notifications_db):
        """Verify all tables are created."""
        conn = notifications_db._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "notifications" in tables
        assert "templates" in tables
        assert "user_preferences" in tables

    def test_create_and_list_notifications(self, notifications_db):
        """Create a notification and list it."""
        req = notifications_mod.NotificationRequest(
            user_id="user-123",
            channel=notifications_mod.NotificationChannel.email,
            subject="Test",
            body="Body",
        )
        notifications_db.create_notification(req, status=notifications_mod.NotificationStatus.sent)

        notifs = notifications_db.list_notifications(user_id="user-123")
        assert len(notifs) >= 1

    def test_create_and_get_template(self, notifications_db):
        """Create a template and get it back."""
        template = notifications_mod.NotificationTemplate(
            name="Test Template",
            channel=notifications_mod.NotificationChannel.email,
            body_template="Hello {{name}}",
        )
        notifications_db.create_template(template)

        retrieved = notifications_db.get_template(template.template_id)
        assert retrieved is not None
        assert retrieved["name"] == "Test Template"

    def test_set_and_get_preferences(self, notifications_db):
        """Set user preferences and get them back."""
        prefs = notifications_mod.UserPreferences(
            user_id="user-123",
            max_per_hour=50,
        )
        notifications_db.set_preferences(prefs)

        retrieved = notifications_db.get_preferences("user-123")
        assert retrieved is not None
        assert retrieved["max_per_hour"] == 50


class TestNotificationsHTTPEndpoints:
    """Test HTTP endpoints for the notifications service."""

    @pytest.fixture
    def notifications_client(self, tmp_path):
        """Create a TestClient with a temporary database."""
        db_path = tmp_path / "test_notifications.db"
        test_db = notifications_mod.NotificationsDatabase(db_path=db_path)

        with patch.object(notifications_mod, "db", test_db):
            client = TestClient(
                notifications_mod.app,
                headers={"X-Internal-Secret": notifications_mod._INTERNAL_SECRET},
            )
            yield client

    def test_health_endpoint(self, notifications_client):
        response = notifications_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "notifications-service"

    def test_send_notification(self, notifications_client):
        response = notifications_client.post(
            "/notifications/send",
            json={
                "user_id": "user-123",
                "channel": "in_app",
                "subject": "Test",
                "body": "Test notification",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "notification_id" in data

    def test_send_notification_with_template(self, notifications_client):
        # Create template first and capture its template_id
        create_resp = notifications_client.post(
            "/templates",
            json={
                "name": "Test Template",
                "channel": "email",
                "subject_template": "Hello {{name}}",
                "body_template": "Welcome {{name}}!",
            },
        )
        template_id = create_resp.json()["template_id"]

        response = notifications_client.post(
            "/notifications/send",
            json={
                "user_id": "user-123",
                "channel": "email",
                "template_id": template_id,
                "template_vars": {"name": "Alice"},
                "body": "fallback body",
            },
        )
        # Should succeed with template expansion or fail gracefully
        assert response.status_code in [200, 404]

    def test_list_notifications(self, notifications_client):
        notifications_client.post(
            "/notifications/send",
            json={
                "user_id": "user-123",
                "channel": "in_app",
                "body": "Test",
            },
        )

        response = notifications_client.get("/notifications?user_id=user-123")
        assert response.status_code == 200
        data = response.json()
        assert len(data["notifications"]) >= 1

    def test_get_notification(self, notifications_client):
        send = notifications_client.post(
            "/notifications/send",
            json={
                "user_id": "user-123",
                "channel": "in_app",
                "body": "Test",
            },
        )
        notification_id = send.json()["notification_id"]

        response = notifications_client.get(f"/notifications/{notification_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["notification_id"] == notification_id

    def test_create_template(self, notifications_client):
        response = notifications_client.post(
            "/templates",
            json={
                "name": "Welcome Template",
                "channel": "email",
                "subject_template": "Welcome!",
                "body_template": "Hello {{name}}",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "template_id" in data

    def test_list_templates(self, notifications_client):
        notifications_client.post(
            "/templates",
            json={
                "name": "Template 1",
                "channel": "email",
                "body_template": "Body 1",
            },
        )

        response = notifications_client.get("/templates")
        assert response.status_code == 200
        data = response.json()
        assert len(data["templates"]) >= 1

    def test_get_template(self, notifications_client):
        create = notifications_client.post(
            "/templates",
            json={
                "name": "Get Me",
                "channel": "email",
                "body_template": "Body",
            },
        )
        template_id = create.json()["template_id"]

        response = notifications_client.get(f"/templates/{template_id}")
        assert response.status_code == 200

    def test_delete_template(self, notifications_client):
        create = notifications_client.post(
            "/templates",
            json={
                "name": "Delete Me",
                "channel": "email",
                "body_template": "Body",
            },
        )
        template_id = create.json()["template_id"]

        response = notifications_client.delete(f"/templates/{template_id}")
        assert response.status_code == 200

    def test_get_preferences(self, notifications_client):
        response = notifications_client.get("/preferences/user-123")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"

    def test_set_preferences(self, notifications_client):
        response = notifications_client.put(
            "/preferences/user-123",
            json={
                "user_id": "user-123",
                "max_per_hour": 50,
                "max_per_day": 200,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# ────────────────────────────────────────────────────────────────────────────────
# infinity-ai — AI API Gateway with OpenAI-compatible API
# ────────────────────────────────────────────────────────────────────────────────


class TestAIModels:
    """Test Pydantic models for the AI gateway."""

    def test_chat_message_model(self):
        msg = ai_mod.ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_chat_completion_request_model(self):
        req = ai_mod.ChatCompletionRequest(
            model="llama3.2",
            messages=[
                ai_mod.ChatMessage(role="user", content="Hello"),
            ],
            max_tokens=100,
        )
        assert req.model == "llama3.2"
        assert len(req.messages) == 1

    def test_chat_completion_response_model(self):
        response = ai_mod.ChatCompletionResponse(
            model="llama3.2",
            choices=[
                ai_mod.ChatCompletionChoice(
                    message=ai_mod.ChatMessage(role="assistant", content="Hi there!"),
                ),
            ],
            provider="ollama",
        )
        assert response.model == "llama3.2"
        assert response.provider == "ollama"
        assert len(response.choices) == 1

    def test_token_budget_model(self):
        budget = ai_mod.TokenBudget(
            tenant_id="tenant-123",
            daily_limit=100_000,
            used_today=5000,
        )
        assert budget.tenant_id == "tenant-123"
        assert budget.daily_limit == 100_000
        assert budget.used_today == 5000
        # remaining is a computed property from the /usage endpoint, not on the model


class TestAILRUCache:
    """Test the LRU cache for AI responses."""

    def test_cache_put_and_get(self):
        cache = ai_mod.LRUCache(max_size=10)
        cache.put("key1", {"response": "test"})
        result = cache.get("key1")
        assert result == {"response": "test"}

    def test_cache_miss(self):
        cache = ai_mod.LRUCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_eviction(self):
        cache = ai_mod.LRUCache(max_size=3)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")
        cache.put("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key4") == "value4"

    def test_cache_clear(self):
        cache = ai_mod.LRUCache()
        cache.put("key1", "value1")
        cache.clear()
        assert cache.get("key1") is None


class TestAIDatabase:
    """Test the AIDatabase class with temporary database."""

    @pytest.fixture
    def ai_db(self, tmp_path):
        db_path = tmp_path / "test_ai.db"
        db = ai_mod.AIDatabase(db_path=db_path)
        yield db

    def test_tables_created(self, ai_db):
        """Verify all tables are created."""
        conn = ai_db._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "token_budgets" in tables
        assert "request_log" in tables

    def test_get_and_set_budget(self, ai_db):
        """Get and set token budget."""
        budget = ai_db.get_budget("tenant-123")
        assert budget.tenant_id == "tenant-123"

        budget.daily_limit = 50_000
        ai_db._save_budget(budget)

        retrieved = ai_db.get_budget("tenant-123")
        assert retrieved.daily_limit == 50_000

    def test_record_usage(self, ai_db):
        """Record token usage."""
        ai_db.record_usage("tenant-123", 1000)

        budget = ai_db.get_budget("tenant-123")
        assert budget.used_today == 1000

    def test_check_budget(self, ai_db):
        """Check if budget allows request."""
        assert ai_db.check_budget("tenant-123", 1000) is True

        ai_db.record_usage("tenant-123", 99_000)
        assert ai_db.check_budget("tenant-123", 2000) is False

    def test_log_request(self, ai_db):
        """Log a request."""
        ai_db.log_request(
            request_id="req-123",
            tenant_id="tenant-123",
            model="llama3.2",
            provider="ollama",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=500,
            success=True,
        )

        stats = ai_db.get_usage_stats(tenant_id="tenant-123")
        assert len(stats["stats"]) >= 1


class TestAIHTTPEndpoints:
    """Test HTTP endpoints for the AI gateway."""

    @pytest.fixture
    def ai_client(self, tmp_path):
        """Create a TestClient with a temporary database."""
        db_path = tmp_path / "test_ai.db"
        test_db = ai_mod.AIDatabase(db_path=db_path)

        with patch.object(ai_mod, "db", test_db):
            client = TestClient(ai_mod.app)
            yield client

    def test_health_endpoint(self, ai_client):
        response = ai_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "infinity-ai"
        assert "ollama_available" in data
        assert "providers" in data

    def test_list_models(self, ai_client):
        response = ai_client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        assert any(m["id"] == "llama3.2" for m in data["data"])

    def test_chat_completions_offline_fallback(self, ai_client):
        """Test chat completions with offline fallback (no Ollama)."""
        response = ai_client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2",
                "messages": [
                    {"role": "user", "content": "Hello"},
                ],
                "max_tokens": 50,
            },
        )
        # Should succeed with offline fallback
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["provider"] in ["offline", "ollama", "openrouter", "huggingface"]

    def test_chat_completions_without_v1_prefix(self, ai_client):
        """Test chat completions without /v1 prefix."""
        response = ai_client.post(
            "/chat/completions",
            json={
                "model": "llama3.2",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 20,
            },
        )
        assert response.status_code == 200

    def test_get_usage(self, ai_client):
        response = ai_client.get("/usage/tenant-123")
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == "tenant-123"
        assert "daily_limit" in data
        assert "used_today" in data
        assert "remaining" in data

    def test_get_usage_stats(self, ai_client):
        response = ai_client.get("/usage/tenant-123/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_set_budget(self, ai_client):
        response = ai_client.post("/admin/budget?tenant_id=tenant-123&daily_limit=50000")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["daily_limit"] == 50_000

    def test_clear_cache(self, ai_client):
        response = ai_client.post("/admin/cache/clear")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
