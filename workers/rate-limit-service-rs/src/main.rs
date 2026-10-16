//! rate-limit-service — in-memory token-bucket rate limiter
//!
//! Port 8099. Replaces the Python stub with a zero-allocation Rust implementation
//! using DashMap for lock-free concurrent access.
//!
//! Routes:
//!   GET  /health
//!   POST /check       { key } -> { allowed, remaining, key }
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
use std::{sync::Arc, time::{Duration, Instant}};
use tracing::info;

#[derive(Clone)]
struct Bucket {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
    last_used: Instant,
}

impl Bucket {
    fn new(max_tokens: f64, refill_rate: f64) -> Self {
        let now = Instant::now();
        Self { tokens: max_tokens, max_tokens, refill_rate, last_refill: now, last_used: now }
    }

    fn refill(&mut self) {
        let elapsed = self.last_refill.elapsed().as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
        self.last_refill = Instant::now();
    }

    fn try_consume(&mut self) -> bool {
        self.refill();
        self.last_used = Instant::now();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

type BucketMap = Arc<DashMap<String, Bucket>>;

const BUCKET_IDLE_TTL: Duration = Duration::from_secs(3600); // evict idle buckets after 1h

#[derive(Clone)]
struct AppState {
    buckets: BucketMap,
    default_limit: u32,
    default_window_secs: u32,
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
}

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
    let max_tokens = s.default_limit as f64;
    let refill_rate = max_tokens / s.default_window_secs as f64;

    let mut entry = s
        .buckets
        .entry(body.key.clone())
        .or_insert_with(|| Bucket::new(max_tokens, refill_rate));

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

use tracing_subscriber::prelude::*;

/// Start Sentry when `SENTRY_DSN` is set, and run uninstrumented when it is not.
///
/// The DSN is read from the environment rather than written here on purpose.
/// This repository is public, and a DSN committed to public source lets anyone
/// post events into the project and exhaust its quota -- it is not a read
/// credential, but it is a write one.
///
/// `send_default_pii` is left FALSE deliberately. These services see
/// `Authorization` headers and client IPs; sending those to a third party is a
/// data-protection decision, not a default. Check it against the Magna Carta
/// rules before turning it on.
fn init_sentry() -> Option<sentry::ClientInitGuard> {
    let dsn = std::env::var("SENTRY_DSN").ok().filter(|d| !d.trim().is_empty())?;
    Some(sentry::init(
        sentry::ClientOptions::new()
            .dsn(&dsn)
            .maybe_release(sentry::release_name!())
            // The builder default is already false; stated explicitly so that
            // turning it on is a visible edit in a diff, not a silent omission.
            .send_default_pii(false)
            // Errors are always captured. Traces are sampled, and the rate is
            // an env knob so production can turn it down without a rebuild.
            .traces_sample_rate(
                std::env::var("SENTRY_TRACES_SAMPLE_RATE")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(0.1),
            ),
    ))
}

#[tokio::main]
async fn main() {
    // Held for the lifetime of main: on drop it flushes pending events.
    let _sentry = init_sentry();

    // The Sentry layer joins the EXISTING subscriber rather than replacing it,
    // so every `tracing` call already in this service reaches Sentry with no
    // call site rewritten, and local stderr output is unchanged.
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with(tracing_subscriber::fmt::layer())
        .with(sentry::integrations::tracing::layer())
        .init();

    let default_limit = std::env::var("RATE_LIMIT")
        .ok().and_then(|v| v.parse().ok()).unwrap_or(100u32);
    let default_window_secs = std::env::var("RATE_WINDOW_SECS")
        .ok().and_then(|v| v.parse().ok()).unwrap_or(60u32);

    let buckets: BucketMap = Arc::new(DashMap::new());

    // Background eviction: remove buckets idle for more than BUCKET_IDLE_TTL.
    {
        let buckets_clone = Arc::clone(&buckets);
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(300)).await;
                buckets_clone.retain(|_, b: &mut Bucket| b.last_used.elapsed() < BUCKET_IDLE_TTL);
            }
        });
    }

    let state = AppState { buckets, default_limit, default_window_secs };

    let app = Router::new()
        .route("/health", get(health))
        .route("/check", post(check))
        .route("/reset/:key", post(reset_key))
        .route("/stats", get(stats))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8099".to_string());
    let addr = format!("0.0.0.0:{port}");
    info!("rate-limit-service listening on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
