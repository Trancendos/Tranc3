/**
 * Tranc3 AI Worker — Cloudflare Edge
 *
 * Self-owned inference. Zero external AI service dependencies.
 *
 * Routes:
 *   GET  /                          → API info
 *   GET  /health                    → health check
 *   GET  /api/v1/ai/models          → list available models
 *   POST /api/v1/ai/chat            → chat / text generation
 *   POST /api/v1/ai/embeddings      → text embeddings
 *   POST /api/v1/ai/analyze-emotion → emotion detection
 *   POST /api/v1/ai/consciousness   → consciousness scoring
 *   POST /api/v1/ai/tokenize        → tokenization
 *   POST /api/v1/ai/predict         → next-token prediction
 *
 * Inference strategy (in priority order — NO external AI APIs):
 *   1. TRANC3_BACKEND_URL  → full Tranc3 Python backend (FastAPI + WorkerPool)
 *   2. TRANC3_NANO_URL     → Tranc3 nanoservices HTTP server (nano_server.py)
 *   3. Deterministic stub  → honest "model not trained yet" response
 *
 * To deploy your own backend (free):
 *   Fly.io free tier: fly deploy (3 shared VMs free)
 *   Self-hosted VPS:  docker run -p 8000:8000 tranc3:latest
 *
 * Bindings required (set via wrangler secret):
 *   TRANC3_AUTH_URL     → infinity-auth-api URL (JWT validation)
 *   TRANC3_BACKEND_URL  → Tranc3 FastAPI backend (optional but recommended)
 *   TRANC3_NANO_URL     → Nanoservices server (optional fallback)
 *   ALLOWED_ORIGINS     → extra CORS origins (comma-separated)
 */

// ── Constants ────────────────────────────────────────────────────────────────

