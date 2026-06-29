/**
 * Trancendos API Gateway
 *
 * Routes (no auth required — public):
 *   /api/auth/*             → USERS_SERVICE_URL  (infinity-auth-api)
 *   /api/categories/*       → PRODUCTS_SERVICE_URL
 *   GET /api/products/*     → PRODUCTS_SERVICE_URL
 *   GET /api/products/search → PRODUCTS_SERVICE_URL
 *
 * Routes (auth required):
 *   /api/users/*            → USERS_SERVICE_URL
 *   /api/products/*         → PRODUCTS_SERVICE_URL
 *   /api/orders/*           → ORDERS_SERVICE_URL
 *   /api/payments/*         → PAYMENTS_SERVICE_URL
 *
 * ── Tranc3 AI routes (auth required) ──
 *   /api/v1/ai/*            → TRANC3_AI_SERVICE_URL   (tranc3-ai worker)
 *
 * Bindings:
 *   KV: CACHE       — rate-limit counters
 *   Vars:
 *     USERS_SERVICE_URL, PRODUCTS_SERVICE_URL, ORDERS_SERVICE_URL,
 *     PAYMENTS_SERVICE_URL, TRANC3_AI_SERVICE_URL, JWT_SECRET
 */

// ── Shared utilities ──────────────────────────────────────────────────────────

class Logger {
  constructor(ctx = {}) { this.ctx = ctx; }
  withContext(c) { return new Logger({ ...this.ctx, ...c }); }
  log(level, msg, extra) {
    console.log(JSON.stringify({ level, msg, ts: Date.now(), ...this.ctx, ...extra }));
  }
  info(m, e)  { this.log("info",  m, e); }
  warn(m, e)  { this.log("warn",  m, e); }
  error(m, e) { this.log("error", m, e); }
  http(method, path, status, ms) {
    this.info("http", { method, path, status, ms });
  }
}

class RateLimiter {
  constructor(kv, { maxRequests = 1000, windowMs = 60_000 } = {}) {
    this.kv = kv; this.max = maxRequests; this.window = windowMs;
  }
  async check(id) {
    const key = `rl:${id}`;
    const now = Date.now();
    const raw = await this.kv.get(key);
    let { count = 0, start = now } = raw ? JSON.parse(raw) : {};
    if (now - start > this.window) { count = 0; start = now; }
    const allowed = count < this.max;
    const remaining = Math.max(0, this.max - count - (allowed ? 1 : 0));
    if (allowed) {
      count++;
      await this.kv.put(key, JSON.stringify({ count, start }), {
        expirationTtl: Math.ceil(this.window / 1000),
      });
    }
    return { allowed, remaining, resetAt: start + this.window };
  }
}

