//! vault-service — The Void (self-hosted AES-256-GCM secrets vault)
//!
//! Port 8082. Implements the same HTTP contract as the CF Worker infinity-void:
//!   GET  /health
//!   GET  /vault/status
//!   POST /secrets                  store + encrypt
//!   POST /secrets/retrieve         decrypt + return plaintext
//!   GET  /secrets                  list metadata (no values)
//!   GET  /secrets/:id              single secret metadata
//!   DELETE /secrets/:id
//!   GET  /secrets/:id/audit        audit log
//!
//! Crypto: PBKDF2-HMAC-SHA256 (100k rounds) key derivation + AES-256-GCM per secret.
//! Storage: SQLite via rusqlite (bundled).

use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::Json,
    routing::{delete, get, post},
    Router,
};
use ring::{
    aead,
    pbkdf2,
    rand::{self, SecureRandom},
};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::{num::NonZeroU32, sync::{Arc, Mutex}};
use tracing::info;
use uuid::Uuid;

type Db = Arc<Mutex<Connection>>;

#[derive(Clone)]
struct AppState {
    db: Db,
    master_key: String,
    internal_secret: String,
}

fn check_internal_auth(headers: &HeaderMap, secret: &str) -> bool {
    if secret.is_empty() {
        return true;
    }
    headers
        .get("x-internal-secret")
        .and_then(|v| v.to_str().ok())
        .map(|v| v == secret)
        .unwrap_or(false)
}

#[derive(Serialize)]
struct HealthResp {
    status: &'static str,
    service: &'static str,
    entity: &'static str,
}

#[derive(Serialize)]
struct VaultStatus {
    status: &'static str,
    total_secrets: i64,
    service: &'static str,
}

#[derive(Deserialize)]
struct StoreBody {
    name: String,
    value: String,
    description: Option<String>,
    tags: Option<Vec<String>>,
}

#[derive(Deserialize)]
struct RetrieveBody {
    id: String,
}

#[derive(Serialize)]
struct SecretMeta {
    id: String,
    name: String,
    description: Option<String>,
    tags: Option<String>,
    created_at: String,
}

#[derive(Serialize)]
struct SecretFull {
    id: String,
    name: String,
    value: String,
    description: Option<String>,
    tags: Option<String>,
    created_at: String,
}

#[derive(Serialize)]
struct AuditEntry {
    id: i64,
    secret_id: String,
    action: String,
    timestamp: String,
}

fn init_db(conn: &Connection) {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS secrets (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            ciphertext  BLOB NOT NULL,
            nonce       BLOB NOT NULL,
            salt        BLOB NOT NULL,
            description TEXT,
            tags        TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_id   TEXT NOT NULL,
            action      TEXT NOT NULL,
            timestamp   TEXT NOT NULL DEFAULT (datetime('now'))
        );",
    )
    .expect("db init failed");
}

fn derive_key(master_key: &str, salt: &[u8]) -> [u8; 32] {
    let mut key = [0u8; 32];
    pbkdf2::derive(
        pbkdf2::PBKDF2_HMAC_SHA256,
        NonZeroU32::new(100_000).unwrap(),
        salt,
        master_key.as_bytes(),
        &mut key,
    );
    key
}

fn encrypt(master_key: &str, plaintext: &[u8]) -> Result<(Vec<u8>, [u8; 12], [u8; 32]), &'static str> {
    let rng = rand::SystemRandom::new();
    let mut salt = [0u8; 32];
    let mut nonce_bytes = [0u8; 12];
    rng.fill(&mut salt).map_err(|_| "rng error")?;
    rng.fill(&mut nonce_bytes).map_err(|_| "rng error")?;

    let key_bytes = derive_key(master_key, &salt);
    let uk = aead::UnboundKey::new(&aead::AES_256_GCM, &key_bytes).map_err(|_| "key error")?;
    let sk = aead::LessSafeKey::new(uk);
    let nonce = aead::Nonce::assume_unique_for_key(nonce_bytes);

    let mut buf = plaintext.to_vec();
    sk.seal_in_place_append_tag(nonce, aead::Aad::empty(), &mut buf)
        .map_err(|_| "seal error")?;

    Ok((buf, nonce_bytes, salt))
}

fn decrypt(master_key: &str, ciphertext: &[u8], nonce_bytes: &[u8], salt: &[u8]) -> Result<Vec<u8>, &'static str> {
    let key_bytes = derive_key(master_key, salt);
    let uk = aead::UnboundKey::new(&aead::AES_256_GCM, &key_bytes).map_err(|_| "key error")?;
    let ok = aead::LessSafeKey::new(uk);

    let mut arr = [0u8; 12];
    arr.copy_from_slice(nonce_bytes);
    let nonce = aead::Nonce::assume_unique_for_key(arr);

    let mut buf = ciphertext.to_vec();
    let plain = ok
        .open_in_place(nonce, aead::Aad::empty(), &mut buf)
        .map_err(|_| "decrypt error")?;
    Ok(plain.to_vec())
}

type AppError = (StatusCode, Json<serde_json::Value>);

fn err(code: StatusCode, msg: &str) -> AppError {
    (code, Json(serde_json::json!({ "error": msg })))
}

async fn health() -> Json<HealthResp> {
    Json(HealthResp { status: "ok", service: "vault-service", entity: "The Void" })
}

async fn vault_status(State(s): State<AppState>) -> Json<VaultStatus> {
    let db = s.db.lock().unwrap();
    let n: i64 = db
        .query_row("SELECT COUNT(*) FROM secrets", [], |r| r.get(0))
        .unwrap_or(0);
    Json(VaultStatus { status: "ok", total_secrets: n, service: "vault-service" })
}

