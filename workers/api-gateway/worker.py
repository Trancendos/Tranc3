"""
Trancendos API Gateway — Self-Hosted Python Replacement for Cloudflare Worker

Replaces: cloudflare/trancendos-api-gateway/src/index.js
Runs as: FastAPI application on Fly.io or bare metal
Zero external provider dependencies.

Features:
  - JWT-based authentication (HMAC-SHA256)
  - Circuit breaker pattern for upstream resilience
  - Rate limiting (in-memory, replaces Cloudflare KV)
  - Request proxying to microservices
  - Structured JSON logging
  - CORS handling

Routes:
  GET  /health                → health check
  GET  /                      → API info
  /api/auth/*                 → AUTH_SERVICE_URL (public)
  /api/categories/*           → PRODUCTS_SERVICE_URL (public)
  GET /api/products/*         → PRODUCTS_SERVICE_URL (public)
  /api/users/*                → USERS_SERVICE_URL (auth required)
  /api/orders/*               → ORDERS_SERVICE_URL (auth required)
  /api/payments/*             → PAYMENTS_SERVICE_URL (auth required)
  /api/v1/ai/*                → TRANC3_AI_SERVICE_URL (auth required)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import defaultdict

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from Dimensional.sanitize import sanitize_for_log

# ── Configuration ───────────────────────────────────────────────

_jwt_secret_raw = os.getenv("JWT_SECRET")
if not _jwt_secret_raw or _jwt_secret_raw == "dev-jwt-secret-not-for-prod":
    raise RuntimeError(
        "JWT_SECRET is not set (or still the default). "
        "The API Gateway cannot start without a strong unique JWT secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "")
PRODUCTS_SERVICE_URL = os.getenv("PRODUCTS_SERVICE_URL", "")
ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "")
PAYMENTS_SERVICE_URL = os.getenv("PAYMENTS_SERVICE_URL", "")
TRANC3_AI_SERVICE_URL = os.getenv("TRANC3_AI_SERVICE_URL", "http://localhost:8001")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

_REQUIRED_PRODUCTION_UPSTREAMS = {
    "USERS_SERVICE_URL": USERS_SERVICE_URL,
    "PRODUCTS_SERVICE_URL": PRODUCTS_SERVICE_URL,
    "ORDERS_SERVICE_URL": ORDERS_SERVICE_URL,
    "PAYMENTS_SERVICE_URL": PAYMENTS_SERVICE_URL,
    "TRANC3_AI_SERVICE_URL": TRANC3_AI_SERVICE_URL,
}

if ENVIRONMENT == "production":
    missing_upstreams = [
        name for name, value in _REQUIRED_PRODUCTION_UPSTREAMS.items() if not value.strip()
    ]
    if missing_upstreams:
        raise RuntimeError(
            "API Gateway production startup requires upstream service URLs: "
            + ", ".join(missing_upstreams),
        )

_REQUIRED_PRODUCTION_UPSTREAMS = {
    "USERS_SERVICE_URL": USERS_SERVICE_URL,
    "PRODUCTS_SERVICE_URL": PRODUCTS_SERVICE_URL,
    "ORDERS_SERVICE_URL": ORDERS_SERVICE_URL,
    "PAYMENTS_SERVICE_URL": PAYMENTS_SERVICE_URL,
    "TRANC3_AI_SERVICE_URL": TRANC3_AI_SERVICE_URL,
}

if ENVIRONMENT == "production":
    missing_upstreams = [
        name for name, value in _REQUIRED_PRODUCTION_UPSTREAMS.items() if not value.strip()
    ]
    if missing_upstreams:
        raise RuntimeError(
            "API Gateway production startup requires upstream service URLs: "
            + ", ".join(missing_upstreams)
        )

# ── Logger ──────────────────────────────────────────────────────

logger = logging.getLogger("api-gateway")


# ── Rate Limiter (in-memory, replaces Cloudflare KV) ───────────


class RateLimiter:
    def __init__(self, max_requests: int = 1000, window_ms: int = 60_000) -> None:
        self.max = max_requests
        self.window = window_ms / 1000
        self._counts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> tuple[bool, int, float]:
        now = time.time()
        self._counts[key] = [t for t in self._counts[key] if now - t < self.window]
        allowed = len(self._counts[key]) < self.max
        remaining = max(0, self.max - len(self._counts[key]) - (1 if allowed else 0))
        if allowed:
            self._counts[key].append(now)
        return allowed, remaining, now + self.window


rate_limiter = RateLimiter()


# ── Circuit Breaker ────────────────────────────────────────────


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60) -> None:
        self.name = name
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery = recovery_timeout
        self.state = "CLOSED"
        self.next_attempt = 0.0

    async def execute(self, fn):
        if self.state == "OPEN":
            if time.time() < self.next_attempt:
                raise Exception(f"Circuit {self.name} is OPEN")
            self.state = "HALF_OPEN"
        try:
            result = await fn()
            self.failures = 0
            self.state = "CLOSED"
            return result
        except Exception:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state = "OPEN"
                self.next_attempt = time.time() + self.recovery
            raise
        return None

    def get_state(self) -> str:
        return self.state


circuit_breakers = {
    "auth": CircuitBreaker("auth"),
    "users": CircuitBreaker("users"),
    "products": CircuitBreaker("products"),
    "orders": CircuitBreaker("orders"),
    "payments": CircuitBreaker("payments"),
    "ai": CircuitBreaker("ai"),
}


# ── JWT Auth Service ───────────────────────────────────────────


class AuthService:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def verify(self, token: str) -> dict | None:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header, payload, sig = parts
            expected_sig = self._hmac(f"{header}.{payload}")
            if not hmac.compare_digest(sig, expected_sig):
                return None
            decoded = json.loads(self._b64d(payload))
            if decoded.get("exp", 0) < time.time():
                return None
            return decoded
        except Exception:
            return None

    def _hmac(self, msg: str) -> str:
        sig = hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    def _b64d(self, s: str) -> bytes:
        s += "=" * (4 - len(s) % 4)
        return base64.urlsafe_b64decode(s)


auth_service = AuthService(JWT_SECRET)


# ── Proxy ──────────────────────────────────────────────────────


async def proxy_request(
    request: Request, target_base: str, target_path: str, request_id: str
) -> httpx.Response:
    """Proxy request to upstream service."""
    url = f"{target_base}{target_path}{request.url.query and '?' + str(request.url.query) or ''}"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "x-internal-secret"}
    }
    headers["X-Request-ID"] = request_id
    if INTERNAL_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_SECRET

    body = None
    if request.method not in ("GET", "HEAD"):
        body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            follow_redirects=False,
        )
    return None


# ── App ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Trancendos API Gateway (Self-Hosted)",
    version="2.0.0",
    description="API Gateway — replaces Cloudflare Worker. Zero external dependencies.",
)

# OpenTelemetry instrumentation
try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.api-gateway")
except Exception:
    pass  # OTel is optional — never block startup

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    max_age=86400,
)


# ── Routes ──────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "api-gateway-worker",
        "timestamp": int(time.time()),
        "circuitBreakers": {k: v.get_state() for k, v in circuit_breakers.items()},
        "hosting": "self-hosted (replaces Cloudflare Worker)",
    }


@app.get("/")
async def root():
    return {
        "name": "Trancendos API Gateway (Self-Hosted)",
        "version": "2.0.0",
        "status": "operational",
        "timestamp": int(time.time()),
        "services": {
            "auth": "/api/auth/*",
            "users": "/api/users/*",
            "products": "/api/products/*",
            "orders": "/api/orders/*",
            "payments": "/api/payments/*",
            "ai": "/api/v1/ai/*",
        },
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway(request: Request, path: str):
    request_id = str(uuid.uuid4())
    start = time.time()

    # Rate limiting
    ip = request.client.host if request.client else "unknown"
    allowed, remaining, reset_at = rate_limiter.check(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too Many Requests")

    # Route matching
    target_service = None
    target_path = None
    breaker = None

    # Public routes (no auth)
    if path.startswith("api/auth"):
        target_service = AUTH_SERVICE_URL or USERS_SERVICE_URL
        target_path = "/" + path.replace("api/auth", "", 1).lstrip("/")
        breaker = circuit_breakers["users"]
    elif path.startswith("api/categories"):
        target_service = PRODUCTS_SERVICE_URL
        target_path = "/" + path.replace("api/categories", "/categories", 1).lstrip("/")
        breaker = circuit_breakers["products"]
    elif path.startswith("api/products") and request.method == "GET":
        target_service = PRODUCTS_SERVICE_URL
        target_path = "/" + path.replace("api/products", "", 1).lstrip("/")
        breaker = circuit_breakers["products"]

    # Auth-protected routes
    if not target_service:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header required")

        token = auth_header[7:]
        payload = await auth_service.verify(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        if path.startswith("api/v1/ai"):
            target_service = TRANC3_AI_SERVICE_URL
            target_path = "/" + path
            breaker = circuit_breakers["ai"]
        elif path.startswith("api/users"):
            target_service = USERS_SERVICE_URL
            target_path = "/" + path.replace("api/users", "users", 1).lstrip("/")
            breaker = circuit_breakers["users"]
        elif path.startswith("api/orders"):
            target_service = ORDERS_SERVICE_URL
            target_path = "/" + path.replace("api/orders", "", 1).lstrip("/")
            breaker = circuit_breakers["orders"]
        elif path.startswith("api/payments"):
            target_service = PAYMENTS_SERVICE_URL
            target_path = "/" + path.replace("api/payments", "", 1).lstrip("/")
            breaker = circuit_breakers["payments"]
        elif path.startswith("api/products"):
            target_service = PRODUCTS_SERVICE_URL
            target_path = "/" + path.replace("api/products", "", 1).lstrip("/")
            breaker = circuit_breakers["products"]

    if target_service and target_path is not None and breaker:
        try:
            resp = await breaker.execute(
                lambda: proxy_request(request, target_service, target_path, request_id)
            )
            elapsed = time.time() - start
            logger.info(
                "http method=%s path=/%s status=%s ms=%.0f",
                sanitize_for_log(request.method),
                sanitize_for_log(path),
                resp.status_code,
                elapsed * 1000,
            )  # codeql[py/cleartext-logging]
            return JSONResponse(
                content=json.loads(resp.text)
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text,
                status_code=resp.status_code,
                headers={"X-Request-ID": request_id},
            )
        except Exception as e:
            if "Circuit" in str(e):
                raise HTTPException(
                    status_code=503, detail="Service temporarily unavailable. Retry in 60s."
                ) from None
            logger.error(
                "Proxy failed: path=/%s error=%s", sanitize_for_log(path), sanitize_for_log(e)
            )  # codeql[py/cleartext-logging]
            raise HTTPException(
                status_code=502, detail="Failed to reach upstream service."
            ) from None

    raise HTTPException(status_code=404, detail=f"{request.method} /{path} not found")
    return None


# ── Run ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec B104 — Docker/K8s bind