class AuthService {
  constructor(secret) { this.secret = secret; }
  async verify(token) {
    try {
      const [header, payload, sig] = token.split(".");
      if (!header || !payload || !sig) return null;
      const expected = await this._hmac(`${header}.${payload}`);
      if (sig !== expected) return null;
      const decoded = JSON.parse(this._b64d(payload));
      if (decoded.exp < Math.floor(Date.now() / 1000)) return null;
      return decoded;
    } catch { return null; }
  }
  async _hmac(msg) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey("raw", enc.encode(this.secret),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const sig = await crypto.subtle.sign("HMAC", key, enc.encode(msg));
    return this._ab64(sig);
  }
  _b64d(s) {
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    return atob(s);
  }
  _ab64(buf) {
    const bytes = new Uint8Array(buf);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
}

class CircuitBreaker {
  constructor(name, { failureThreshold = 5, recoveryTimeout = 60_000 } = {}) {
    this.name = name; this.failures = 0;
    this.threshold = failureThreshold; this.recovery = recoveryTimeout;
    this.state = "CLOSED"; this.nextAttempt = 0;
  }
  async execute(fn) {
    if (this.state === "OPEN") {
      if (Date.now() < this.nextAttempt) throw new Error(`Circuit ${this.name} is OPEN`);
      this.state = "HALF_OPEN";
    }
    try {
      const r = await fn();
      this.failures = 0; this.state = "CLOSED"; return r;
    } catch (e) {
      this.failures++;
      if (this.failures >= this.threshold) {
        this.state = "OPEN";
        this.nextAttempt = Date.now() + this.recovery;
      }
      throw e;
    }
  }
  getState() { return this.state; }
}

// ── Proxy ─────────────────────────────────────────────────────────────────────

async function proxy(request, targetBase, targetPath, requestId) {
  const orig = new URL(request.url);
  const url  = `${targetBase}${targetPath}${orig.search}`;
  const hdrs = new Headers();
  for (const [k, v] of request.headers) {
    if (!["host"].includes(k.toLowerCase())) hdrs.set(k, v);
  }
  hdrs.set("X-Request-ID", requestId);

  const body = ["GET", "HEAD"].includes(request.method) ? null : request.body;
  const res  = await fetch(new Request(url, { method: request.method, headers: hdrs, body, redirect: "manual" }));

  const out = new Headers();
  const skip = new Set(["content-encoding", "content-length", "transfer-encoding", "connection"]);
  for (const [k, v] of res.headers) if (!skip.has(k.toLowerCase())) out.set(k, v);
  out.set("Access-Control-Allow-Origin", "*");
  out.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH");
  out.set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID");
  out.set("X-Request-ID", requestId);
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: out });
}

// ── Main ──────────────────────────────────────────────────────────────────────

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Request-ID",
  "Access-Control-Max-Age": "86400",
};

function jsonResp(data, status, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS, ...extra },
  });
}

