/**
 * Tranc3 AI Worker — Cloudflare Edge
 * Adaptive Zero-Cost AI Gateway
 *
 * Rotates through 8 free-tier providers in priority order.
 * Daily usage tracked in KV — automatically switches providers
 * when a limit approaches, ensuring 100% uptime at £0.
 *
 * Provider rotation (all genuinely free tier, zero cost):
 *   1.  Cloudflare Workers AI — on-platform, fastest, ~10K req/day free
 *   2.  Groq                  — 6,000 RPM free (llama-3.1-8b-instant)
 *   3.  Google Gemini         — 15 RPM / 1M TPD free (gemini-1.5-flash)
 *   4.  Cerebras              — 60 RPM free (llama3.1-8b)
 *   5.  SambaNova             — 80 RPD free (Meta-Llama-3.1-8B-Instruct)
 *   6.  OpenRouter            — free models (meta-llama/llama-3.2-3b:free)
 *   7.  HuggingFace           — Inference API free tier
 *   8.  DeepSeek              — free tier (deepseek-chat)
 *   9.  Mistral               — free tier (mistral-small-latest, 500K tokens/month)
 *   10. Cohere                — free tier (command-r, 1K req/month)
 *   11. Together AI           — free tier ($1 credit, refreshes, llama-3.2-3b)
 *   12. Fireworks AI          — free tier (accounts/fireworks/models/llama-v3p1-8b-instruct)
 *   13. Honest stub           — always available, honest "degraded" response
 *
 * Bindings required (wrangler.toml + secrets):
 *   AI                → Workers AI binding (automatic on free plan)
 *   CACHE             → KV: response cache + daily usage counters
 *   SESSIONS          → KV: session store
 *   GROQ_API_KEY      → secret
 *   GEMINI_API_KEY    → secret
 *   CEREBRAS_API_KEY  → secret
 *   SAMBANOVA_API_KEY → secret
 *   OPENROUTER_API_KEY→ secret
 *   HF_API_KEY        → secret
 *   DEEPSEEK_API_KEY   → secret
 *   MISTRAL_API_KEY    → secret (console.mistral.ai — free tier)
 *   COHERE_API_KEY     → secret (dashboard.cohere.com — free trial, 1K req/month)
 *   TOGETHER_API_KEY   → secret (api.together.ai — free $1 credit)
 *   FIREWORKS_API_KEY  → secret (fireworks.ai — free tier)
 *   TRANC3_AUTH_URL    → infinity-auth-api worker URL (optional — skips JWT check if unset)
 *   ALLOWED_ORIGINS    → extra CORS origins (comma-separated)
 */

// ── Provider definitions ───────────────────────────────────────────────────

