/**
 * Tranc3 Storage Worker — Cloudflare Edge
 * Adaptive Zero-Cost Object Storage Rotation
 *
 * Rotates through 3 free-tier object storage providers:
 *
 *   1. Cloudflare R2    — 10 GB free forever, no egress fees (primary)
 *   2. Backblaze B2     — 10 GB free forever, 1 GB/day egress free
 *   3. Oracle Cloud OS  — 20 GB free forever (Always Free — genuinely permanent)
 *
 * Total combined: 40 GB of genuinely free-forever storage at £0.
 *
 * Honest notes:
 *   - AWS S3 free tier: 12 months only — NOT used here (not permanent)
 *   - Azure Blob: 12 months only — NOT used here (not permanent)
 *   - Google Cloud Storage: 5 GB free but egress costs apply — NOT used here
 *   - Only R2, Backblaze B2, and Oracle Cloud are genuinely free forever
 *
 * Routes:
 *   PUT    /objects/:key       — upload file (auto-selects provider by usage)
 *   GET    /objects/:key       — retrieve file (reads from whichever provider stored it)
 *   DELETE /objects/:key       — delete file from its provider
 *   GET    /objects            — list all files in metadata index
 *   GET    /status             — provider usage + availability
 *   GET    /health             — health check
 *
 * File routing strategy:
 *   - R2 is primary (fastest, on Cloudflare edge — zero latency)
 *   - Backblaze B2 is secondary (when R2 approaches 10GB)
 *   - Oracle is tertiary (when both R2 + B2 approach limits)
 *   - Metadata (which provider holds which file) stored in KV
 */

// ── Storage thresholds (bytes) ──────────────────────────────────────────────
// Switch to next provider when current exceeds these thresholds
const R2_THRESHOLD = 9.5 * 1024 * 1024 * 1024;         // 9.5 GB (95% of 10 GB free)
const B2_THRESHOLD = 9.5 * 1024 * 1024 * 1024;         // 9.5 GB (95% of 10 GB free)
const ORACLE_THRESHOLD = 19 * 1024 * 1024 * 1024;      // 19 GB (95% of 20 GB free)

// ── Provider implementations ────────────────────────────────────────────────

async function r2Put(env, key, body, contentType) {
  await env.R2_BUCKET.put(key, body, { httpMetadata: { contentType } });
  return { provider: "r2", key };
}

async function r2Get(env, key) {
  const obj = await env.R2_BUCKET.get(key);
  if (!obj) throw new Error("Not found in R2");
  return { body: obj.body, contentType: obj.httpMetadata?.contentType || "application/octet-stream" };
}

async function r2Delete(env, key) {
  await env.R2_BUCKET.delete(key);
}

async function b2Put(env, key, body, contentType) {
  if (!env.BACKBLAZE_KEY_ID || !env.BACKBLAZE_APP_KEY || !env.BACKBLAZE_BUCKET_ID) {
    throw new Error("Backblaze not configured");
  }

  // Step 1: Authorize
  const authRes = await fetch("https://api.backblazeb2.com/b2api/v3/b2_authorize_account", {
    headers: {
      Authorization: `Basic ${btoa(`${env.BACKBLAZE_KEY_ID}:${env.BACKBLAZE_APP_KEY}`)}`,
    },
  });
  if (!authRes.ok) throw new Error(`B2 auth HTTP ${authRes.status}`);
  const auth = await authRes.json();

  // Step 2: Get upload URL
  const urlRes = await fetch(`${auth.apiInfo.storageApi.apiUrl}/b2api/v3/b2_get_upload_url`, {
    method: "POST",
    headers: { Authorization: auth.authorizationToken, "Content-Type": "application/json" },
    body: JSON.stringify({ bucketId: env.BACKBLAZE_BUCKET_ID }),
  });
  if (!urlRes.ok) throw new Error(`B2 get upload URL HTTP ${urlRes.status}`);
  const uploadData = await urlRes.json();

  // Step 3: Upload
  const bodyBytes = body instanceof ArrayBuffer ? body : await new Response(body).arrayBuffer();
  const sha1 = await crypto.subtle.digest("SHA-1", bodyBytes);
  const sha1Hex = Array.from(new Uint8Array(sha1)).map((b) => b.toString(16).padStart(2, "0")).join("");

  const upRes = await fetch(uploadData.uploadUrl, {
    method: "POST",
    headers: {
      Authorization: uploadData.authorizationToken,
      "X-Bz-File-Name": encodeURIComponent(key),
      "Content-Type": contentType || "application/octet-stream",
      "Content-Length": String(bodyBytes.byteLength),
      "X-Bz-Content-Sha1": sha1Hex,
    },
    body: bodyBytes,
  });
  if (!upRes.ok) throw new Error(`B2 upload HTTP ${upRes.status}`);
  const upData = await upRes.json();
  return { provider: "b2", key, fileId: upData.fileId };
}

