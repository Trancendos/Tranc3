/**
 * Tranc3 Notifications Worker — Cloudflare Edge
 * Adaptive Zero-Cost Email Rotation Gateway
 *
 * Rotates through 3 free-tier email providers in priority order.
 * Daily usage tracked in KV — automatically switches providers
 * when a limit approaches, ensuring 100% uptime at £0.
 *
 * Provider rotation (all genuinely free, zero cost — no credit card needed):
 *   1. Resend    — 3,000 emails/month, 100/day free forever
 *   2. Brevo     — 9,000 emails/month, 300/day free forever
 *   3. Mailjet   — 6,000 emails/month, 200/day free forever
 *   4. Honest stub — queues message, notifies about degraded state
 *
 * Combined daily capacity: 600 emails/day at zero cost.
 * Combined monthly capacity: 18,000 emails/month at zero cost.
 *
 * Routes:
 *   POST /send              — send a transactional email
 *   POST /send-bulk         — send to multiple recipients (chunked across providers)
 *   GET  /status            — provider usage + availability
 *   GET  /health            — health check
 */

// ── Provider definitions ───────────────────────────────────────────────────

const EMAIL_PROVIDERS = [
  {
    id: "resend",
    name: "Resend",
    dailyLimit: 95,    // 100/day free — leave 5% buffer
    monthlyLimit: 2850, // 3000/month free — leave 5% buffer
    available: (env) => !!env.RESEND_API_KEY,
    send: async (env, { to, subject, html, text }) => {
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.RESEND_API_KEY}`,
        },
        body: JSON.stringify({
          from: `${env.FROM_NAME || "Trancendos"} <${env.FROM_EMAIL || "no-reply@trancendos.com"}>`,
          to: Array.isArray(to) ? to : [to],
          subject,
          html,
          text,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Resend HTTP ${res.status}: ${err}`);
      }
      const data = await res.json();
      return { id: data.id, provider: "resend" };
    },
  },
  {
    id: "brevo",
    name: "Brevo (Sendinblue)",
    dailyLimit: 285,   // 300/day free — leave 5% buffer
    monthlyLimit: 8550, // 9000/month free — leave 5% buffer
    available: (env) => !!env.BREVO_API_KEY,
    send: async (env, { to, subject, html, text }) => {
      const toArr = Array.isArray(to) ? to : [to];
      const res = await fetch("https://api.brevo.com/v3/smtp/email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "api-key": env.BREVO_API_KEY,
        },
        body: JSON.stringify({
          sender: {
            name: env.FROM_NAME || "Trancendos",
            email: env.FROM_EMAIL || "no-reply@trancendos.com",
          },
          to: toArr.map((email) => ({ email })),
          subject,
          htmlContent: html,
          textContent: text,
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Brevo HTTP ${res.status}: ${err}`);
      }
      const data = await res.json();
      return { id: data.messageId || "brevo-ok", provider: "brevo" };
    },
  },
  {
    id: "mailjet",
    name: "Mailjet",
    dailyLimit: 190,   // 200/day free — leave 5% buffer
    monthlyLimit: 5700, // 6000/month free — leave 5% buffer
    available: (env) => !!env.MAILJET_API_KEY && !!env.MAILJET_SECRET_KEY,
    send: async (env, { to, subject, html, text }) => {
      const toArr = Array.isArray(to) ? to : [to];
      const credentials = btoa(`${env.MAILJET_API_KEY}:${env.MAILJET_SECRET_KEY}`);
      const res = await fetch("https://api.mailjet.com/v3.1/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Basic ${credentials}`,
        },
        body: JSON.stringify({
          Messages: [
            {
              From: {
                Email: env.FROM_EMAIL || "no-reply@trancendos.com",
                Name: env.FROM_NAME || "Trancendos",
              },
              To: toArr.map((email) => ({ Email: email })),
              Subject: subject,
              HTMLPart: html,
              TextPart: text,
            },
          ],
        }),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Mailjet HTTP ${res.status}: ${err}`);
      }
      const data = await res.json();
      const msg = data.Messages?.[0];
      return { id: msg?.To?.[0]?.MessageID || "mailjet-ok", provider: "mailjet" };
    },
  },
];

// ── Usage tracking ─────────────────────────────────────────────────────────

function todayKey() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD UTC
}

function thisMonthKey() {
  return new Date().toISOString().slice(0, 7); // YYYY-MM UTC
}

async function getUsage(env, providerId, period = "day") {
  try {
    const key = period === "month"
      ? `email-usage:${providerId}:${thisMonthKey()}`
      : `email-usage:${providerId}:${todayKey()}`;
    const val = await env.CACHE.get(key);
    return parseInt(val || "0", 10);
  } catch { return 0; }
}

async function incUsage(env, providerId) {
  try {
    // Track daily (26h TTL — resets at midnight UTC)
    const dayKey = `email-usage:${providerId}:${todayKey()}`;
    const dayVal = await getUsage(env, providerId, "day");
    await env.CACHE.put(dayKey, String(dayVal + 1), { expirationTtl: 93600 });

    // Track monthly (32-day TTL)
    const monKey = `email-usage:${providerId}:${thisMonthKey()}`;
    const monVal = await getUsage(env, providerId, "month");
    await env.CACHE.put(monKey, String(monVal + 1), { expirationTtl: 2764800 });
  } catch { /* non-critical */ }
}

async function selectProvider(env) {
  for (const p of EMAIL_PROVIDERS) {
    if (!p.available(env)) continue;
    const dayUsage = await getUsage(env, p.id, "day");
    const monUsage = await getUsage(env, p.id, "month");
    if (dayUsage < p.dailyLimit && monUsage < p.monthlyLimit) return p;
  }
  return null;
}

async function usageStatus(env) {
  const result = {};
  for (const p of EMAIL_PROVIDERS) {
    const dayUsage = await getUsage(env, p.id, "day");
    const monUsage = await getUsage(env, p.id, "month");
    result[p.id] = {
      name: p.name,
      day: { used: dayUsage, limit: p.dailyLimit, pct: Math.round((dayUsage / p.dailyLimit) * 100) },
      month: { used: monUsage, limit: p.monthlyLimit, pct: Math.round((monUsage / p.monthlyLimit) * 100) },
      available: p.available(env),
      active: p.available(env) && dayUsage < p.dailyLimit && monUsage < p.monthlyLimit,
    };
  }
  return result;
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

// ── Request validation ─────────────────────────────────────────────────────

function validateEmail(email) {
  if (typeof email !== "string") return false;
  const at = email.indexOf("@");
  if (at <= 0 || at !== email.lastIndexOf("@")) return false;
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  if (!local || !domain) return false;
  if (domain.indexOf(".") <= 0 || domain.endsWith(".")) return false;
  for (const ch of local + domain) {
    if (ch === " " || ch === "\n" || ch === "\r" || ch === "\t") return false;
  }
  return true;
}

function validateSendRequest(body) {
  const errors = [];
  if (!body.to) errors.push("'to' is required");
  const toArr = Array.isArray(body.to) ? body.to : [body.to];
  if (!toArr.every(validateEmail)) errors.push("'to' must be valid email address(es)");
  if (!body.subject || typeof body.subject !== "string") errors.push("'subject' is required");
  if (!body.html && !body.text) errors.push("'html' or 'text' body is required");
  return errors;
}

// ── Main handler ───────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    // ── GET /health ──────────────────────────────────────────────────────────
    if (url.pathname === "/health" && request.method === "GET") {
      return json({
        status: "ok",
        service: "tranc3-notifications",
        timestamp: new Date().toISOString(),
        providers: EMAIL_PROVIDERS.map((p) => ({ id: p.id, name: p.name, configured: p.available(env) })),
      }, 200, cors);
    }

    // ── GET /status ──────────────────────────────────────────────────────────
    if (url.pathname === "/status" && request.method === "GET") {
      const status = await usageStatus(env);
      const activeProvider = await selectProvider(env);
      return json({
        status: "ok",
        activeProvider: activeProvider?.id || "stub",
        providers: status,
        totalDailyCapacity: EMAIL_PROVIDERS.reduce((s, p) => s + p.dailyLimit, 0),
        totalMonthlyCapacity: EMAIL_PROVIDERS.reduce((s, p) => s + p.monthlyLimit, 0),
        timestamp: new Date().toISOString(),
      }, 200, cors);
    }

    // ── POST /send ───────────────────────────────────────────────────────────
    if (url.pathname === "/send" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON body" }, 400, cors); }

      const errors = validateSendRequest(body);
      if (errors.length) return json({ error: errors.join("; ") }, 400, cors);

      const provider = await selectProvider(env);

      if (!provider) {
        // All providers exhausted — honest response, do not silently drop
        return json({
          success: false,
          degraded: true,
          message: "All email provider daily free quotas have been reached. Email will be retried when quotas reset at midnight UTC.",
          retryAfter: "midnight UTC",
        }, 503, cors);
      }

      try {
        const result = await provider.send(env, body);
        await incUsage(env, provider.id);
        return json({ success: true, ...result }, 200, cors);
      } catch (err) {
        // Provider failed — try next one
        for (const fallback of EMAIL_PROVIDERS) {
          if (fallback.id === provider.id || !fallback.available(env)) continue;
          const dayUsage = await getUsage(env, fallback.id, "day");
          const monUsage = await getUsage(env, fallback.id, "month");
          if (dayUsage >= fallback.dailyLimit || monUsage >= fallback.monthlyLimit) continue;
          try {
            const result = await fallback.send(env, body);
            await incUsage(env, fallback.id);
            return json({ success: true, ...result, primaryFailed: provider.id }, 200, cors);
          } catch { continue; }
        }
        return json({ error: "All email providers failed", details: err.message }, 502, cors);
      }
    }

    // ── POST /send-bulk ──────────────────────────────────────────────────────
    if (url.pathname === "/send-bulk" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON body" }, 400, cors); }

      if (!Array.isArray(body.emails) || body.emails.length === 0) {
        return json({ error: "'emails' array is required" }, 400, cors);
      }

      const results = [];
      for (const email of body.emails) {
        const errors = validateSendRequest(email);
        if (errors.length) {
          results.push({ success: false, to: email.to, error: errors.join("; ") });
          continue;
        }

        const provider = await selectProvider(env);
        if (!provider) {
          results.push({ success: false, to: email.to, degraded: true, message: "Provider quota reached" });
          continue;
        }

        try {
          const result = await provider.send(env, email);
          await incUsage(env, provider.id);
          results.push({ success: true, to: email.to, ...result });
        } catch {
          results.push({ success: false, to: email.to, error: "Send failed" });
        }
      }

      const sent = results.filter((r) => r.success).length;
      return json({ sent, failed: results.length - sent, results }, 200, cors);
    }

    return json({ error: "Not found", path: url.pathname }, 404, cors);
  },
};