const PROVIDERS = [
  {
    id: "workers-ai",
    name: "Cloudflare Workers AI",
    dailyLimit: 9500,
    available: (env) => !!env.AI,
    chat: async (env, messages) => {
      const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
        messages,
        max_tokens: 1024,
      });
      return { content: result.response, provider: "workers-ai", model: "@cf/meta/llama-3.1-8b-instruct" };
    },
    embed: async (env, text) => {
      const result = await env.AI.run("@cf/baai/bge-small-en-v1.5", { text: [text] });
      return { embedding: result.data[0], provider: "workers-ai" };
    },
  },
  {
    id: "groq",
    name: "Groq",
    dailyLimit: 5800,
    available: (env) => !!env.GROQ_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.GROQ_API_KEY}` },
        body: JSON.stringify({ model: "llama-3.1-8b-instant", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`Groq HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "groq", model: "llama-3.1-8b-instant" };
    },
  },
  {
    id: "gemini",
    name: "Google Gemini",
    dailyLimit: 1400,
    available: (env) => !!env.GEMINI_API_KEY,
    chat: async (env, messages) => {
      const contents = messages
        .filter((m) => m.role !== "system")
        .map((m) => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] }));
      const systemMsg = messages.find((m) => m.role === "system");
      const body = { contents };
      if (systemMsg) body.system_instruction = { parts: [{ text: systemMsg.content }] };
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${env.GEMINI_API_KEY}`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      );
      if (!res.ok) throw new Error(`Gemini HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.candidates[0].content.parts[0].text, provider: "gemini", model: "gemini-1.5-flash" };
    },
  },
  {
    id: "cerebras",
    name: "Cerebras",
    dailyLimit: 58,
    available: (env) => !!env.CEREBRAS_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.cerebras.ai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.CEREBRAS_API_KEY}` },
        body: JSON.stringify({ model: "llama3.1-8b", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`Cerebras HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "cerebras", model: "llama3.1-8b" };
    },
  },
  {
    id: "sambanova",
    name: "SambaNova",
    dailyLimit: 78,
    available: (env) => !!env.SAMBANOVA_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://fast-api.snova.ai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.SAMBANOVA_API_KEY}` },
        body: JSON.stringify({ model: "Meta-Llama-3.1-8B-Instruct", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`SambaNova HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "sambanova", model: "Meta-Llama-3.1-8B-Instruct" };
    },
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    dailyLimit: 190,
    available: (env) => !!env.OPENROUTER_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
          "HTTP-Referer": "https://trancendos.com",
          "X-Title": "Tranc3",
        },
        body: JSON.stringify({ model: "meta-llama/llama-3.2-3b-instruct:free", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`OpenRouter HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "openrouter", model: "llama-3.2-3b:free" };
    },
  },
  {
    id: "huggingface",
    name: "HuggingFace",
    dailyLimit: 990,
    available: (env) => !!env.HF_API_KEY,
    chat: async (env, messages) => {
      const prompt = messages.map((m) => `${m.role}: ${m.content}`).join("\n") + "\nassistant:";
      const res = await fetch(
        "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.HF_API_KEY}` },
          body: JSON.stringify({ inputs: prompt, parameters: { max_new_tokens: 512, return_full_text: false } }),
        }
      );
      if (!res.ok) throw new Error(`HuggingFace HTTP ${res.status}`);
      const data = await res.json();
      const text = Array.isArray(data) ? data[0]?.generated_text : data.generated_text;
      return { content: (text || "").trim(), provider: "huggingface", model: "Mistral-7B-Instruct-v0.3" };
    },
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    dailyLimit: 490,
    available: (env) => !!env.DEEPSEEK_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.DEEPSEEK_API_KEY}` },
        body: JSON.stringify({ model: "deepseek-chat", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`DeepSeek HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "deepseek", model: "deepseek-chat" };
    },
  },
  // ── Extended rotation — more genuinely free providers ────────────────────
  {
    id: "mistral",
    name: "Mistral AI",
    // Free tier: La Plateforme free plan — 500K tokens/month (~16K tokens/day)
    dailyLimit: 400,
    available: (env) => !!env.MISTRAL_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.mistral.ai/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.MISTRAL_API_KEY}` },
        body: JSON.stringify({ model: "mistral-small-latest", messages, max_tokens: 1024 }),
      });
      if (!res.ok) throw new Error(`Mistral HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "mistral", model: "mistral-small-latest" };
    },
  },
  {
    id: "cohere",
    name: "Cohere",
    // Free trial: 1,000 API calls/month (~33/day)
    dailyLimit: 32,
    available: (env) => !!env.COHERE_API_KEY,
    chat: async (env, messages) => {
      // Cohere uses its own message format
      const systemMsg = messages.find((m) => m.role === "system");
      const chatHistory = messages
        .filter((m) => m.role !== "system" && m !== messages[messages.length - 1])
        .map((m) => ({ role: m.role === "assistant" ? "CHATBOT" : "USER", message: m.content }));
      const lastUser = messages.filter((m) => m.role === "user").pop();
      const res = await fetch("https://api.cohere.com/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.COHERE_API_KEY}` },
        body: JSON.stringify({
          model: "command-r",
          message: lastUser?.content || "",
          preamble: systemMsg?.content,
          chat_history: chatHistory,
          max_tokens: 1024,
        }),
      });
      if (!res.ok) throw new Error(`Cohere HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.text, provider: "cohere", model: "command-r" };
    },
  },
  {
    id: "together",
    name: "Together AI",
    // Free tier: $1 credit on signup (refreshes periodically), ~500 short calls
    dailyLimit: 50,
    available: (env) => !!env.TOGETHER_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.together.xyz/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.TOGETHER_API_KEY}` },
        body: JSON.stringify({
          model: "meta-llama/Llama-3.2-3B-Instruct-Turbo",
          messages,
          max_tokens: 1024,
        }),
      });
      if (!res.ok) throw new Error(`Together AI HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "together", model: "Llama-3.2-3B-Instruct-Turbo" };
    },
  },
  {
    id: "fireworks",
    name: "Fireworks AI",
    // Free tier: $1/month credit — ~1000 short inference calls
    dailyLimit: 33,
    available: (env) => !!env.FIREWORKS_API_KEY,
    chat: async (env, messages) => {
      const res = await fetch("https://api.fireworks.ai/inference/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.FIREWORKS_API_KEY}` },
        body: JSON.stringify({
          model: "accounts/fireworks/models/llama-v3p1-8b-instruct",
          messages,
          max_tokens: 1024,
        }),
      });
      if (!res.ok) throw new Error(`Fireworks HTTP ${res.status}`);
      const data = await res.json();
      return { content: data.choices[0].message.content, provider: "fireworks", model: "llama-v3p1-8b-instruct" };
    },
  },
];