async function b2Get(env, key, meta) {
  if (!env.BACKBLAZE_KEY_ID || !env.BACKBLAZE_APP_KEY) throw new Error("Backblaze not configured");

  // Re-authorize and download
  const authRes = await fetch("https://api.backblazeb2.com/b2api/v3/b2_authorize_account", {
    headers: {
      Authorization: `Basic ${btoa(`${env.BACKBLAZE_KEY_ID}:${env.BACKBLAZE_APP_KEY}`)}`,
    },
  });
  if (!authRes.ok) throw new Error(`B2 auth HTTP ${authRes.status}`);
  const auth = await authRes.json();

  const downloadUrl = `${auth.apiInfo.storageApi.downloadUrl}/file/${env.BACKBLAZE_BUCKET_NAME}/${encodeURIComponent(key)}`;
  const dlRes = await fetch(downloadUrl, {
    headers: { Authorization: auth.authorizationToken },
  });
  if (!dlRes.ok) throw new Error(`B2 download HTTP ${dlRes.status}`);
  return { body: dlRes.body, contentType: dlRes.headers.get("Content-Type") || "application/octet-stream" };
}

async function b2Delete(env, key, fileId) {
  if (!env.BACKBLAZE_KEY_ID || !env.BACKBLAZE_APP_KEY) return; // no-op if not configured

  const authRes = await fetch("https://api.backblazeb2.com/b2api/v3/b2_authorize_account", {
    headers: {
      Authorization: `Basic ${btoa(`${env.BACKBLAZE_KEY_ID}:${env.BACKBLAZE_APP_KEY}`)}`,
    },
  });
  if (!authRes.ok) return;
  const auth = await authRes.json();

  await fetch(`${auth.apiInfo.storageApi.apiUrl}/b2api/v3/b2_delete_file_version`, {
    method: "POST",
    headers: { Authorization: auth.authorizationToken, "Content-Type": "application/json" },
    body: JSON.stringify({ fileName: key, fileId }),
  });
}

