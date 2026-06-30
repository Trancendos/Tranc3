//! rate-limit-service — in-memory token-bucket rate limiter
//!
//! Port 8028. Replaces the Python stub with a zero-allocation Rust implementation
//! using DashMap for lock-free concurrent access.
//!
//! Routes:
//!   GET  /health
//!   POST /check       { key, limit?, window_secs? } -> { allowed, remaining, key }
//!   POST /reset/:key  reset bucket for a key
//!   GET  /stats       active key count

use axum::{
    extract::{Path, State},
    response::Json,
    routing::{get, post},
    Router,
};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::{sync::Arc, time::Instant};
use tracing::info;

#[derive(Clone)]
struct Bucket {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
}

impl Bucket {
    fn new(max_tokens: f64, refill_rate: f64) -> Self {
        Self { tokens: max_tokens, max_tokens, refill_rate, last_refill: Instant::now() }
    }

    fn refill(&mut self) {
        let elapsed = self.last_refill.elapsed().as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
        self.last_refill = Instant::now();
    }

    fn try_consume(&mut self) -> bool {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

type BucketMap = Arc<DashMap<String, Bucket>>;

#[derive(Clone)]
struct AppState {
    buckets: BucketMap,
}

#[derive(Serialize)]
struct HealthResp {
    status: &'static str,
    service: &'static str,
    entity: &'static str,
}

#[derive(Deserialize)]
struct CheckReq {
    key: String,
    #[serde(default = "default_limit")]
    limit: u32,
    #[serde(default = "default_window")]
    window_secs: u32,
}

fn default_limit() -> u32 { 100 }
fn default_window() -> u32 { 60 }

#[derive(Serialize)]
struct CheckResp {
    allowed: bool,
    remaining: f64,
    key: String,
}

async fn health() -> Json<HealthResp> {
    Json(HealthResp { status: "ok", service: "rate-limit-service", entity: "The HIVE" })
}

async fn check(State(s): State<AppState>, Json(body): Json<CheckReq>) -> Json<CheckResp> {
    let max_tokens = body.limit as f64;
    let refill_rate = max_tokens / body.window_secs as f64;

    let mut entry = s
        .buckets
        .entry(body.key.clone())
        .or_insert_with(|| Bucket::new(max_tokens, refill_rate));

    // Re-sync params if caller changed limit/window.
    entry.max_tokens = max_tokens;
    entry.refill_rate = refill_rate;

    let allowed = entry.try_consume();
    let remaining = entry.tokens;
    drop(entry);

    Json(CheckResp { allowed, remaining, key: body.key })
}

async fn reset_key(State(s): State<AppState>, Path(key): Path<String>) -> Json<serde_json::Value> {
    s.buckets.remove(&key);
    Json(serde_json::json!({ "reset": true, "key": key }))
}

async fn stats(State(s): State<AppState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({ "active_keys": s.buckets.len() }))
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let state = AppState { buckets: Arc::new(DashMap::new()) };

    let app = Router::new()
        .route("/health", get(health))
        .route("/check", post(check))
        .route("/reset/:key", post(reset_key))
        .route("/stats", get(stats))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8028".to_string());
    let addr = format!("0.0.0.0:{port}");
    info!("rate-limit-service listening on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
