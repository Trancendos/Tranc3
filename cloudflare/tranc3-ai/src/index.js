/**
 * Tranc3 AI Worker — Cloudflare Edge
 *
 * Routes:
 *   GET  /                         → API info
 *   GET  /health                   → health check
 *   GET  /api/v1/ai/models         → list available models
 *   POST /api/v1/ai/chat           → chat / text generation
 *   POST /api/v1/ai/embeddings     → text embeddings
 *   POST /api/v1/ai/analyze-emotion → emotion detection
 *   POST /api/v1/ai/consciousness  → consciousness scoring
 *
 * Inference strategy (in order):
 *   1. If TRANC3_BACKEND_URL is set → proxy to the Tranc3 Python backend
 *   2. Otherwise → Cloudflare Workers AI (hosted models)
 *
 * Auth: validated against infinity-auth-api via TRANC3_AUTH_URL
 */

// ── Constants ────────────────────────────────────────────────────────────────

const MODELS = {
  default: "@cf/meta/llama-3.1-8b-instruct",
  fast: "@cf/mistral/mistral-7b-instruct-v0.1",
  embedding: "@cf/baai/bge-small-en-v1.5",
  tranc3: "tranc3-base",
};

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
};

// ── CORS ─────────────────────────────────────────────────────────────────────

const DEFAULT_ORIGINS = [
  "https://trancendos.com",
  "https://www.trancendos.com",
  "https://infinity-portal.pages.dev",
  "https://infinity-portal.com",
  "http://localhost:5173",
  "http://localhost:3000",
];

function getAllowedOrigin(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  const extra = (env.ALLOWED_ORIGINS || "").split(",").map((o) => o.trim()).filter(Boolean);
  const all = [...new Set([...DEFAULT_ORIGINS, ...extra])];
  if (all.includes(origin)) return origin;
  if (origin.endsWith(".trancendos.com")) return origin;
  if (origin.endsWith(".infinity-portal.pages.dev")) return origin;
  return null;
}

function corsHeaders(request, env) {
  const origin = getAllowedOrigin(request, env);
  if (!origin) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Request-ID",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Max-Age": "86400",
  };
}

function json(data, status = 200, extra = {}, request, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...SECURITY_HEADERS,
      ...(request && env ? corsHeaders(request, env) : {}),
      ...extra,
    },
  });
}

function err(message, status = 400, request, env, detail) {
  return json({ error: message, detail: detail ?? null }, status, {}, request, env);
}

// ── Auth ─────────────────────────────────────────────────────────────────────

async function verifyAuth(request, env) {
  const header = request.headers.get("Authorization");
  if (!header?.startsWith("Bearer ")) return null;

  // If no auth URL configured, skip validation in dev mode
  if (!env.TRANC3_AUTH_URL && env.ENVIRONMENT !== "production") {
    return { userId: "dev", role: "admin" };
  }

  const authUrl = env.TRANC3_AUTH_URL || "https://infinity-auth-api.trancendos.workers.dev";
  try {
    const res = await fetch(`${authUrl}/api/v1/auth/me`, {
      headers: { Authorization: header },
    });
    if (!res.ok) return null;
    const user = await res.json();
    return { userId: user.id, role: user.role, email: user.email };
  } catch {
    return null;
  }
}

// ── Backend proxy ─────────────────────────────────────────────────────────────

async function proxyToBackend(request, env, path) {
  const backendUrl = `${env.TRANC3_BACKEND_URL}${path}`;
  const headers = new Headers(request.headers);
  headers.set("X-Forwarded-For", request.headers.get("CF-Connecting-IP") || "");
  headers.set("X-Tranc3-Edge", "cloudflare");

  const body = ["GET", "HEAD"].includes(request.method) ? null : request.body;
  const res = await fetch(backendUrl, {
    method: request.method,
    headers,
    body,
  });
  return res;
}

// ── CF Workers AI inference ───────────────────────────────────────────────────

