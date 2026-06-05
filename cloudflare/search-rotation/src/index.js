/**
 * Tranc3 Search Worker — Cloudflare Edge
 * Adaptive Zero-Cost Search Rotation Gateway
 *
 * Rotates through free-tier search providers:
 *
 *   1. Cloudflare KV full-text (built-in, zero extra cost — uses existing CACHE KV)
 *   2. Typesense Cloud free tier — 1M records, unlimited searches, 3 nodes
 *   3. Meilisearch Cloud free tier — 100K documents, 10K req/month
 *   4. Algolia free tier — 10K req/month, 10K records
 *
 * Honest notes:
 *   - KV full-text is basic prefix matching only — not full semantic search
 *   - Typesense is the best free option for real search (unlimited searches)
 *   - Meilisearch and Algolia have monthly caps — used as overflow/fallback
 *   - All four are genuinely free (no expiry on free tiers)
 *
 * Routes:
 *   POST /index          — add document(s) to search index
 *   POST /search         — search across indexed documents
 *   DELETE /index/:id    — remove document from index
 *   GET  /status         — provider usage + availability
 *   GET  /health         — health check
 */

// ── Provider definitions ───────────────────────────────────────────────────

const SEARCH_PROVIDERS = [
  {
    id: "typesense",
    name: "Typesense Cloud",
    // Free: unlimited searches, 1M records, 3 nodes — genuinely free forever
    searchLimit: Infinity,
    indexLimit: 990000,
    available: (env) => !!env.TYPESENSE_API_KEY && !!env.TYPESENSE_HOST,

    search: async (env, { query, collection = "trancendos", limit = 10, filters }) => {
      const params = new URLSearchParams({
        q: query,
        query_by: "title,content,tags",
        per_page: String(limit),
      });
      if (filters) params.set("filter_by", filters);

      const res = await fetch(
        `https://${env.TYPESENSE_HOST}/collections/${collection}/documents/search?${params}`,
        { headers: { "X-TYPESENSE-API-KEY": env.TYPESENSE_API_KEY } }
      );
      if (!res.ok) throw new Error(`Typesense HTTP ${res.status}`);
      const data = await res.json();
      return {
        hits: data.hits.map((h) => ({ id: h.document.id, score: h.text_match, ...h.document })),
        total: data.found,
        provider: "typesense",
      };
    },

    index: async (env, documents, collection = "trancendos") => {
      // Batch upsert
      const ndjson = documents.map((d) => JSON.stringify(d)).join("\n");
      const res = await fetch(
        `https://${env.TYPESENSE_HOST}/collections/${collection}/documents/import?action=upsert`,
        {
          method: "POST",
          headers: { "X-TYPESENSE-API-KEY": env.TYPESENSE_API_KEY, "Content-Type": "text/plain" },
          body: ndjson,
        }
      );
      if (!res.ok) throw new Error(`Typesense index HTTP ${res.status}`);
      return { provider: "typesense", indexed: documents.length };
    },

    delete: async (env, id, collection = "trancendos") => {
      const res = await fetch(
        `https://${env.TYPESENSE_HOST}/collections/${collection}/documents/${id}`,
        { method: "DELETE", headers: { "X-TYPESENSE-API-KEY": env.TYPESENSE_API_KEY } }
      );
      if (!res.ok && res.status !== 404) throw new Error(`Typesense delete HTTP ${res.status}`);
      return { provider: "typesense", deleted: id };
    },
  },

  {
    id: "meilisearch",
    name: "Meilisearch Cloud",
    // Free: 100K documents, 10K req/month
    searchLimit: 9500,    // leave 5% buffer on 10K
    indexLimit: 95000,    // leave 5% buffer on 100K
    available: (env) => !!env.MEILISEARCH_HOST && !!env.MEILISEARCH_API_KEY,

    search: async (env, { query, collection = "trancendos", limit = 10, filters }) => {
      const body = { q: query, limit };
      if (filters) body.filter = filters;
      const res = await fetch(`${env.MEILISEARCH_HOST}/indexes/${collection}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.MEILISEARCH_API_KEY}`,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Meilisearch HTTP ${res.status}`);
      const data = await res.json();
      return {
        hits: data.hits,
        total: data.estimatedTotalHits || data.hits.length,
        provider: "meilisearch",
      };
    },

    index: async (env, documents, collection = "trancendos") => {
      const res = await fetch(`${env.MEILISEARCH_HOST}/indexes/${collection}/documents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.MEILISEARCH_API_KEY}`,
        },
        body: JSON.stringify(documents),
      });
      if (!res.ok) throw new Error(`Meilisearch index HTTP ${res.status}`);
      return { provider: "meilisearch", indexed: documents.length };
    },

    delete: async (env, id, collection = "trancendos") => {
      const res = await fetch(`${env.MEILISEARCH_HOST}/indexes/${collection}/documents/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${env.MEILISEARCH_API_KEY}` },
      });
      if (!res.ok && res.status !== 404) throw new Error(`Meilisearch delete HTTP ${res.status}`);
      return { provider: "meilisearch", deleted: id };
    },
  },

  {
    id: "algolia",
    name: "Algolia",
    // Free: 10K req/month, 10K records
    searchLimit: 9500,
    indexLimit: 9500,
    available: (env) => !!env.ALGOLIA_APP_ID && !!env.ALGOLIA_API_KEY,

    search: async (env, { query, collection, limit = 10, filters }) => {
      const index = env.ALGOLIA_INDEX || collection || "trancendos";
      const body = { query, hitsPerPage: limit };
      if (filters) body.filters = filters;
      const res = await fetch(
        `https://${env.ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/${index}/query`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Algolia-Application-Id": env.ALGOLIA_APP_ID,
            "X-Algolia-API-Key": env.ALGOLIA_API_KEY,
          },
          body: JSON.stringify(body),
        }
      );
      if (!res.ok) throw new Error(`Algolia HTTP ${res.status}`);
      const data = await res.json();
      return {
        hits: data.hits,
        total: data.nbHits,
        provider: "algolia",
      };
    },

    index: async (env, documents, collection) => {
      if (!env.ALGOLIA_WRITE_KEY) throw new Error("ALGOLIA_WRITE_KEY not set");
      const index = env.ALGOLIA_INDEX || collection || "trancendos";
      const res = await fetch(
        `https://${env.ALGOLIA_APP_ID}.algolia.net/1/indexes/${index}/batch`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Algolia-Application-Id": env.ALGOLIA_APP_ID,
            "X-Algolia-API-Key": env.ALGOLIA_WRITE_KEY,
          },
          body: JSON.stringify({
            requests: documents.map((d) => ({ action: "updateObject", body: d })),
          }),
        }
      );
      if (!res.ok) throw new Error(`Algolia index HTTP ${res.status}`);
      return { provider: "algolia", indexed: documents.length };
    },

    delete: async (env, id, collection) => {
      if (!env.ALGOLIA_WRITE_KEY) throw new Error("ALGOLIA_WRITE_KEY not set");
      const index = env.ALGOLIA_INDEX || collection || "trancendos";
      const res = await fetch(
        `https://${env.ALGOLIA_APP_ID}.algolia.net/1/indexes/${index}/${id}`,
        {
          method: "DELETE",
          headers: {
            "X-Algolia-Application-Id": env.ALGOLIA_APP_ID,
            "X-Algolia-API-Key": env.ALGOLIA_WRITE_KEY,
          },
        }
      );
      if (!res.ok && res.status !== 404) throw new Error(`Algolia delete HTTP ${res.status}`);
      return { provider: "algolia", deleted: id };
    },
  },
];

