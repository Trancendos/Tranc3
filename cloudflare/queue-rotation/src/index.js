/**
 * Tranc3 Queue Worker — Cloudflare Edge
 * Adaptive Zero-Cost Task Queue
 *
 * Provider rotation (all genuinely free, zero cost):
 *   1. Cloudflare Queues — 1M messages/month free forever (primary)
 *   2. Upstash Redis     — 10,000 commands/day free forever (secondary)
 *   3. KV queue         — uses existing KV namespace as list (tertiary/fallback)
 *
 * Task types supported:
 *   - email      → enqueues to tranc3-notifications
 *   - ai         → enqueues to tranc3-ai
 *   - webhook    → HTTP POST to a callback URL
 *   - generic    → any JSON payload for custom consumers
 *
 * Routes:
 *   POST /enqueue            — add a task to the queue
 *   POST /enqueue-bulk       — add multiple tasks
 *   GET  /status             — queue depth + provider usage
 *   GET  /health             — health check
 *
 * The Cloudflare Queues consumer (queue handler below) processes tasks
 * automatically when messages arrive. Upstash and KV queues are polled
 * via a scheduled cron trigger.
 */

// ── Usage tracking ─────────────────────────────────────────────────────────

function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

async function getUsage(env, provider) {
  try {
    const val = await env.CACHE.get(`queue-usage:${provider}:${todayKey()}`);
    return parseInt(val || "0", 10);
  } catch { return 0; }
}

async function incUsage(env, provider, count = 1) {
  try {
    const key = `queue-usage:${provider}:${todayKey()}`;
    const current = await getUsage(env, provider);
    await env.CACHE.put(key, String(current + count), { expirationTtl: 93600 });
  } catch {}
}

// ── Upstash Redis helpers ───────────────────────────────────────────────────

async function upstashPush(env, listName, message) {
  if (!env.UPSTASH_REDIS_URL || !env.UPSTASH_REDIS_TOKEN) throw new Error("Upstash not configured");
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/rpush/${listName}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify([JSON.stringify(message)]),
  });
  if (!res.ok) throw new Error(`Upstash push HTTP ${res.status}`);
  return await res.json();
}

async function upstashPop(env, listName) {
  if (!env.UPSTASH_REDIS_URL || !env.UPSTASH_REDIS_TOKEN) return null;
  const res = await fetch(`${env.UPSTASH_REDIS_URL}/lpop/${listName}`, {
    headers: { Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (!data.result) return null;
  try { return JSON.parse(data.result); } catch { return null; }
}

async function upstashLen(env, listName) {
  if (!env.UPSTASH_REDIS_URL || !env.UPSTASH_REDIS_TOKEN) return 0;
  try {
    const res = await fetch(`${env.UPSTASH_REDIS_URL}/llen/${listName}`, {
      headers: { Authorization: `Bearer ${env.UPSTASH_REDIS_TOKEN}` },
    });
    const data = await res.json();
    return data.result || 0;
  } catch { return 0; }
}

// ── KV queue helpers ────────────────────────────────────────────────────────

async function kvQueuePush(env, message) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  await env.CACHE.put(`kv-queue:${id}`, JSON.stringify(message), { expirationTtl: 86400 });
  // Maintain list of pending IDs
  const list = JSON.parse((await env.CACHE.get("kv-queue:list")) || "[]");
  list.push(id);
  await env.CACHE.put("kv-queue:list", JSON.stringify(list.slice(-1000)));
}

async function kvQueueLen(env) {
  const list = JSON.parse((await env.CACHE.get("kv-queue:list")) || "[]");
  return list.length;
}

// ── Task dispatch (for consumed messages) ─────────────────────────────────

async function dispatchTask(env, task) {
  const { type, payload } = task;

  if (type === "email") {
    // Forward to tranc3-notifications worker
    const notifUrl = env.NOTIFICATIONS_URL || "https://tranc3-notifications.luminous-aimastermind.workers.dev/send";
    const res = await fetch(notifUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return { type, success: res.ok, status: res.status };
  }

  if (type === "ai") {
    // Forward to tranc3-ai worker
    const aiUrl = env.AI_URL || "https://tranc3-ai.luminous-aimastermind.workers.dev/api/v1/ai/chat";
    const res = await fetch(aiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return { type, success: res.ok, status: res.status };
  }

  if (type === "webhook" && payload.url) {
    // HTTP POST to callback URL
    const res = await fetch(payload.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(payload.headers || {}) },
      body: JSON.stringify(payload.body || {}),
    });
    return { type, success: res.ok, status: res.status, url: payload.url };
  }

  // generic — log to KV audit trail
  await env.CACHE.put(
    `task-audit:${Date.now()}`,
    JSON.stringify({ type, payload, processed: new Date().toISOString() }),
    { expirationTtl: 604800 } // 7 days
  );
  return { type, success: true, note: "generic task logged" };
}

// ── CORS ───────────────────────────────────────────────────────────────────

function corsHeaders(origin) {
  const allowed = ["https://trancendos.com", "https://www.trancendos.com", "http://localhost:5173"];
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

function json(body, status = 200, cors = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors },
  });
}