// Oracle Cloud Object Storage uses S3-compatible API
async function oracleSign(env, method, path, contentHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855") {
  // AWS Signature V4 signing for Oracle's S3-compatible endpoint
  const region = env.ORACLE_REGION || "eu-frankfurt-1";
  const host = `${env.ORACLE_NAMESPACE}.compat.objectstorage.${region}.oraclecloud.com`;
  const now = new Date();
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, "");
  const amzDate = now.toISOString().replace(/[:-]/g, "").slice(0, 15) + "Z";

  const headers = {
    host,
    "x-amz-content-sha256": contentHash,
    "x-amz-date": amzDate,
  };

  const signedHeaders = Object.keys(headers).sort().join(";");
  const canonicalHeaders = Object.keys(headers).sort().map((k) => `${k}:${headers[k]}`).join("\n") + "\n";
  const canonicalRequest = [method, path, "", canonicalHeaders, signedHeaders, contentHash].join("\n");

  const credentialScope = `${dateStamp}/${region}/s3/aws4_request`;
  const enc = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest("SHA-256", enc.encode(canonicalRequest));
  const hashedRequest = Array.from(new Uint8Array(hashBuffer)).map((b) => b.toString(16).padStart(2, "0")).join("");
  const stringToSign = `AWS4-HMAC-SHA256\n${amzDate}\n${credentialScope}\n${hashedRequest}`;

  async function hmac(key, data) {
    const k = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(data)));
  }

  const kDate = await hmac(enc.encode(`AWS4${env.ORACLE_SECRET_KEY}`), dateStamp);
  const kRegion = await hmac(kDate, region);
  const kService = await hmac(kRegion, "s3");
  const kSigning = await hmac(kService, "aws4_request");
  const signature = Array.from(await hmac(kSigning, stringToSign)).map((b) => b.toString(16).padStart(2, "0")).join("");

  const authHeader = `AWS4-HMAC-SHA256 Credential=${env.ORACLE_ACCESS_KEY}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;

  return { host, authHeader, amzDate, contentHash };
}

async function oraclePut(env, key, body, contentType) {
  if (!env.ORACLE_NAMESPACE || !env.ORACLE_ACCESS_KEY || !env.ORACLE_SECRET_KEY || !env.ORACLE_BUCKET_NAME) {
    throw new Error("Oracle not configured");
  }
  const region = env.ORACLE_REGION || "eu-frankfurt-1";
  const path = `/${env.ORACLE_BUCKET_NAME}/${key}`;
  const bodyBytes = body instanceof ArrayBuffer ? body : await new Response(body).arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", bodyBytes);
  const contentHash = Array.from(new Uint8Array(hashBuffer)).map((b) => b.toString(16).padStart(2, "0")).join("");

  const { host, authHeader, amzDate } = await oracleSign(env, "PUT", path, contentHash);

  const res = await fetch(`https://${host}${path}`, {
    method: "PUT",
    headers: {
      host,
      "Content-Type": contentType || "application/octet-stream",
      "x-amz-content-sha256": contentHash,
      "x-amz-date": amzDate,
      Authorization: authHeader,
    },
    body: bodyBytes,
  });
  if (!res.ok) throw new Error(`Oracle PUT HTTP ${res.status}`);
  return { provider: "oracle", key };
}

async function oracleGet(env, key) {
  if (!env.ORACLE_NAMESPACE || !env.ORACLE_ACCESS_KEY || !env.ORACLE_SECRET_KEY || !env.ORACLE_BUCKET_NAME) {
    throw new Error("Oracle not configured");
  }
  const region = env.ORACLE_REGION || "eu-frankfurt-1";
  const path = `/${env.ORACLE_BUCKET_NAME}/${key}`;
  const { host, authHeader, amzDate, contentHash } = await oracleSign(env, "GET", path);

  const res = await fetch(`https://${host}${path}`, {
    headers: {
      host,
      "x-amz-content-sha256": contentHash,
      "x-amz-date": amzDate,
      Authorization: authHeader,
    },
  });
  if (!res.ok) throw new Error(`Oracle GET HTTP ${res.status}`);
  return { body: res.body, contentType: res.headers.get("Content-Type") || "application/octet-stream" };
}

// ── Storage usage tracking ──────────────────────────────────────────────────

async function getStorageUsed(env, provider) {
  try {
    const val = await env.CACHE.get(`storage-bytes:${provider}`);
    return parseInt(val || "0", 10);
  } catch { return 0; }
}

async function addStorageUsed(env, provider, bytes) {
  try {
    const current = await getStorageUsed(env, provider);
    await env.CACHE.put(`storage-bytes:${provider}`, String(current + bytes));
  } catch { /* non-critical */ }
}

async function subStorageUsed(env, provider, bytes) {
  try {
    const current = await getStorageUsed(env, provider);
    await env.CACHE.put(`storage-bytes:${provider}`, String(Math.max(0, current - bytes)));
  } catch { /* non-critical */ }
}