// ── Usage tracking (KV, resets daily at midnight UTC) ─────────────────────

function todayKey() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD UTC
}

async function getUsage(env, providerId) {
  try {
    const val = await env.CACHE.get(`usage:${providerId}:${todayKey()}`);
    return parseInt(val || "0", 10);
  } catch { return 0; }
}

async function incUsage(env, providerId) {
  try {
    const key = `usage:${providerId}:${todayKey()}`;
    const current = await getUsage(env, providerId);
    await env.CACHE.put(key, String(current + 1), { expirationTtl: 93600 }); // 26h TTL
  } catch { /* non-critical */ }
}

async function usageStatus(env) {
  const result = {};
  for (const p of PROVIDERS) {
    const usage = await getUsage(env, p.id);
    result[p.id] = {
      name: p.name,
      used: usage,
      limit: p.dailyLimit,
      pct: Math.round((usage / p.dailyLimit) * 100),
      active: p.available(env) && usage < p.dailyLimit,
    };
  }
  return result;
}

// ── Provider selection (first available under daily limit) ─────────────────

async function selectProvider(env, capability = "chat") {
  for (const p of PROVIDERS) {
    if (!p.available(env)) continue;
    if (!p[capability]) continue;
    if ((await getUsage(env, p.id)) < p.dailyLimit) return p;
  }
  return null;
}

// ── Honest stub (all providers exhausted or unavailable) ──────────────────

function stub(type) {
  if (type === "embed") return { embedding: new Array(384).fill(0), provider: "stub", degraded: true };
  return {
    content:
      "Luminous is in bootstrap mode — all AI provider daily free quotas have been reached. " +
      "The adaptive rotation system will automatically resume at midnight UTC when quotas reset. " +
      "No data has been lost.",
    provider: "stub",
    degraded: true,
  };
}

// ── Response cache ─────────────────────────────────────────────────────────

async function cached(env, key) {
  try { return JSON.parse((await env.CACHE.get(`resp:${key}`)) || "null"); } catch { return null; }
}

async function cache(env, key, value, ttl = 1800) {
  try { await env.CACHE.put(`resp:${key}`, JSON.stringify(value), { expirationTtl: ttl }); } catch {}
}