// ── Main handler ───────────────────────────────────────────────────────────

export default {
  // ── HTTP fetch handler ───────────────────────────────────────────────────
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    // ── GET /health ────────────────────────────────────────────────────────
    if (url.pathname === "/health" && request.method === "GET") {
      return json({
        status: "ok",
        service: "tranc3-queue",
        timestamp: new Date().toISOString(),
        providers: {
          "cf-queues": { configured: !!env.TASK_QUEUE, free: "1M msg/month forever" },
          "upstash-redis": { configured: !!env.UPSTASH_REDIS_URL, free: "10K commands/day forever" },
          "kv-fallback": { configured: true, free: "always available" },
        },
      }, 200, cors);
    }

    // ── GET /status ────────────────────────────────────────────────────────
    if (url.pathname === "/status" && request.method === "GET") {
      const [cfUsage, upstashUsage, kvDepth, upstashDepth] = await Promise.all([
        getUsage(env, "cf-queues"),
        getUsage(env, "upstash"),
        kvQueueLen(env),
        upstashLen(env, "tranc3-tasks"),
      ]);

      return json({
        status: "ok",
        providers: {
          "cf-queues": {
            configured: !!env.TASK_QUEUE,
            todayUsage: cfUsage,
            dailyLimit: 33000, // ~1M/month ÷ 30
            free: "1M messages/month forever",
          },
          "upstash-redis": {
            configured: !!env.UPSTASH_REDIS_URL,
            todayUsage: upstashUsage,
            dailyLimit: 9500,
            queueDepth: upstashDepth,
            free: "10K commands/day forever",
          },
          "kv-fallback": {
            configured: true,
            queueDepth: kvDepth,
            free: "unlimited (uses CACHE KV)",
          },
        },
        timestamp: new Date().toISOString(),
      }, 200, cors);
    }

    // ── POST /enqueue ──────────────────────────────────────────────────────
    if (url.pathname === "/enqueue" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON" }, 400, cors); }

      if (!body.type) return json({ error: "'type' is required" }, 400, cors);
      if (!body.payload) return json({ error: "'payload' is required" }, 400, cors);

      const message = { type: body.type, payload: body.payload, enqueued: new Date().toISOString() };

      // Try CF Queues first (1M/month free)
      if (env.TASK_QUEUE) {
        try {
          await env.TASK_QUEUE.send(message);
          await incUsage(env, "cf-queues");
          return json({ success: true, provider: "cf-queues", type: body.type }, 202, cors);
        } catch { /* fall through */ }
      }

      // Try Upstash (10K commands/day free)
      const upstashUsage = await getUsage(env, "upstash");
      if (upstashUsage < 9500 && env.UPSTASH_REDIS_URL) {
        try {
          await upstashPush(env, "tranc3-tasks", message);
          await incUsage(env, "upstash");
          return json({ success: true, provider: "upstash-redis", type: body.type }, 202, cors);
        } catch { /* fall through */ }
      }

      // KV fallback (always available)
      await kvQueuePush(env, message);
      return json({ success: true, provider: "kv-fallback", type: body.type }, 202, cors);
    }

    // ── POST /enqueue-bulk ─────────────────────────────────────────────────
    if (url.pathname === "/enqueue-bulk" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON" }, 400, cors); }

      if (!Array.isArray(body.tasks)) return json({ error: "'tasks' array is required" }, 400, cors);

      const results = [];
      for (const task of body.tasks) {
        if (!task.type || !task.payload) {
          results.push({ success: false, error: "type and payload required" });
          continue;
        }
        const message = { type: task.type, payload: task.payload, enqueued: new Date().toISOString() };

        if (env.TASK_QUEUE) {
          try {
            await env.TASK_QUEUE.send(message);
            await incUsage(env, "cf-queues");
            results.push({ success: true, provider: "cf-queues", type: task.type });
            continue;
          } catch {}
        }

        await kvQueuePush(env, message);
        results.push({ success: true, provider: "kv-fallback", type: task.type });
      }

      const sent = results.filter((r) => r.success).length;
      return json({ queued: sent, failed: results.length - sent, results }, 202, cors);
    }

    return json({ error: "Not found" }, 404, cors);
  },

  // ── Cloudflare Queues consumer ───────────────────────────────────────────
  async queue(batch, env) {
    for (const msg of batch.messages) {
      try {
        const task = msg.body;
        await dispatchTask(env, task);
        msg.ack();
      } catch (err) {
        // Retry up to 3 times (CF Queues handles retry automatically)
        msg.retry();
      }
    }
  },
};