// ── KV fallback full-text (prefix matching) ────────────────────────────────
// Used when all cloud providers are over quota or unavailable
// Stores documents as KV entries: search-doc:{id} → JSON
// Maintains a search-index:{word} → [id,...] inverted index

async function kvIndex(env, documents) {
  for (const doc of documents) {
    await env.CACHE.put(`search-doc:${doc.id}`, JSON.stringify(doc));
    // Build simple word → doc inverted index
    const words = `${doc.title || ""} ${doc.content || ""} ${(doc.tags || []).join(" ")}`
      .toLowerCase().split(/\W+/).filter((w) => w.length > 2);
    const uniqueWords = [...new Set(words)];
    for (const word of uniqueWords.slice(0, 100)) {
      const existing = JSON.parse((await env.CACHE.get(`search-idx:${word}`)) || "[]");
      if (!existing.includes(doc.id)) {
        existing.push(doc.id);
        await env.CACHE.put(`search-idx:${word}`, JSON.stringify(existing.slice(-500)));
      }
    }
  }
  return { provider: "kv-fallback", indexed: documents.length };
}

async function kvSearch(env, query, limit = 10) {
  const words = query.toLowerCase().split(/\W+/).filter((w) => w.length > 2);
  const scoremap = {};
  for (const word of words) {
    const ids = JSON.parse((await env.CACHE.get(`search-idx:${word}`)) || "[]");
    for (const id of ids) {
      scoremap[id] = (scoremap[id] || 0) + 1;
    }
  }
  const sorted = Object.entries(scoremap)
    .sort(([, a], [, b]) => b - a)
    .slice(0, limit);

  const hits = [];
  for (const [id] of sorted) {
    const doc = JSON.parse((await env.CACHE.get(`search-doc:${id}`)) || "null");
    if (doc) hits.push(doc);
  }
  return { hits, total: hits.length, provider: "kv-fallback", degraded: true };
}

// ── Usage tracking ─────────────────────────────────────────────────────────

function thisMonthKey() {
  return new Date().toISOString().slice(0, 7);
}