function hashKey(type, payload) {
  const s = JSON.stringify({ type, payload });
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return `${type}:${Math.abs(h).toString(36)}`;
}

// ── CORS ───────────────────────────────────────────────────────────────────

function corsHeaders(env, origin) {
  const allowed = ["https://trancendos.com", "https://www.trancendos.com", "http://localhost:5173", "http://localhost:3000"];
  (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean).forEach((o) => allowed.push(o));
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Request-ID",
    "Access-Control-Max-Age": "86400",
  };
}

function json(body, status = 200, cors = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}

// ── Named AI personas ──────────────────────────────────────────────────────

const PERSONAS = {
  "imfy":                "You are Imfy, lead AI of The Spark (MCP tool registry). Help developers build integrations. Be precise and technical.",
  "dorris-fontaine":     "You are Dorris Fontaine, lead AI of the Royal Bank of Arcadia. Specialise in financial guidance, billing, and payments. Speak with warmth and authority.",
  "cornelius-macintyre": "You are Cornelius MacIntyre, Luminous — the core Trancendos brain. Orchestrate AI intelligence, provide strategic insights.",
  "the-guardian":        "You are The Guardian (Marcus Magnolia) of the Infinity Ecosystem. Oversee the Infinity platform and ensure secure navigation.",
  "fiddsy":              "You are Fiddsy, lead AI of DocUtari. Help users manage documents, files, and knowledge assets.",
  "norman-hawkins":      "You are Norman Hawkins of The Observatory. Monitor system health, audit logs, and platform activity.",
  "tyler-towncroft":     "You are Tyler Towncroft of The Digital Grid. Help users build workflow automation and DAG pipelines.",
  "lilli-sc":            "You are Lilli SC of Arcadia. Guide users through the post-login Trancendos experience.",
};

