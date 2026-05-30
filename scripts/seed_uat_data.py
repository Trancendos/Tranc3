#!/usr/bin/env python3
"""
seed_uat_data.py — UAT demo fixture loader
Runs once at UAT stack startup (docker-compose.uat.yml seed-data service).

Creates demo users, exercises key API endpoints, verifies the stack is alive.
All data is clearly marked UAT / demo so it is never confused with production.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "http://api:8000"
TIMEOUT = 30.0
MAX_RETRIES = 10
RETRY_DELAY = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Demo fixtures ─────────────────────────────────────────────────────────────
_UAT_ADMIN_PW = "uat-demo-admin-2024!"  # pragma: allowlist secret  # noqa: S105 — UAT fixture only
_UAT_USER_PW = "uat-demo-user-2024!"  # pragma: allowlist secret  # noqa: S105 — UAT fixture only
_UAT_OP_PW = "uat-demo-operator-2024!"  # pragma: allowlist secret  # noqa: S105 — UAT fixture only

DEMO_USERS = [
    {
        "email": "demo-admin@uat.trancendos.internal",
        "password": _UAT_ADMIN_PW,
        "username": "demo_admin",
        "role": "admin",
    },
    {
        "email": "demo-user@uat.trancendos.internal",
        "password": _UAT_USER_PW,
        "username": "demo_user",
        "role": "user",
    },
    {
        "email": "demo-operator@uat.trancendos.internal",
        "password": _UAT_OP_PW,
        "username": "demo_operator",
        "role": "operator",
    },
]

DEMO_CHAT_MESSAGES = [
    "Hello! This is a UAT acceptance test message.",
    "Can you confirm the AI inference pipeline is responding?",
    "UAT seed data verification complete.",
]


def wait_for_api(client: httpx.Client) -> bool:
    """Poll /health until the API is up or we hit MAX_RETRIES."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(f"{BASE_URL}/health", timeout=5.0)
            if r.status_code == 200:
                log.info("API is healthy (attempt %d)", attempt)
                return True
        except Exception as exc:
            log.info("API not ready yet (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
        time.sleep(RETRY_DELAY)
    return False


def register_user(client: httpx.Client, user: dict[str, Any]) -> dict[str, Any] | None:
    """Register a demo user; skip if already exists (409)."""
    try:
        r = client.post(
            f"{BASE_URL}/auth/register",
            json={
                "email": user["email"],
                "password": user["password"],
                "username": user["username"],
            },
            timeout=TIMEOUT,
        )
        if r.status_code == 201:
            log.info("Created user: %s", user["email"])
            return r.json()
        if r.status_code == 409:
            log.info("User already exists (skipping): %s", user["email"])
            return None
        log.warning("Unexpected status %d for %s: %s", r.status_code, user["email"], r.text[:200])
        return None
    except Exception as exc:
        log.warning("Failed to register %s: %s", user["email"], exc)
        return None


def login_user(client: httpx.Client, user: dict[str, Any]) -> str | None:
    """Log in a demo user and return the access token."""
    try:
        r = client.post(
            f"{BASE_URL}/auth/token",
            data={
                "username": user["email"],
                "password": user["password"],
                "grant_type": "password",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            token = r.json().get("access_token")
            log.info("Logged in: %s", user["email"])
            return token
        log.warning("Login failed for %s (%d): %s", user["email"], r.status_code, r.text[:200])
        return None
    except Exception as exc:
        log.warning("Login error for %s: %s", user["email"], exc)
        return None


def send_demo_chat(client: httpx.Client, token: str, message: str) -> bool:
    """Send a demo chat message to exercise the inference pipeline."""
    try:
        r = client.post(
            f"{BASE_URL}/chat",
            json={
                "message": message,
                "conversation_history": [],
                "session_id": "uat-seed-session",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            log.info("Chat OK: '%s...'", message[:40])
            return True
        log.warning("Chat returned %d: %s", r.status_code, r.text[:200])
        return False
    except Exception as exc:
        log.warning("Chat error: %s", exc)
        return False


def check_worker_health(client: httpx.Client) -> dict[str, bool]:
    """Check health of P0/P1 workers from the API perspective."""
    workers = {
        "infinity-ws": "http://infinity-ws:8004/health",
        "infinity-auth": "http://infinity-auth:8005/health",
        "users-service": "http://users-service:8006/health",
        "infinity-ai": "http://infinity-ai:8009/health",
    }
    results: dict[str, bool] = {}
    for name, url in workers.items():
        try:
            r = client.get(url, timeout=5.0)
            results[name] = r.status_code == 200
            status = "UP" if results[name] else f"DOWN ({r.status_code})"
            log.info("Worker %-20s %s", name, status)
        except Exception as exc:
            results[name] = False
            log.warning("Worker %-20s UNREACHABLE: %s", name, exc)
    return results


def print_summary(results: dict[str, Any]) -> None:
    log.info("")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("UAT SEED SUMMARY")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("Users created/verified : %d", results["users_ok"])
    log.info("Chat messages sent     : %d", results["chats_ok"])
    log.info("Workers healthy        : %d / %d", results["workers_up"], results["workers_total"])
    log.info("Overall status         : %s", "✅ PASS" if results["pass"] else "⚠️  PARTIAL")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main() -> int:
    log.info("Tranc3 UAT Seed Data Loader starting…")

    with httpx.Client(follow_redirects=True) as client:
        # 1. Wait for API
        if not wait_for_api(client):
            log.error("API did not become healthy after %d attempts. Aborting.", MAX_RETRIES)
            return 1

        # 2. Register demo users
        users_ok = 0
        admin_token: str | None = None
        for user in DEMO_USERS:
            register_user(client, user)
            token = login_user(client, user)
            if token:
                users_ok += 1
                if user["role"] == "admin" and admin_token is None:
                    admin_token = token

        # 3. Send demo chat messages (uses admin token if available)
        chats_ok = 0
        if admin_token:
            for msg in DEMO_CHAT_MESSAGES:
                if send_demo_chat(client, admin_token, msg):
                    chats_ok += 1
        else:
            log.warning("No admin token available — skipping chat seed")

        # 4. Check worker health
        worker_health = check_worker_health(client)
        workers_up = sum(1 for v in worker_health.values() if v)
        workers_total = len(worker_health)

        # 5. Summary
        overall_pass = users_ok >= 1 and workers_up >= 2  # P0 minimum
        results = {
            "users_ok": users_ok,
            "chats_ok": chats_ok,
            "workers_up": workers_up,
            "workers_total": workers_total,
            "pass": overall_pass,
        }
        print_summary(results)

        # Write JSON summary for CI/pipeline consumption
        summary_path = "/app/uat_seed_summary.json"
        try:
            with open(summary_path, "w") as f:
                json.dump(results, f, indent=2)
            log.info("Summary written to %s", summary_path)
        except Exception:
            pass  # non-critical

        return 0 if overall_pass else 2


if __name__ == "__main__":
    sys.exit(main())