async function getUsage(env, providerId, type = "search") {
  try {
    const val = await env.CACHE.get(`search-usage:${providerId}:${type}:${thisMonthKey()}`);
    return parseInt(val || "0", 10);
  } catch { return 0; }
}

async function incUsage(env, providerId, type = "search") {
  try {
    const key = `search-usage:${providerId}:${type}:${thisMonthKey()}`;
    const current = await getUsage(env, providerId, type);
    await env.CACHE.put(key, String(current + 1), { expirationTtl: 2764800 }); // 32-day TTL
  } catch {}
}

async function selectProvider(env, capability = "search") {
  for (const p of SEARCH_PROVIDERS) {
    if (!p.available(env)) continue;
    if (!p[capability]) continue;
    const limit = capability === "search" ? p.searchLimit : p.indexLimit;
    if (limit === Infinity) return p;
    const usage = await getUsage(env, p.id, capability);
    if (usage < limit) return p;
  }
  return null; // fall through to KV
}

// ── CORS ───────────────────────────────────────────────────────────────────

function corsHeaders(origin) {
  const allowed = ["https://trancendos.com", "https://www.trancendos.com", "http://localhost:5173"];
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
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
        service: "tranc3-search",
        timestamp: new Date().toISOString(),
        providers: SEARCH_PROVIDERS.map((p) => ({ id: p.id, name: p.name, configured: p.available(env) })),
        fallback: "KV full-text (always available)",
      }, 200, cors);
    }

    // ── GET /status ──────────────────────────────────────────────────────────
    if (url.pathname === "/status" && request.method === "GET") {
      const result = {};
      for (const p of SEARCH_PROVIDERS) {
        const sUsage = await getUsage(env, p.id, "search");
        const iUsage = await getUsage(env, p.id, "index");
        result[p.id] = {
          name: p.name,
          configured: p.available(env),
          search: { used: sUsage, limit: p.searchLimit === Infinity ? "unlimited" : p.searchLimit },
          index: { used: iUsage, limit: p.indexLimit === Infinity ? "unlimited" : p.indexLimit },
          active: p.available(env),
        };
      }
      const activeSearch = await selectProvider(env, "search");
      return json({
        status: "ok",
        activeSearchProvider: activeSearch?.id || "kv-fallback",
        providers: result,
        timestamp: new Date().toISOString(),
      }, 200, cors);
    }

    // ── POST /search ─────────────────────────────────────────────────────────
    if (url.pathname === "/search" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON" }, 400, cors); }

      if (!body.query || typeof body.query !== "string") {
        return json({ error: "'query' string is required" }, 400, cors);
      }

      const provider = await selectProvider(env, "search");

      if (!provider) {
        // Fallback to KV
        const result = await kvSearch(env, body.query, body.limit || 10);
        return json(result, 200, cors);
      }

      try {
        const result = await provider.search(env, body);
        await incUsage(env, provider.id, "search");
        return json(result, 200, cors);
      } catch {
        // Try KV fallback on provider error
        const result = await kvSearch(env, body.query, body.limit || 10);
        return json({ ...result, note: "Cloud search failed, using KV fallback" }, 200, cors);
      }
    }

    // ── POST /index ──────────────────────────────────────────────────────────
    if (url.pathname === "/index" && request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "Invalid JSON" }, 400, cors); }

      const documents = Array.isArray(body) ? body : [body];
      if (!documents.every((d) => d.id)) {
        return json({ error: "Each document must have an 'id' field" }, 400, cors);
      }

      // Always index to KV fallback (free, instant, always available)
      await kvIndex(env, documents);

      // Also index to cloud provider if available
      const provider = await selectProvider(env, "index");
      if (provider) {
        try {
          await provider.index(env, documents, body.collection);
          await incUsage(env, provider.id, "index");
          return json({ success: true, indexed: documents.length, provider: provider.id, kvFallback: true }, 201, cors);
        } catch {
          return json({ success: true, indexed: documents.length, provider: "kv-fallback", note: "Cloud index failed" }, 201, cors);
        }
      }

      return json({ success: true, indexed: documents.length, provider: "kv-fallback" }, 201, cors);
    }

    // ── DELETE /index/:id ────────────────────────────────────────────────────
    if (url.pathname.startsWith("/index/") && request.method === "DELETE") {
      const id = decodeURIComponent(url.pathname.slice("/index/".length));
      if (!id) return json({ error: "Document ID required" }, 400, cors);

      await env.CACHE.delete(`search-doc:${id}`);

      const provider = await selectProvider(env, "delete");
      if (provider) {
        try {
          await provider.delete(env, id);
          return json({ success: true, deleted: id, provider: provider.id }, 200, cors);
        } catch {
          return json({ success: true, deleted: id, provider: "kv-fallback" }, 200, cors);
        }
      }

      return json({ success: true, deleted: id, provider: "kv-fallback" }, 200, cors);
    }

    return json({ error: "Not found", path: url.pathname }, 404, cors);
  },
};