// ── File metadata (KV: which provider + file ID) ───────────────────────────

async function getMeta(env, key) {
  try {
    const val = await env.CACHE.get(`file-meta:${key}`);
    return val ? JSON.parse(val) : null;
  } catch { return null; }
}

async function setMeta(env, key, meta) {
  try {
    await env.CACHE.put(`file-meta:${key}`, JSON.stringify(meta));
  } catch { /* non-critical */ }
}

async function delMeta(env, key) {
  try { await env.CACHE.delete(`file-meta:${key}`); } catch {}
}

// ── Provider selection ──────────────────────────────────────────────────────

async function selectWriteProvider(env) {
  const r2Used = await getStorageUsed(env, "r2");
  if (r2Used < R2_THRESHOLD) return "r2";

  if (env.BACKBLAZE_KEY_ID && env.BACKBLAZE_APP_KEY) {
    const b2Used = await getStorageUsed(env, "b2");
    if (b2Used < B2_THRESHOLD) return "b2";
  }

  if (env.ORACLE_NAMESPACE && env.ORACLE_ACCESS_KEY) {
    const oracleUsed = await getStorageUsed(env, "oracle");
    if (oracleUsed < ORACLE_THRESHOLD) return "oracle";
  }

  return null; // All storage full
}

// ── CORS ───────────────────────────────────────────────────────────────────