export default {
  async fetch(request, env) {
    const url       = new URL(request.url);
    const path      = url.pathname;
    const method    = request.method;
    const logger    = new Logger({ service: "api-gateway" });
    const requestId = crypto.randomUUID();
    const start     = Date.now();

    if (method === "OPTIONS") return new Response(null, { status: 204, headers: { ...CORS, "X-Request-ID": requestId } });

    const rl = new RateLimiter(env.CACHE, { maxRequests: 1000, windowMs: 60_000 });
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const { allowed, remaining, resetAt } = await rl.check(ip);

    if (!allowed) {
      return jsonResp({ error: "Too Many Requests", message: "Rate limit exceeded. Please try again later." }, 429, {
        "Retry-After": "60",
        "X-RateLimit-Limit": "1000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": String(resetAt),
      });
    }

    const rateLimitHeaders = {
      "X-RateLimit-Limit": "1000",
      "X-RateLimit-Remaining": String(remaining),
      "X-RateLimit-Reset": String(resetAt),
    };

    const cb = {
      users:    new CircuitBreaker("users"),
      products: new CircuitBreaker("products"),
      orders:   new CircuitBreaker("orders"),
      payments: new CircuitBreaker("payments"),
      ai:       new CircuitBreaker("ai"),
    };

    // Health
    if (path === "/health" && method === "GET") {
      return jsonResp({
        status: "healthy", service: "api-gateway", timestamp: Date.now(),
        circuitBreakers: Object.fromEntries(Object.entries(cb).map(([k, v]) => [k, v.getState()])),
      }, 200);
    }

    // Root
    if (path === "/" && method === "GET") {
      return jsonResp({
        name: "Trancendos API Gateway", version: "2.0.0",
        status: "operational", timestamp: Date.now(), requestId,
        services: {
          auth:     "/api/auth/*",
          users:    "/api/users/*",
          products: "/api/products/*",
          orders:   "/api/orders/*",
          payments: "/api/payments/*",
          ai:       "/api/v1/ai/*",
        },
      }, 200, { ...rateLimitHeaders, "X-Request-ID": requestId });
    }

    // ── Route matching ──────────────────────────────────────────────────────
    let targetService = null;
    let targetPath    = null;
    let breaker       = null;
    let requiresAuth  = true;

    // Public (no auth)
    if (path === "/health" || path === "/api/health" || path.startsWith("/health/")) {
      targetService = env.TRANC3_BACKEND_URL || "https://trancendos-backend.fly.dev";
      targetPath = path; breaker = cb.ai; requiresAuth = false;
    } else if (path === "/mcp" || path.startsWith("/mcp/") || path === "/api/mcp" || path.startsWith("/api/mcp/")) {
      // MCP tools are authenticated at the MCP layer, not the gateway
      targetService = env.TRANC3_BACKEND_URL || "https://trancendos-backend.fly.dev";
      targetPath = path; breaker = cb.ai; requiresAuth = false;
    } else if (path.startsWith("/api/auth")) {
      targetService = env.USERS_SERVICE_URL; targetPath = path.replace("/api/auth", "");
      breaker = cb.users; requiresAuth = false;
    } else if (path.startsWith("/api/categories")) {
      targetService = env.PRODUCTS_SERVICE_URL; targetPath = path.replace("/api/categories", "/categories");
      breaker = cb.products; requiresAuth = false;
    } else if (path.startsWith("/api/products") && method === "GET") {
      targetService = env.PRODUCTS_SERVICE_URL; targetPath = path.replace("/api/products", "/products");
      breaker = cb.products; requiresAuth = false;
    }

    // Auth-protected (with JWT check)
    if (!targetService) {
      const authHeader = request.headers.get("Authorization");
      if (!authHeader?.startsWith("Bearer ")) {
        return jsonResp({ error: "Unauthorized", message: "Authorization header required", requestId }, 401, { "X-Request-ID": requestId });
      }
      const token   = authHeader.slice(7);
      const auth    = new AuthService(env.JWT_SECRET);
      const payload = await auth.verify(token);
      if (!payload) {
        return jsonResp({ error: "Unauthorized", message: "Invalid or expired token", requestId }, 401, { "X-Request-ID": requestId });
      }

      if (path.startsWith("/api/v1/ai")) {
        targetService = env.TRANC3_AI_SERVICE_URL || "https://tranc3-ai.trancendos.workers.dev";
        targetPath    = path; // keep full path — tranc3-ai handles its own routing
        breaker       = cb.ai;
      } else if (path.startsWith("/api/users")) {
        targetService = env.USERS_SERVICE_URL; targetPath = path.replace("/api/users", ""); breaker = cb.users;
      } else if (path.startsWith("/api/orders")) {
        targetService = env.ORDERS_SERVICE_URL; targetPath = path.replace("/api/orders", "/orders"); breaker = cb.orders;
      } else if (path.startsWith("/api/payments")) {
        targetService = env.PAYMENTS_SERVICE_URL; targetPath = path.replace("/api/payments", "/payments"); breaker = cb.payments;
      } else if (path.startsWith("/api/products")) {
        targetService = env.PRODUCTS_SERVICE_URL; targetPath = path.replace("/api/products", "/products"); breaker = cb.products;
      } else if (path.startsWith("/api/")) {
        // Fallback: route remaining /api/* paths to tranc3-backend on Fly.io
        targetService = env.TRANC3_BACKEND_URL || "https://trancendos-backend.fly.dev";
        targetPath    = path;
        breaker       = cb.ai;
      } else {
        return jsonResp({ error: "Not Found", message: "No route matched", requestId }, 404, { "X-Request-ID": requestId });
      }
    }

    if (targetService && targetPath !== null) {
      try {
        const res = await breaker.execute(() => proxy(request, targetService, targetPath, requestId));
        logger.http(method, path, res.status, Date.now() - start);
        return res;
      } catch (e) {
        if (e.message.includes("Circuit")) {
          return jsonResp({ error: "Service Unavailable", message: "Service temporarily unavailable. Retry in 60s.", requestId }, 503, { "Retry-After": "60" });
        }
        logger.error("Proxy failed", { path, error: e.message });
        return jsonResp({ error: "Bad Gateway", message: "Failed to reach upstream service.", requestId }, 502);
      }
    }

    return jsonResp({ error: "Not Found", message: `${method} ${path} not found`, requestId }, 404);
  },
};