const TRANC3_MODELS = {
  "tranc3-base":         { name: "Tranc3 Base",        backend: "tranc3-own",   capabilities: ["chat", "emotion", "consciousness"] },
  "tranc3-fast":         { name: "Tranc3 Fast",         backend: "tranc3-own",   capabilities: ["chat"] },
  "tranc3-embeddings":   { name: "Tranc3 Embeddings",   backend: "tranc3-own",   capabilities: ["embeddings"] },
  "dorris-fontaine":     { name: "Dorris Fontaine",     backend: "tranc3-own",   capabilities: ["chat", "finance"] },
  "cornelius-macintyre": { name: "Cornelius MacIntyre", backend: "tranc3-own",   capabilities: ["chat", "orchestration"] },
  "the-guardian":        { name: "The Guardian",        backend: "tranc3-own",   capabilities: ["chat", "security"] },
  "vesper-nightingale":  { name: "Vesper Nightingale",  backend: "tranc3-own",   capabilities: ["chat", "healthcare"] },
  "atlas-meridian":      { name: "Atlas Meridian",      backend: "tranc3-own",   capabilities: ["chat", "infrastructure"] },
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

  // Dev bypass when no auth URL is configured
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

// ── Self-owned backend call ───────────────────────────────────────────────────
//
// Priority:
//   1. Full backend  (TRANC3_BACKEND_URL  → /nano/<endpoint>)
//   2. Nanoservices  (TRANC3_NANO_URL     → /<endpoint>)
//   3. Stub response (no external service)

async function callNano(env, endpoint, payload) {
  // Try full backend first
  if (env.TRANC3_BACKEND_URL) {
    try {
      const res = await fetch(`${env.TRANC3_BACKEND_URL}/nano/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Tranc3-Edge": "cloudflare" },
        body: JSON.stringify(payload),
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn(`Backend ${endpoint} failed: ${e.message}`);
    }
  }

  // Try dedicated nanoservices server
  if (env.TRANC3_NANO_URL) {
    try {
      const res = await fetch(`${env.TRANC3_NANO_URL}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn(`Nanoservice ${endpoint} failed: ${e.message}`);
    }
  }

  // No backend available — return honest stub
  return null;
}

// ── Stub responses (no external AI — honest, useful) ─────────────────────────

function stubChat(messages, model) {
  const lastMsg = messages[messages.length - 1]?.content || "";
  return {
    id: crypto.randomUUID(),
    object: "chat.completion",
    model: model || "tranc3-base",
    backend: "tranc3-stub",
    trained: false,
    message: "TRANC3 model weights not yet trained. Run: python train.py",
    choices: [{
      index: 0,
      message: {
        role: "assistant",
        content: (
          `TRANC3 (${model || "tranc3-base"}) is initialising. ` +
          "Model weights are not yet trained. " +
          "Run `python train.py` on your Tranc3 backend to produce weights. " +
          `Your message: "${lastMsg.slice(0, 80)}"`
        ),
      },
      finish_reason: "stop",
    }],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

function stubEmbedding(input) {
  const texts = Array.isArray(input) ? input : [input];
  // Deterministic pseudo-embedding derived from text hash
  return {
    object: "list",
    model: "tranc3-embeddings",
    backend: "tranc3-stub",
    trained: false,
    data: texts.map((text, i) => {
      const hash = simpleHash(text);
      const vec  = Array.from({ length: 256 }, (_, j) => ((hash >> (j % 32)) & 1) * 0.1 - 0.05);
      return { object: "embedding", index: i, embedding: vec };
    }),
    usage: { prompt_tokens: 0, total_tokens: 0 },
  };
}

function stubEmotion(text) {
  const t = text.toLowerCase();
  const scores = {
    joy:      [/happy|great|excellent|wonderful|love|yay|amazing/].some(r => r.test(t)) ? 0.6 : 0.05,
    sadness:  [/sad|unhappy|terrible|awful|cry|miss|depressed/].some(r => r.test(t)) ? 0.6 : 0.05,
    anger:    [/angry|furious|hate|rage|frustrated|annoyed/].some(r => r.test(t)) ? 0.6 : 0.05,
    fear:     [/scared|afraid|fear|worried|anxious|nervous/].some(r => r.test(t)) ? 0.6 : 0.05,
    surprise: [/wow|amazing|unexpected|shocked|unbelievable/].some(r => r.test(t)) ? 0.6 : 0.05,
    disgust:  [/disgusting|horrible|gross|nasty|repulsive/].some(r => r.test(t)) ? 0.6 : 0.05,
  };
  const total = Object.values(scores).reduce((a, b) => a + b, 0) || 1;
  const norm  = Object.fromEntries(Object.entries(scores).map(([k, v]) => [k, +(v / total).toFixed(4)]));
  const dominant = Object.entries(norm).sort((a, b) => b[1] - a[1])[0][0];
  return { dominant, scores: norm, model: "tranc3-rule-based", backend: "tranc3-stub" };
}

function simpleHash(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = (h * 0x01000193) >>> 0;
  }
  return h;
}

// ── Route handlers ────────────────────────────────────────────────────────────

function handleModels(request, env) {
  const hasBackend = !!(env.TRANC3_BACKEND_URL || env.TRANC3_NANO_URL);
  return json({
    object: "list",
    backend_connected: hasBackend,
    data: Object.entries(TRANC3_MODELS).map(([id, info]) => ({
      id,
      object: "model",
      name: info.name,
      available: true,
      backend: hasBackend ? info.backend : "tranc3-stub",
      trained: hasBackend,
      capabilities: info.capabilities,
    })),
  }, 200, {}, request, env);
}

async function handleChat(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const { messages, model, stream, personality } = body;
  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return err("messages array is required", 400, request, env);
  }
  if (stream) {
    return err("Streaming not supported at edge; use the Tranc3 backend directly", 400, request, env);
  }

  // Build nanoservice payload
  const lastUser = messages.filter(m => m.role === "user").pop()?.content || "";
  const systemMsg = messages.find(m => m.role === "system")?.content;

  const nano = await callNano(env, "generate", {
    prompt:        lastUser,
    personality:   personality || model || "tranc3-base",
    system_prompt: systemMsg,
    max_tokens:    body.max_tokens || 256,
    temperature:   body.temperature || 0.8,
    top_p:         body.top_p || 0.9,
  });

  if (nano && nano.response) {
    return json({
      id:      crypto.randomUUID(),
      object:  "chat.completion",
      model:   model || "tranc3-base",
      backend: "tranc3-own",
      choices: [{
        index:  0,
        message: { role: "assistant", content: nano.response },
        finish_reason: "stop",
      }],
      usage: {
        prompt_tokens:     0,
        completion_tokens: nano.tokens || 0,
        total_tokens:      nano.tokens || 0,
      },
      personality: nano.personality,
    }, 200, {}, request, env);
  }

  // No backend available — return honest stub
  return json(stubChat(messages, model), 200, {}, request, env);
}

async function handleEmbeddings(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const { input } = body;
  if (!input) return err("input is required", 400, request, env);

  const texts = Array.isArray(input) ? input : [input];
  const nano  = await callNano(env, "embed", { text: texts[0], pooling: body.pooling || "mean" });

  if (nano && nano.embedding) {
    return json({
      object:  "list",
      model:   "tranc3-embeddings",
      backend: "tranc3-own",
      data: texts.map((_, i) => ({
        object: "embedding",
        index:  i,
        embedding: nano.embedding,
      })),
      usage: { prompt_tokens: 0, total_tokens: 0 },
    }, 200, {}, request, env);
  }

  return json(stubEmbedding(input), 200, {}, request, env);
}

async function handleEmotion(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const text = body.text || body.input || "";
  if (!text) return err("text is required", 400, request, env);

  const nano = await callNano(env, "emotion", { text });
  if (nano && nano.dominant) return json(nano, 200, {}, request, env);

  return json(stubEmotion(text), 200, {}, request, env);
}

async function handleConsciousness(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const text = body.text || body.input || "";
  if (!text) return err("text or input is required", 400, request, env);

  const nano = await callNano(env, "consciousness", { text });
  if (nano && typeof nano.phi === "number") return json(nano, 200, {}, request, env);

  // Heuristic phi estimate
  const words = text.split(/\s+/).filter(Boolean);
  const vocab  = new Set(words).size;
  const phi    = Math.min(1.0, (vocab / Math.max(words.length, 1)) * 2.0);
  return json({
    phi:      +phi.toFixed(4),
    awareness: phi > 0.7 ? "high" : phi > 0.4 ? "medium" : "low",
    model:    "tranc3-heuristic",
    backend:  "tranc3-stub",
  }, 200, {}, request, env);
}

async function handleTokenize(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const nano = await callNano(env, "tokenize", {
    action:       body.action || "encode",
    text:         body.text || "",
    ids:          body.ids || [],
    skip_special: body.skip_special ?? true,
  });
  if (nano) return json(nano, 200, {}, request, env);

  // Whitespace fallback
  if ((body.action || "encode") === "encode") {
    const tokens = (body.text || "").split(/\s+/).filter(Boolean);
    return json({ tokens, ids: tokens.map((_, i) => i), model: "fallback" }, 200, {}, request, env);
  }
  return json({ text: `[${(body.ids || []).length} tokens decoded]`, model: "fallback" }, 200, {}, request, env);
}

async function handlePredict(request, env) {
  let body;
  try { body = await request.json(); } catch {
    return err("Invalid JSON body", 400, request, env);
  }

  const text = body.text || "";
  if (!text) return err("text is required", 400, request, env);

  const nano = await callNano(env, "predict", {
    text,
    top_k:        body.top_k || 5,
    predict_type: body.predict_type || "next_token",
  });
  if (nano) return json(nano, 200, {}, request, env);

  return json({
    prediction: "the",
    confidence: 0.1,
    top_k:  [{ token: "the", prob: 0.1 }],
    model:  "tranc3-stub",
    backend: "tranc3-stub",
  }, 200, {}, request, env);
}

// ── Health ────────────────────────────────────────────────────────────────────

async function handleHealth(env) {
  const hasBackend = !!env.TRANC3_BACKEND_URL;
  const hasNano    = !!env.TRANC3_NANO_URL;

  let backendOk = false;
  if (hasBackend) {
    try {
      const r = await fetch(`${env.TRANC3_BACKEND_URL}/health`, { method: "GET" });
      backendOk = r.ok;
    } catch {}
  }

  let nanoOk = false;
  if (hasNano) {
    try {
      const r = await fetch(`${env.TRANC3_NANO_URL}/health`, { method: "GET" });
      nanoOk = r.ok;
    } catch {}
  }

  const mode = backendOk ? "tranc3-backend" : nanoOk ? "tranc3-nano" : "stub";

  return new Response(JSON.stringify({
    status:          "ok",
    service:         "tranc3-ai",
    version:         "2.0.0",
    backend:         mode,
    backend_url:     hasBackend ? env.TRANC3_BACKEND_URL : null,
    nano_url:        hasNano    ? env.TRANC3_NANO_URL    : null,
    backend_healthy: backendOk,
    nano_healthy:    nanoOk,
    note:            mode === "stub"
      ? "No backend connected. Set TRANC3_BACKEND_URL to enable full inference."
      : "Self-owned inference active.",
    timestamp: Date.now(),
  }), {
    status:  200,
    headers: { "Content-Type": "application/json", ...SECURITY_HEADERS },
  });
}

// ── Main fetch handler ────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const url    = new URL(request.url);
    const path   = url.pathname;
    const method = request.method;

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    // Public routes (no auth)
    if (path === "/health" || path === "/api/v1/ai/health") {
      return handleHealth(env);
    }

    if (path === "/" && method === "GET") {
      return json({
        name:    "Tranc3 AI Edge",
        version: "2.0.0",
        backend: env.TRANC3_BACKEND_URL ? "self-hosted" : "stub",
        note:    "Self-owned inference — no external AI services.",
        routes: {
          models:      "GET  /api/v1/ai/models",
          chat:        "POST /api/v1/ai/chat",
          embeddings:  "POST /api/v1/ai/embeddings",
          emotion:     "POST /api/v1/ai/analyze-emotion",
          consciousness:"POST /api/v1/ai/consciousness",
          tokenize:    "POST /api/v1/ai/tokenize",
          predict:     "POST /api/v1/ai/predict",
        },
      }, 200, {}, request, env);
    }

    // Models list — no auth required
    if (path === "/api/v1/ai/models" && method === "GET") {
      return handleModels(request, env);
    }

    // Auth-protected routes
    const user = await verifyAuth(request, env);
    if (!user) {
      return err("Unauthorized", 401, request, env, "Valid Bearer token required");
    }

    // Route dispatch
    if (path === "/api/v1/ai/chat"            && method === "POST") return handleChat(request, env);
    if (path === "/api/v1/ai/embeddings"      && method === "POST") return handleEmbeddings(request, env);
    if (path === "/api/v1/ai/analyze-emotion" && method === "POST") return handleEmotion(request, env);
    if (path === "/api/v1/ai/consciousness"   && method === "POST") return handleConsciousness(request, env);
    if (path === "/api/v1/ai/tokenize"        && method === "POST") return handleTokenize(request, env);
    if (path === "/api/v1/ai/predict"         && method === "POST") return handlePredict(request, env);

    return err("Not Found", 404, request, env, `${method} ${path}`);
  },
};