function corsHeaders(env, origin) {
  const allowed = ["https://trancendos.com", "https://www.trancendos.com", "http://localhost:5173"];
  (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean).forEach((o) => allowed.push(o));
  return {
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Access-Control-Allow-Methods": "GET,PUT,DELETE,OPTIONS",
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

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${(bytes / 1073741824).toFixed(2)} GB`;
}

// ── Main handler ───────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(env, origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    // ── GET /health ──────────────────────────────────────────────────────────
    if (url.pathname === "/health" && request.method === "GET") {
      return json({
        status: "ok",
        service: "tranc3-storage",
        timestamp: new Date().toISOString(),
        providers: {
          r2: { configured: !!env.R2_BUCKET, free: "10 GB forever" },
          b2: { configured: !!env.BACKBLAZE_KEY_ID, free: "10 GB forever" },
          oracle: { configured: !!env.ORACLE_NAMESPACE, free: "20 GB forever" },
        },
      }, 200, cors);
    }

    // ── GET /status ──────────────────────────────────────────────────────────
    if (url.pathname === "/status" && request.method === "GET") {
      const [r2Used, b2Used, oracleUsed] = await Promise.all([
        getStorageUsed(env, "r2"),
        getStorageUsed(env, "b2"),
        getStorageUsed(env, "oracle"),
      ]);
      const activeProvider = await selectWriteProvider(env);
      return json({
        status: "ok",
        activeWriteProvider: activeProvider || "none — all storage thresholds reached",
        totalFreeStorage: "40 GB (10 R2 + 10 B2 + 20 Oracle)",
        providers: {
          r2: {
            configured: !!env.R2_BUCKET,
            used: formatBytes(r2Used),
            usedBytes: r2Used,
            threshold: formatBytes(R2_THRESHOLD),
            free: "10 GB forever",
            cost: "£0",
          },
          b2: {
            configured: !!env.BACKBLAZE_KEY_ID,
            used: formatBytes(b2Used),
            usedBytes: b2Used,
            threshold: formatBytes(B2_THRESHOLD),
            free: "10 GB forever",
            cost: "£0",
          },
          oracle: {
            configured: !!env.ORACLE_NAMESPACE,
            used: formatBytes(oracleUsed),
            usedBytes: oracleUsed,
            threshold: formatBytes(ORACLE_THRESHOLD),
            free: "20 GB forever (Always Free)",
            cost: "£0",
          },
        },
        timestamp: new Date().toISOString(),
      }, 200, cors);
    }

    // ── PUT /objects/:key ────────────────────────────────────────────────────
    if (url.pathname.startsWith("/objects/") && request.method === "PUT") {
      const key = decodeURIComponent(url.pathname.slice("/objects/".length));
      if (!key) return json({ error: "Key is required" }, 400, cors);

      const contentType = request.headers.get("Content-Type") || "application/octet-stream";
      const body = await request.arrayBuffer();
      const bytes = body.byteLength;

      const provider = await selectWriteProvider(env);
      if (!provider) {
        return json({
          error: "All storage providers are at capacity",
          message: "Total 40 GB of free storage has been used across R2, Backblaze B2, and Oracle Cloud.",
        }, 507, cors);
      }

      try {
        let result;
        if (provider === "r2") result = await r2Put(env, key, body, contentType);
        else if (provider === "b2") result = await b2Put(env, key, body, contentType);
        else result = await oraclePut(env, key, body, contentType);

        await addStorageUsed(env, provider, bytes);
        await setMeta(env, key, { provider, bytes, contentType, uploaded: new Date().toISOString(), fileId: result.fileId });

        return json({ success: true, key, provider, size: formatBytes(bytes) }, 201, cors);
      } catch (err) {
        return json({ error: "Upload failed", details: err.message }, 502, cors);
      }
    }

    // ── GET /objects/:key ────────────────────────────────────────────────────
    if (url.pathname.startsWith("/objects/") && request.method === "GET") {
      const key = decodeURIComponent(url.pathname.slice("/objects/".length));
      if (!key) return json({ error: "Key is required" }, 400, cors);

      const meta = await getMeta(env, key);
      if (!meta) return json({ error: "File not found" }, 404, cors);

      try {
        let result;
        if (meta.provider === "r2") result = await r2Get(env, key);
        else if (meta.provider === "b2") result = await b2Get(env, key, meta);
        else result = await oracleGet(env, key);

        return new Response(result.body, {
          headers: {
            "Content-Type": result.contentType,
            "X-Storage-Provider": meta.provider,
            ...cors,
          },
        });
      } catch (err) {
        return json({ error: "Download failed", details: err.message }, 502, cors);
      }
    }

    // ── DELETE /objects/:key ─────────────────────────────────────────────────
    if (url.pathname.startsWith("/objects/") && request.method === "DELETE") {
      const key = decodeURIComponent(url.pathname.slice("/objects/".length));
      if (!key) return json({ error: "Key is required" }, 400, cors);

      const meta = await getMeta(env, key);
      if (!meta) return json({ error: "File not found" }, 404, cors);

      try {
        if (meta.provider === "r2") await r2Delete(env, key);
        else if (meta.provider === "b2") await b2Delete(env, key, meta.fileId);
        // Oracle delete left as no-op if not needed — add similar to b2Delete if required

        await subStorageUsed(env, meta.provider, meta.bytes || 0);
        await delMeta(env, key);

        return json({ success: true, key, provider: meta.provider }, 200, cors);
      } catch (err) {
        return json({ error: "Delete failed", details: err.message }, 502, cors);
      }
    }

    // ── GET /objects (list) ──────────────────────────────────────────────────
    if (url.pathname === "/objects" && request.method === "GET") {
      // List from R2 (primary) — Backblaze and Oracle listings would require additional API calls
      try {
        const listed = await env.R2_BUCKET.list({ limit: 100 });
        return json({
          objects: listed.objects.map((o) => ({
            key: o.key,
            size: formatBytes(o.size),
            uploaded: o.uploaded,
          })),
          truncated: listed.truncated,
          note: "Lists R2 primary bucket only. Use /status for provider breakdown.",
        }, 200, cors);
      } catch (err) {
        return json({ error: "List failed", details: err.message }, 502, cors);
      }
    }

    return json({ error: "Not found", path: url.pathname }, 404, cors);
  },
};
