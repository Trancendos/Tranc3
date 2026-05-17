/**
 * The Void — Encrypted Secrets Vault
 *
 * AES-GCM encryption with PBKDF2 key derivation (100k iterations).
 * D1 for metadata + encrypted payload storage.
 * KV for rate limiting.
 * R2 optional — uncomment wrangler.toml block when enabled.
 *
 * Routes:
 *   GET  /health               → health check
 *   GET  /vault/status         → vault seal status + secret count
 *   POST /secrets              → store a secret
 *   POST /secrets/retrieve     → retrieve a secret's plaintext
 *   GET  /secrets              → list own secrets (metadata only)
 *   GET  /secrets/:id          → get secret metadata
 *   DELETE /secrets/:id        → crypto-shred a secret
 *   GET  /secrets/:id/audit    → audit log for a secret
 */

export interface Env {
  DB: D1Database;
  KV_RATE_LIMIT: KVNamespace;
  R2_SECRETS?: R2Bucket;
  MASTER_KEY_SEED: string;
  INTERNAL_SECRET: string;
  INFINITY_ONE_URL: string;
  ENVIRONMENT: string;
  SERVICE_NAME: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
      "Cache-Control": "no-store",
    },
  });
}

function errorResponse(message: string, status = 400, code = "ERROR"): Response {
  return jsonResponse(
    { error: { message, code, status }, timestamp: new Date().toISOString() },
    status,
  );
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers":
      "Content-Type, Authorization, X-Request-ID, X-MFA-Token, X-Hardware-Key, X-Lighthouse-Token, X-Internal-Secret",
  };
}

async function d1Query<T = Record<string, unknown>>(
  db: D1Database,
  sql: string,
  params: unknown[] = [],
): Promise<{ data: T[] | null; error: string | null }> {
  try {
    const result = await db.prepare(sql).bind(...params).all<T>();
    return { data: result.results, error: null };
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : String(e) };
  }
}

async function d1Run(
  db: D1Database,
  sql: string,
  params: unknown[] = [],
): Promise<{ success: boolean; error: string | null }> {
  try {
    await db.prepare(sql).bind(...params).run();
    return { success: true, error: null };
  } catch (e) {
    return { success: false, error: e instanceof Error ? e.message : String(e) };
  }
}

async function checkRateLimit(
  kv: KVNamespace,
  key: string,
  max: number,
  window: number,
): Promise<boolean> {
  const k = `rl:${key}`;
  const cur = parseInt((await kv.get(k)) ?? "0", 10);
  if (cur >= max) return false;
  await kv.put(k, String(cur + 1), { expirationTtl: window });
  return true;
}

// ── Crypto ────────────────────────────────────────────────────────────────────

async function deriveKey(seed: string, salt: Uint8Array): Promise<CryptoKey> {
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(seed),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 100_000, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

async function encryptSecret(
  plaintext: string,
  masterKeySeed: string,
): Promise<{ ciphertext: string; iv: string; salt: string; tag: string }> {
  const salt = crypto.getRandomValues(new Uint8Array(32));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(masterKeySeed, salt);
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(plaintext),
  );
  const encryptedArray = new Uint8Array(encrypted);
  const ciphertext = encryptedArray.slice(0, -16);
  const tag = encryptedArray.slice(-16);
  return {
    ciphertext: btoa(String.fromCharCode(...ciphertext)),
    iv: btoa(String.fromCharCode(...iv)),
    salt: btoa(String.fromCharCode(...salt)),
    tag: btoa(String.fromCharCode(...tag)),
  };
}

async function decryptSecret(
  ciphertextB64: string,
  ivB64: string,
  saltB64: string,
  tagB64: string,
  masterKeySeed: string,
): Promise<string> {
  const ciphertext = Uint8Array.from(atob(ciphertextB64), (c) => c.charCodeAt(0));
  const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0));
  const salt = Uint8Array.from(atob(saltB64), (c) => c.charCodeAt(0));
  const tag = Uint8Array.from(atob(tagB64), (c) => c.charCodeAt(0));
  const key = await deriveKey(masterKeySeed, salt);
  const combined = new Uint8Array(ciphertext.length + tag.length);
  combined.set(ciphertext);
  combined.set(tag, ciphertext.length);
  const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, combined);
  return new TextDecoder().decode(decrypted);
}