async function cfChat(env, messages, model) {
  const selectedModel = model === "tranc3-base" ? MODELS.default : (model || MODELS.default);
  const response = await env.AI.run(selectedModel, { messages });
  return {
    id: crypto.randomUUID(),
    object: "chat.completion",
    model: selectedModel,
    backend: "cloudflare-workers-ai",
    choices: [{
      index: 0,
      message: {
        role: "assistant",
        content: response.response || response.result || "",
      },
      finish_reason: "stop",
    }],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

async function cfEmbeddings(env, input) {
  const texts = Array.isArray(input) ? input : [input];
  const response = await env.AI.run(MODELS.embedding, { text: texts });
  const embeddings = Array.isArray(response.data) ? response.data : [response.data];
  return {
    object: "list",
    model: MODELS.embedding,
    backend: "cloudflare-workers-ai",
    data: embeddings.map((vec, i) => ({ object: "embedding", index: i, embedding: vec })),
    usage: { prompt_tokens: 0, total_tokens: 0 },
  };
}

// ── Route handlers ────────────────────────────────────────────────────────────

async function handleModels(request, env) {
  const hasTranc3Backend = !!env.TRANC3_BACKEND_URL;
  return json({
    object: "list",
    data: [
      {
        id: "tranc3-base",
        object: "model",
        name: "Tranc3 Base",
        description: "Tranc3 consciousness-aware language model",
        available: hasTranc3Backend,
        backend: hasTranc3Backend ? "tranc3-backend" : "cloudflare-workers-ai",
        capabilities: ["chat", "consciousness-scoring", "emotion-detection"],
      },
      {
        id: MODELS.default,
        object: "model",
        name: "LLaMA 3.1 8B Instruct",
        available: true,
        backend: "cloudflare-workers-ai",
        capabilities: ["chat"],
      },
      {
        id: MODELS.fast,
        object: "model",
        name: "Mistral 7B Instruct",
        available: true,
        backend: "cloudflare-workers-ai",
        capabilities: ["chat"],
      },
      {
        id: MODELS.embedding,
        object: "model",
        name: "BGE Small EN v1.5",
        available: true,
        backend: "cloudflare-workers-ai",
        capabilities: ["embeddings"],
      },
    ],
  }, 200, {}, request, env);
}

async function handleChat(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const { messages, model, stream } = body;
  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return err("messages array is required", 400, request, env);
  }
  if (stream) {
    return err("Streaming not supported on edge; use the Tranc3 backend directly", 400, request, env);
  }

  // Proxy to Python backend if available
  if (env.TRANC3_BACKEND_URL) {
    try {
      const res = await proxyToBackend(
        new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify(body) }),
        env,
        "/chat",
      );
      if (res.ok) return res;
    } catch (e) {
      console.error("Backend proxy failed, falling back to CF Workers AI:", e.message);
    }
  }

  // Fall back to CF Workers AI
  try {
    const result = await cfChat(env, messages, model);
    return json(result, 200, {}, request, env);
  } catch (e) {
    console.error("CF Workers AI error:", e);
    return err("Inference failed", 502, request, env, e.message);
  }
}

async function handleEmbeddings(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const { input, model } = body;
  if (!input) return err("input is required", 400, request, env);

  if (env.TRANC3_BACKEND_URL) {
    try {
      const res = await proxyToBackend(
        new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify(body) }),
        env,
        "/embeddings",
      );
      if (res.ok) return res;
    } catch (e) {
      console.error("Backend proxy failed:", e.message);
    }
  }

  try {
    const result = await cfEmbeddings(env, input);
    return json(result, 200, {}, request, env);
  } catch (e) {
    return err("Embedding failed", 502, request, env, e.message);
  }
}

