"""
Infinity Auth — Router integration tests
==========================================
Tests for HTTP endpoints using FastAPI TestClient with an in-memory
SQLite DB and mocked worker_kit. No real JWT_SECRET or external deps needed.
"""

from __future__ import annotations

import json
import pytest


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_returns_200(test_client):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "infinity-auth"


# ── /auth/register ────────────────────────────────────────────────────────────


def test_register_new_user(test_client):
    resp = test_client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "securepass123",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_username(test_client):
    payload = {"username": "bob", "email": "bob@example.com", "password": "password123"}
    test_client.post("/auth/register", json=payload)
    resp = test_client.post(
        "/auth/register",
        json={"username": "bob", "email": "bob2@example.com", "password": "password123"},
    )
    assert resp.status_code == 409
    assert "Username already exists" in resp.json()["detail"]


def test_register_duplicate_email(test_client):
    test_client.post(
        "/auth/register",
        json={"username": "carol", "email": "carol@example.com", "password": "password123"},
    )
    resp = test_client.post(
        "/auth/register",
        json={"username": "carol2", "email": "carol@example.com", "password": "password123"},
    )
    assert resp.status_code == 409
    assert "Email already registered" in resp.json()["detail"]


def test_register_short_password_rejected(test_client):
    resp = test_client.post(
        "/auth/register",
        json={"username": "dave", "email": "dave@example.com", "password": "short"},
    )
    assert resp.status_code == 422  # Pydantic validation failure


# ── /auth/login ───────────────────────────────────────────────────────────────


def test_login_valid_credentials(test_client):
    test_client.post(
        "/auth/register",
        json={"username": "eve", "email": "eve@example.com", "password": "evepassword"},
    )
    resp = test_client.post(
        "/auth/login",
        json={"username": "eve", "password": "evepassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "eve"
    assert "access_token" in data


def test_login_wrong_password(test_client):
    test_client.post(
        "/auth/register",
        json={"username": "frank", "email": "frank@example.com", "password": "frankpassword"},
    )
    resp = test_client.post(
        "/auth/login",
        json={"username": "frank", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_login_unknown_user(test_client):
    resp = test_client.post(
        "/auth/login",
        json={"username": "nonexistent", "password": "doesnotmatter"},
    )
    assert resp.status_code == 401


# ── /auth/refresh ─────────────────────────────────────────────────────────────


def test_refresh_token_rotation(test_client):
    reg = test_client.post(
        "/auth/register",
        json={"username": "grace", "email": "grace@example.com", "password": "gracepassword"},
    )
    refresh_token = reg.json()["refresh_token"]

    resp = test_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # token rotated


def test_refresh_invalid_token(test_client):
    resp = test_client.post("/auth/refresh", json={"refresh_token": "invalid-token-value"})
    assert resp.status_code == 401


# ── /auth/logout ──────────────────────────────────────────────────────────────


def test_logout_revokes_session(test_client):
    reg = test_client.post(
        "/auth/register",
        json={"username": "henry", "email": "henry@example.com", "password": "henrypassword"},
    )
    data = reg.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    resp = test_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200

    # After logout, the old refresh token must be revoked
    resp2 = test_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


# ── /auth/me ──────────────────────────────────────────────────────────────────


def test_get_profile(test_client):
    reg = test_client.post(
        "/auth/register",
        json={"username": "iris", "email": "iris@example.com", "password": "irispassword"},
    )
    access_token = reg.json()["access_token"]

    resp = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["username"] == "iris"
    assert profile["email"] == "iris@example.com"
    assert "role" in profile
    assert "tier" in profile
    assert "infinity_role" in profile


def test_get_profile_without_token(test_client):
    resp = test_client.get("/auth/me")
    assert resp.status_code == 403  # HTTPBearer returns 403 when no header


# ── /auth/verify ─────────────────────────────────────────────────────────────


def test_verify_valid_token(test_client):
    reg = test_client.post(
        "/auth/register",
        json={"username": "jack", "email": "jack@example.com", "password": "jackpassword"},
    )
    access_token = reg.json()["access_token"]

    resp = test_client.get(
        "/auth/verify",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# ── OIDC Discovery ────────────────────────────────────────────────────────────


def test_oidc_discovery_document(test_client):
    resp = test_client.get("/.well-known/openid-configuration")
    assert resp.status_code == 200
    data = resp.json()
    assert "issuer" in data
    assert "token_endpoint" in data
    assert "authorization_endpoint" in data


def test_jwks_endpoint(test_client):
    resp = test_client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    assert "keys" in resp.json()


# ── Role management ───────────────────────────────────────────────────────────


def test_update_role_requires_admin(test_client):
    # Register a regular user
    reg = test_client.post(
        "/auth/register",
        json={"username": "kurt", "email": "kurt@example.com", "password": "kurtpassword"},
    )
    data = reg.json()
    access_token = data["access_token"]
    user_id = data["user_id"]

    resp = test_client.put(
        f"/auth/users/{user_id}/role?role=admin",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 403