async fn store_secret(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<StoreBody>,
) -> Result<(StatusCode, Json<serde_json::Value>), AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let id = Uuid::new_v4().to_string();
    let (ciphertext, nonce, salt) =
        encrypt(&s.master_key, body.value.as_bytes()).map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e))?;
    let tags_str = body.tags.as_ref().and_then(|t| serde_json::to_string(t).ok());

    let db = s.db.lock().unwrap();
    db.execute(
        "INSERT INTO secrets (id,name,ciphertext,nonce,salt,description,tags) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![id, body.name, ciphertext.as_slice(), nonce.as_slice(), salt.as_slice(), body.description, tags_str],
    )
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    db.execute("INSERT INTO audit_log(secret_id,action) VALUES(?1,'store')", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok((StatusCode::CREATED, Json(serde_json::json!({ "id": id, "name": body.name }))))
}

async fn retrieve_secret(
    State(s): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<RetrieveBody>,
) -> Result<Json<SecretFull>, AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let db = s.db.lock().unwrap();
    let row = db
        .query_row(
            "SELECT id,name,ciphertext,nonce,salt,description,tags,created_at FROM secrets WHERE id=?1",
            params![body.id],
            |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, Vec<u8>>(2)?,
                    r.get::<_, Vec<u8>>(3)?,
                    r.get::<_, Vec<u8>>(4)?,
                    r.get::<_, Option<String>>(5)?,
                    r.get::<_, Option<String>>(6)?,
                    r.get::<_, String>(7)?,
                ))
            },
        )
        .map_err(|_| err(StatusCode::NOT_FOUND, "not found"))?;

    let (id, name, ciphertext, nonce, salt, description, tags, created_at) = row;
    let plain = decrypt(&s.master_key, &ciphertext, &nonce, &salt)
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e))?;
    let value = String::from_utf8(plain).map_err(|_| err(StatusCode::INTERNAL_SERVER_ERROR, "utf8 error"))?;

    db.execute("INSERT INTO audit_log(secret_id,action) VALUES(?1,'retrieve')", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;

    Ok(Json(SecretFull { id, name, value, description, tags, created_at }))
}

async fn list_secrets(State(s): State<AppState>, headers: HeaderMap) -> Result<Json<Vec<SecretMeta>>, AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let db = s.db.lock().unwrap();
    let mut stmt = db
        .prepare("SELECT id,name,description,tags,created_at FROM secrets ORDER BY created_at DESC")
        .unwrap();
    let rows = stmt
        .query_map([], |r| {
            Ok(SecretMeta {
                id: r.get(0)?,
                name: r.get(1)?,
                description: r.get(2)?,
                tags: r.get(3)?,
                created_at: r.get(4)?,
            })
        })
        .unwrap();
    Ok(Json(rows.filter_map(|r| r.ok()).collect()))
}

async fn get_secret(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<SecretMeta>, AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let db = s.db.lock().unwrap();
    db.query_row(
        "SELECT id,name,description,tags,created_at FROM secrets WHERE id=?1",
        params![id],
        |r| {
            Ok(SecretMeta {
                id: r.get(0)?,
                name: r.get(1)?,
                description: r.get(2)?,
                tags: r.get(3)?,
                created_at: r.get(4)?,
            })
        },
    )
    .map(Json)
    .map_err(|_| err(StatusCode::NOT_FOUND, "not found"))
}

async fn delete_secret(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let db = s.db.lock().unwrap();
    let n = db
        .execute("DELETE FROM secrets WHERE id=?1", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    if n == 0 {
        return Err(err(StatusCode::NOT_FOUND, "not found"));
    }
    db.execute("INSERT INTO audit_log(secret_id,action) VALUES(?1,'delete')", params![id])
        .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()))?;
    Ok(Json(serde_json::json!({ "deleted": true })))
}

async fn get_audit(
    State(s): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<Vec<AuditEntry>>, AppError> {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return Err(err(StatusCode::UNAUTHORIZED, "unauthorized"));
    }
    let db = s.db.lock().unwrap();
    let mut stmt = db
        .prepare(
            "SELECT id,secret_id,action,timestamp FROM audit_log WHERE secret_id=?1 ORDER BY timestamp DESC LIMIT 100",
        )
        .unwrap();
    let rows = stmt
        .query_map(params![id], |r| {
            Ok(AuditEntry {
                id: r.get(0)?,
                secret_id: r.get(1)?,
                action: r.get(2)?,
                timestamp: r.get(3)?,
            })
        })
        .unwrap();
    Ok(Json(rows.filter_map(|r| r.ok()).collect()))
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let master_key = std::env::var("VAULT_MASTER_KEY")
        .or_else(|_| std::env::var("MASTER_KEY"))
        .expect("VAULT_MASTER_KEY or MASTER_KEY must be set");

    let internal_secret = std::env::var("INTERNAL_SECRET").unwrap_or_default();

    let db_path = std::env::var("VAULT_DB_PATH").unwrap_or_else(|_| "/data/vault.db".to_string());
    let conn = Connection::open(&db_path).expect("open db");
    init_db(&conn);
    let db: Db = Arc::new(Mutex::new(conn));

    let state = AppState { db, master_key, internal_secret };

    let app = Router::new()
        .route("/health", get(health))
        .route("/vault/status", get(vault_status))
        .route("/secrets", post(store_secret).get(list_secrets))
        .route("/secrets/retrieve", post(retrieve_secret))
        .route("/secrets/:id", get(get_secret).delete(delete_secret))
        .route("/secrets/:id/audit", get(get_audit))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8082".to_string());
    let addr = format!("0.0.0.0:{port}");
    info!("vault-service (The Void) listening on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