async function handleEmotion(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const { text } = body;
  if (!text) return err("text is required", 400, request, env);

  if (env.TRANC3_BACKEND_URL) {
    try {
      const res = await proxyToBackend(
        new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify(body) }),
        env,
        "/analyze-emotion",
      );
      if (res.ok) return res;
    } catch (e) {
      console.error("Backend proxy failed:", e.message);
    }
  }

  // Lightweight CF Workers AI fallback: classify via LLM
  try {
    const msgs = [
      { role: "system", content: "You are an emotion classifier. Respond ONLY with a JSON object like: {\"dominant\":\"neutral\",\"scores\":{\"neutral\":0.7,\"happy\":0.1,\"sad\":0.1,\"angry\":0.05,\"surprised\":0.03,\"fearful\":0.01,\"disgusted\":0.01}}" },
      { role: "user", content: `Classify the emotion in this text: "${text}"` },
    ];
    const response = await env.AI.run(MODELS.default, { messages: msgs });
    const raw = response.response || "{}";
    const parsed = JSON.parse(raw.match(/\{[\s\S]*\}/)?.[0] || "{}");
    return json({
      text,
      dominant: parsed.dominant || "neutral",
      scores: parsed.scores || { neutral: 1.0 },
      backend: "cloudflare-workers-ai",
    }, 200, {}, request, env);
  } catch (e) {
    return json({
      text,
      dominant: "neutral",
      scores: { neutral: 1.0 },
      backend: "fallback",
    }, 200, {}, request, env);
  }
}

async function handleConsciousness(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  if (env.TRANC3_BACKEND_URL) {
    try {
      const res = await proxyToBackend(
        new Request(request.url, { method: "POST", headers: request.headers, body: JSON.stringify(body) }),
        env,
        "/consciousness/score",
      );
      if (res.ok) return res;
    } catch (e) {
      console.error("Backend proxy failed:", e.message);
    }
  }

  // Without the full Tranc3 engine, return a placeholder
  return json({
    phi: 0.0,
    awareness: 0.0,
    is_conscious: false,
    note: "Full consciousness scoring requires the Tranc3 backend. Set TRANC3_BACKEND_URL to enable.",
    backend: "edge-placeholder",
  }, 200, {}, request, env);
}

// ── Main handler ──────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const { pathname: path, method } = Object.assign(url, { method: request.method });
    const requestId = crypto.randomUUID();

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: { ...corsHeaders(request, env), ...SECURITY_HEADERS, "X-Request-ID": requestId },
      });
    }

    try {
      // Public endpoints (no auth required)
      if ((path === "/" || path === "/api/v1/ai") && method === "GET") {
        return json({
          name: "Tranc3 AI API",
          version: "1.0.0",
          environment: env.ENVIRONMENT || "production",
          backend: env.TRANC3_BACKEND_URL ? "tranc3-python" : "cloudflare-workers-ai",
          endpoints: [
            "GET  /health",
            "GET  /api/v1/ai/models",
            "POST /api/v1/ai/chat",
            "POST /api/v1/ai/embeddings",
            "POST /api/v1/ai/analyze-emotion",
            "POST /api/v1/ai/consciousness",
          ],
        }, 200, { "X-Request-ID": requestId }, request, env);
      }

      if (path === "/health" && method === "GET") {
        return json({
          status: "healthy",
          service: "tranc3-ai",
          version: "1.0.0",
          environment: env.ENVIRONMENT || "production",
          backend: env.TRANC3_BACKEND_URL ? "tranc3-python" : "cloudflare-workers-ai",
          timestamp: new Date().toISOString(),
        }, 200, { "X-Request-ID": requestId }, request, env);
      }

      if (path === "/api/v1/ai/models" && method === "GET") {
        return handleModels(request, env);
      }

      // Auth-protected endpoints
      const auth = await verifyAuth(request, env);
      if (!auth) {
        return err("Authentication required", 401, request, env);
      }

      if (path === "/api/v1/ai/chat" && method === "POST") {
        return handleChat(request, env);
      }

      if (path === "/api/v1/ai/embeddings" && method === "POST") {
        return handleEmbeddings(request, env);
      }

      if (path === "/api/v1/ai/analyze-emotion" && method === "POST") {
        return handleEmotion(request, env);
      }

      if (path === "/api/v1/ai/consciousness" && method === "POST") {
        return handleConsciousness(request, env);
      }

      return err(`Route not found: ${method} ${path}`, 404, request, env);
    } catch (e) {
      console.error("Unhandled error:", e);
      return err(
        env.ENVIRONMENT === "production" ? "Internal server error" : String(e),
        500, request, env,
      );
    }
  },
};