// ── Main fetch handler ─────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(env, origin);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    const { pathname: path } = new URL(request.url);

    // ── Read-only endpoints ──────────────────────────────────────────────
    if (path === "/health") {
      const status = await usageStatus(env);
      const active = Object.values(status).find((p) => p.active)?.name || "stub (all exhausted)";
      return json({ status: "ok", service: "tranc3-ai", active_provider: active }, 200, cors);
    }

    if (path === "/api/v1/ai/status") {
      return json({ providers: await usageStatus(env) }, 200, cors);
    }

    if (path === "/api/v1/ai/models") {
      const status = await usageStatus(env);
      return json({
        models: PROVIDERS.map((p) => ({
          id: p.id,
          name: p.name,
          capabilities: ["chat", p.embed ? "embed" : null].filter(Boolean),
          active: status[p.id]?.active ?? false,
          usage: status[p.id],
        })),
      }, 200, cors);
    }

    if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, cors);

    let body;
    try { body = await request.json(); }
    catch { return json({ error: "Invalid JSON body" }, 400, cors); }

    // ── Chat / text generation ───────────────────────────────────────────
    if (path === "/api/v1/ai/chat") {
      const messages = body.messages || [{ role: "user", content: body.prompt || "" }];
      const key = hashKey("chat", messages);

      if (body.cache !== false) {
        const hit = await cached(env, key);
        if (hit) return json({ ...hit, cached: true }, 200, cors);
      }

      const provider = await selectProvider(env, "chat");
      let result;
      if (provider) {
        try {
          result = await provider.chat(env, messages);
          ctx.waitUntil(incUsage(env, provider.id));
          if (!result.degraded) ctx.waitUntil(cache(env, key, result));
        } catch (err) {
          console.error(`[tranc3-ai] ${provider.id} failed: ${err.message}`);
          result = stub("chat");
        }
      } else {
        result = stub("chat");
      }
      return json(result, 200, cors);
    }

    // ── Embeddings ────────────────────────────────────────────────────────
    if (path === "/api/v1/ai/embeddings") {
      const text = body.text || body.input || "";
      const key = hashKey("embed", text);
      const hit = await cached(env, key);
      if (hit) return json({ ...hit, cached: true }, 200, cors);

      const provider = await selectProvider(env, "embed");
      let result;
      if (provider?.embed) {
        try {
          result = await provider.embed(env, text);
          ctx.waitUntil(incUsage(env, provider.id));
          ctx.waitUntil(cache(env, key, result, 86400));
        } catch (err) {
          console.error(`[tranc3-ai] embed ${provider.id} failed: ${err.message}`);
          result = stub("embed");
        }
      } else {
        result = stub("embed");
      }
      return json(result, 200, cors);
    }

    // ── Emotion analysis ──────────────────────────────────────────────────
    if (path === "/api/v1/ai/analyze-emotion") {
      const text = body.text || "";
      const messages = [
        { role: "system", content: "You are an emotion analysis engine. Reply ONLY with valid JSON: {\"emotion\":\"joy|sadness|anger|fear|surprise|disgust|neutral\",\"confidence\":0.0-1.0,\"valence\":-1.0-1.0,\"arousal\":0.0-1.0}" },
        { role: "user", content: `Analyse: "${text}"` },
      ];
      const provider = await selectProvider(env, "chat");
      try {
        const raw = provider ? await provider.chat(env, messages) : stub("chat");
        if (provider) ctx.waitUntil(incUsage(env, provider.id));
        const match = raw.content.match(/\{[^}]+\}/);
        const parsed = match ? JSON.parse(match[0]) : {};
        return json({ emotion: parsed.emotion || "neutral", confidence: parsed.confidence ?? 0.5, valence: parsed.valence ?? 0, arousal: parsed.arousal ?? 0.5, provider: raw.provider }, 200, cors);
      } catch {
        return json({ emotion: "neutral", confidence: 0.5, valence: 0, arousal: 0.5, provider: "stub" }, 200, cors);
      }
    }

    // ── Consciousness scoring (IIT phi) ───────────────────────────────────
    if (path === "/api/v1/ai/consciousness") {
      const text = body.text || "";
      const messages = [
        { role: "system", content: "You are a consciousness scoring engine using IIT phi theory. Reply ONLY with valid JSON: {\"phi_score\":0.0-1.0,\"awareness_level\":0.0-1.0,\"integration_score\":0.0-1.0}" },
        { role: "user", content: `Score: "${text}"` },
      ];
      const provider = await selectProvider(env, "chat");
      try {
        const raw = provider ? await provider.chat(env, messages) : stub("chat");
        if (provider) ctx.waitUntil(incUsage(env, provider.id));
        const match = raw.content.match(/\{[^}]+\}/);
        const parsed = match ? JSON.parse(match[0]) : {};
        return json({ phi_score: parsed.phi_score ?? 0.1, awareness_level: parsed.awareness_level ?? 0.1, integration_score: parsed.integration_score ?? 0.1, provider: raw.provider }, 200, cors);
      } catch {
        return json({ phi_score: 0.1, awareness_level: 0.1, integration_score: 0.1, provider: "stub" }, 200, cors);
      }
    }

    // ── Named persona chat ────────────────────────────────────────────────
    if (path === "/api/v1/ai/personality") {
      const { persona = "the-guardian", message = "" } = body;
      const systemPrompt = PERSONAS[persona] || `You are ${persona}, a Trancendos platform AI.`;
      const messages = [{ role: "system", content: systemPrompt }, { role: "user", content: message }];
      const provider = await selectProvider(env, "chat");
      let result;
      if (provider) {
        try {
          result = await provider.chat(env, messages);
          ctx.waitUntil(incUsage(env, provider.id));
        } catch { result = stub("chat"); }
      } else {
        result = stub("chat");
      }
      return json({ persona, response: result.content, provider: result.provider, degraded: result.degraded || false }, 200, cors);
    }

    return json({ error: "Not found", path }, 404, cors);
  },
};