async function hashValue(value: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ── Auth ──────────────────────────────────────────────────────────────────────

async function getAuthUserId(request: Request, env: Env): Promise<string | null> {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) return null;
  const token = authHeader.slice(7);
  try {
    const resp = await fetch(`${env.INFINITY_ONE_URL}/auth/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": env.INTERNAL_SECRET,
      },
      body: JSON.stringify({ token }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { user_id?: string };
    return data.user_id ?? null;
  } catch {
    return null;
  }
}

// ── Schema ────────────────────────────────────────────────────────────────────

async function initSchema(db: D1Database): Promise<void> {
  const stmts = [
    `CREATE TABLE IF NOT EXISTS void_secrets (
      secret_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      description TEXT,
      type TEXT NOT NULL DEFAULT 'generic',
      classification TEXT NOT NULL DEFAULT 'confidential',
      status TEXT NOT NULL DEFAULT 'active',
      version INTEGER NOT NULL DEFAULT 1,
      path TEXT,
      tags TEXT NOT NULL DEFAULT '[]',
      owner_id TEXT,
      r2_key TEXT,
      payload TEXT,
      payload_hash TEXT NOT NULL,
      iv TEXT NOT NULL,
      salt TEXT NOT NULL,
      expires_at TEXT,
      last_accessed_at TEXT,
      access_policy TEXT NOT NULL DEFAULT '{}',
      rotation_config TEXT NOT NULL DEFAULT '{}',
      metadata TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`,
    `CREATE TABLE IF NOT EXISTS void_audit_log (
      audit_id TEXT PRIMARY KEY,
      secret_id TEXT NOT NULL,
      action TEXT NOT NULL,
      actor_id TEXT,
      actor_type TEXT NOT NULL DEFAULT 'user',
      ip_address TEXT,
      success INTEGER NOT NULL DEFAULT 1,
      metadata TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL
    )`,
    `CREATE TABLE IF NOT EXISTS void_vault_state (
      state_key TEXT PRIMARY KEY,
      state_value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`,
    `CREATE INDEX IF NOT EXISTS idx_void_secrets_owner ON void_secrets(owner_id)`,
    `CREATE INDEX IF NOT EXISTS idx_void_secrets_status ON void_secrets(status)`,
    `CREATE INDEX IF NOT EXISTS idx_void_audit_secret ON void_audit_log(secret_id)`,
    `INSERT OR IGNORE INTO void_vault_state (state_key, state_value, updated_at)
     VALUES ('sealed', 'false', '${new Date().toISOString()}')`,
  ];
  for (const sql of stmts) {
    await db.prepare(sql).run().catch(console.error);
  }
}

async function isVaultSealed(db: D1Database): Promise<boolean> {
  const { data } = await d1Query<{ state_value: string }>(
    db,
    "SELECT state_value FROM void_vault_state WHERE state_key = 'sealed'",
  );
  return data?.[0]?.state_value === "true";
}

async function auditLog(
  db: D1Database,
  secretId: string,
  action: string,
  actorId: string | null,
  ip: string | null,
  success = true,
): Promise<void> {
  await d1Run(db, "INSERT INTO void_audit_log (audit_id, secret_id, action, actor_id, actor_type, ip_address, success, metadata, created_at) VALUES (?,?,?,?,?,?,?,?,?)", [
    crypto.randomUUID(),
    secretId,
    action,
    actorId,
    "user",
    ip,
    success ? 1 : 0,
    "{}",
    new Date().toISOString(),
  ]);
}

// ── Handlers ──────────────────────────────────────────────────────────────────

async function handleStoreSecret(request: Request, env: Env): Promise<Response> {
  const userId = await getAuthUserId(request, env);
  if (!userId) return errorResponse("Unauthorized", 401, "UNAUTHORIZED");
  if (await isVaultSealed(env.DB)) return errorResponse("Vault is sealed", 503, "VAULT_SEALED");
  if (!(await checkRateLimit(env.KV_RATE_LIMIT, `store:${userId}`, 50, 3600)))
    return errorResponse("Rate limit exceeded", 429, "RATE_LIMIT");

  const body = (await request.json()) as {
    name?: string;
    plaintext?: string;
    description?: string;
    type?: string;
    classification?: string;
    path?: string;
    tags?: string[];
    expires_at?: string;
    access_policy?: Record<string, unknown>;
    rotation_config?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  };
  if (!body?.name || !body?.plaintext) return errorResponse("name and plaintext required", 400);

  const secretId = crypto.randomUUID();
  const now = new Date().toISOString();
  const payloadHash = await hashValue(body.plaintext);
  const { ciphertext, iv, salt, tag } = await encryptSecret(body.plaintext, env.MASTER_KEY_SEED);

  let r2Key: string | null = null;
  let payloadInD1: string | null = null;

  if (env.R2_SECRETS) {
    r2Key = `secrets/${userId}/${secretId}`;
    await env.R2_SECRETS.put(r2Key, JSON.stringify({ ciphertext, tag }), {
      httpMetadata: { contentType: "application/octet-stream" },
    });
  } else {
    payloadInD1 = JSON.stringify({ ciphertext, tag });
  }

  await d1Run(env.DB, "INSERT INTO void_secrets (secret_id, name, description, type, classification, status, version, path, tags, owner_id, r2_key, payload, payload_hash, iv, salt, expires_at, access_policy, rotation_config, metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
    secretId,
    body.name,
    body.description ?? null,
    body.type ?? "generic",
    body.classification ?? "confidential",
    "active",
    1,
    body.path ?? null,
    JSON.stringify(body.tags ?? []),
    userId,
    r2Key,
    payloadInD1,
    payloadHash,
    iv,
    salt,
    body.expires_at ?? null,
    JSON.stringify(body.access_policy ?? {}),
    JSON.stringify(body.rotation_config ?? {}),
    JSON.stringify(body.metadata ?? {}),
    now,
    now,
  ]);

  await auditLog(env.DB, secretId, "store", userId, request.headers.get("CF-Connecting-IP"));
  return jsonResponse({ secret_id: secretId, name: body.name, status: "active", version: 1, created_at: now }, 201);
}

async function handleRetrieveSecret(request: Request, env: Env): Promise<Response> {
  const userId = await getAuthUserId(request, env);
  if (!userId) return errorResponse("Unauthorized", 401, "UNAUTHORIZED");
  if (await isVaultSealed(env.DB)) return errorResponse("Vault is sealed", 503, "VAULT_SEALED");
  if (!(await checkRateLimit(env.KV_RATE_LIMIT, `retrieve:${userId}`, 50, 3600)))
    return errorResponse("Rate limit exceeded", 429, "RATE_LIMIT");

  const body = (await request.json()) as { secret_id?: string };
  if (!body?.secret_id) return errorResponse("secret_id required", 400);

  const { data } = await d1Query<Record<string, string>>(
    env.DB,
    "SELECT * FROM void_secrets WHERE secret_id = ?",
    [body.secret_id],
  );
  if (!data?.length) return errorResponse("Secret not found", 404, "NOT_FOUND");
  const secret = data[0];
  if (secret.owner_id !== userId) return errorResponse("Forbidden", 403, "FORBIDDEN");
  if (secret.status !== "active") return errorResponse("Secret is not active", 410, "INACTIVE");

  let payload: { ciphertext: string; tag: string };
  if (secret.r2_key && env.R2_SECRETS) {
    const r2Object = await env.R2_SECRETS.get(secret.r2_key);
    if (!r2Object) return errorResponse("Secret payload not found", 404, "PAYLOAD_NOT_FOUND");
    payload = (await r2Object.json()) as { ciphertext: string; tag: string };
  } else if (secret.payload) {
    payload = JSON.parse(secret.payload) as { ciphertext: string; tag: string };
  } else {
    return errorResponse("Payload not found", 404, "PAYLOAD_NOT_FOUND");
  }

  const plaintext = await decryptSecret(payload.ciphertext, secret.iv, secret.salt, payload.tag, env.MASTER_KEY_SEED);
  await d1Run(env.DB, "UPDATE void_secrets SET last_accessed_at = ? WHERE secret_id = ?", [new Date().toISOString(), body.secret_id]);
  await auditLog(env.DB, body.secret_id, "retrieve", userId, request.headers.get("CF-Connecting-IP"));
  return jsonResponse({ secret_id: body.secret_id, plaintext });
}

async function handleGetSecretMeta(secretId: string, userId: string, env: Env): Promise<Response> {
  const { data } = await d1Query(
    env.DB,
    "SELECT secret_id, name, description, type, classification, status, version, path, tags, owner_id, expires_at, last_accessed_at, created_at, updated_at FROM void_secrets WHERE secret_id = ?",
    [secretId],
  );
  if (!data?.length) return errorResponse("Secret not found", 404, "NOT_FOUND");
  const secret = data[0] as Record<string, unknown>;
  if (secret.owner_id !== userId) return errorResponse("Forbidden", 403, "FORBIDDEN");
  return jsonResponse(data[0]);
}

async function handleDeleteSecret(secretId: string, userId: string, env: Env, request: Request): Promise<Response> {
  const { data } = await d1Query<{ owner_id: string; r2_key: string | null }>(
    env.DB,
    "SELECT owner_id, r2_key FROM void_secrets WHERE secret_id = ?",
    [secretId],
  );
  if (!data?.length) return errorResponse("Secret not found", 404, "NOT_FOUND");
  if (data[0].owner_id !== userId) return errorResponse("Forbidden", 403, "FORBIDDEN");
  if (data[0].r2_key && env.R2_SECRETS) await env.R2_SECRETS.delete(data[0].r2_key);
  await d1Run(env.DB, "UPDATE void_secrets SET status = ?, payload = NULL, updated_at = ? WHERE secret_id = ?", [
    "deleted",
    new Date().toISOString(),
    secretId,
  ]);
  await auditLog(env.DB, secretId, "crypto_shred", userId, request.headers.get("CF-Connecting-IP"));
  return jsonResponse({ secret_id: secretId, status: "deleted", shredded: true });
}

async function handleListSecrets(userId: string, env: Env): Promise<Response> {
  const { data } = await d1Query(
    env.DB,
    "SELECT secret_id, name, type, classification, status, version, created_at, expires_at FROM void_secrets WHERE owner_id = ? AND status != 'deleted' ORDER BY created_at DESC LIMIT 100",
    [userId],
  );
  return jsonResponse({ secrets: data ?? [], count: data?.length ?? 0 });
}

async function handleVaultStatus(env: Env): Promise<Response> {
  const sealed = await isVaultSealed(env.DB);
  const { data } = await d1Query<{ count: number }>(
    env.DB,
    "SELECT COUNT(*) as count FROM void_secrets WHERE status = 'active'",
  );
  return jsonResponse({
    sealed,
    secret_count: data?.[0]?.count ?? 0,
    storage: env.R2_SECRETS ? "r2+d1" : "d1",
    timestamp: new Date().toISOString(),
  });
}

async function handleGetAuditLog(secretId: string, userId: string, env: Env): Promise<Response> {
  const { data: secret } = await d1Query<{ owner_id: string }>(
    env.DB,
    "SELECT owner_id FROM void_secrets WHERE secret_id = ?",
    [secretId],
  );
  if (!secret?.length) return errorResponse("Secret not found", 404, "NOT_FOUND");
  if (secret[0].owner_id !== userId) return errorResponse("Forbidden", 403, "FORBIDDEN");
  const { data } = await d1Query(
    env.DB,
    "SELECT audit_id, action, actor_id, actor_type, ip_address, success, created_at FROM void_audit_log WHERE secret_id = ? ORDER BY created_at DESC LIMIT 100",
    [secretId],
  );
  return jsonResponse({ secret_id: secretId, audit_log: data ?? [] });
}

async function handleHealth(env: Env): Promise<Response> {
  const sealed = await isVaultSealed(env.DB).catch(() => true);
  return jsonResponse({
    status: "healthy",
    service: env.SERVICE_NAME ?? "the-void",
    version: "2.1.0",
    vault_sealed: sealed,
    storage: env.R2_SECRETS ? "r2+d1" : "d1",
    environment: env.ENVIRONMENT,
    timestamp: new Date().toISOString(),
  });
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    await initSchema(env.DB).catch(console.error);

    try {
      if (method === "GET" && path === "/health") return handleHealth(env);
      if (method === "GET" && path === "/vault/status") return handleVaultStatus(env);

      const userId = await getAuthUserId(request, env);
      if (!userId) return errorResponse("Unauthorized", 401, "UNAUTHORIZED");

      if (method === "POST" && path === "/secrets") return handleStoreSecret(request, env);
      if (method === "POST" && path === "/secrets/retrieve") return handleRetrieveSecret(request, env);
      if (method === "GET" && path === "/secrets") return handleListSecrets(userId, env);

      const secretMatch = path.match(/^\/secrets\/([\w-]+)$/);
      if (secretMatch) {
        const secretId = secretMatch[1];
        if (method === "GET") return handleGetSecretMeta(secretId, userId, env);
        if (method === "DELETE") return handleDeleteSecret(secretId, userId, env, request);
      }

      const auditMatch = path.match(/^\/secrets\/([\w-]+)\/audit$/);
      if (auditMatch && method === "GET") return handleGetAuditLog(auditMatch[1], userId, env);

      return errorResponse("Not found", 404, "NOT_FOUND");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Internal server error";
      console.error("VOID error:", msg);
      return errorResponse(msg, 500, "INTERNAL_ERROR");
    }
  },
};
