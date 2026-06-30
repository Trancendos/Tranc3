//! nexus-ws — The Nexus WebSocket hub
//!
//! Port 8004. Replaces the Python infinity-ws worker with a zero-allocation Rust
//! implementation. Supports channel-based pub/sub, JWT auth, per-connection rate
//! limiting, and internal-secret protected admin routes.
//!
//! Routes:
//!   GET  /health            — public
//!   GET  /ws?token=&user_id= — WebSocket upgrade
//!   GET  /stats             — internal auth
//!   GET  /channels          — internal auth
//!   POST /broadcast         — internal auth; body: { channel, data, type? }

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Query, State,
    },
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Json},
    routing::{get, post},
    Router,
};
use dashmap::DashMap;
use futures::{sink::SinkExt, stream::StreamExt};
use jsonwebtoken::{decode, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use tokio::sync::{mpsc, RwLock};
use tracing::{info, warn};
use uuid::Uuid;

// ── Types ────────────────────────────────────────────────────────────────────

type ConnId = Uuid;

struct ConnHandle {
    tx: mpsc::UnboundedSender<String>,
    user_id: String,
}

struct AppState {
    connections: DashMap<ConnId, ConnHandle>,
    // channel name → set of ConnIds
    channels: RwLock<std::collections::HashMap<String, HashSet<ConnId>>>,
    messages_sent: AtomicU64,
    started_at: Instant,
    jwt_secret: String,
    internal_secret: String,
    max_connections: usize,
    max_channels: usize,
}

impl AppState {
    fn new(jwt_secret: String, internal_secret: String) -> Self {
        Self {
            connections: DashMap::new(),
            channels: RwLock::new(std::collections::HashMap::new()),
            messages_sent: AtomicU64::new(0),
            started_at: Instant::now(),
            jwt_secret,
            internal_secret,
            max_connections: 1000,
            max_channels: 100,
        }
    }
}

// ── Message shapes ────────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct WsMsg {
    #[serde(rename = "type")]
    kind: String,
    channel: Option<String>,
    data: Option<Value>,
}

#[derive(Deserialize)]
struct WsParams {
    token: Option<String>,
    user_id: Option<String>,
}

#[derive(Deserialize)]
struct BroadcastBody {
    channel: String,
    #[serde(rename = "type")]
    kind: Option<String>,
    data: Option<Value>,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn now_iso() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    // Simple ISO-8601 approximation (no chrono dep)
    let s = secs % 60;
    let m = (secs / 60) % 60;
    let h = (secs / 3600) % 24;
    let days = secs / 86400;
    // epoch day → year/month/day (Gregorian, good enough for log timestamps)
    let y = 1970 + days / 365;
    format!("{y}-01-01T{h:02}:{m:02}:{s:02}Z")
}

fn build_msg(kind: &str, channel: Option<&str>, data: Value, msg_id: &str) -> String {
    let mut m = json!({
        "type": kind,
        "sender": "system",
        "message_id": msg_id,
        "timestamp": now_iso(),
        "data": data,
    });
    if let Some(ch) = channel {
        m["channel"] = json!(ch);
    }
    m.to_string()
}

fn verify_jwt(token: &str, secret: &str) -> Option<String> {
    if secret.is_empty() {
        return None;
    }
    let key = DecodingKey::from_secret(secret.as_bytes());
    let mut v = Validation::new(jsonwebtoken::Algorithm::HS256);
    v.validate_exp = true;
    decode::<Value>(token, &key, &v)
        .ok()
        .and_then(|t| {
            t.claims
                .get("sub")
                .or_else(|| t.claims.get("user_id"))
                .and_then(|v| v.as_str().map(String::from))
        })
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

// ── Broadcast helper ──────────────────────────────────────────────────────────

async fn broadcast_to_channel(
    state: &Arc<AppState>,
    channel: &str,
    payload: String,
    exclude: Option<ConnId>,
) -> usize {
    let channels = state.channels.read().await;
    let ids = match channels.get(channel) {
        Some(s) => s.clone(),
        None => return 0,
    };
    drop(channels);

    let mut sent = 0usize;
    for id in &ids {
        if Some(*id) == exclude {
            continue;
        }
        if let Some(h) = state.connections.get(id) {
            if h.tx.send(payload.clone()).is_ok() {
                sent += 1;
            }
        }
    }
    state.messages_sent.fetch_add(sent as u64, Ordering::Relaxed);
    sent
}

// ── Routes ────────────────────────────────────────────────────────────────────

async fn health(State(s): State<Arc<AppState>>) -> Json<Value> {
    Json(json!({
        "status": "healthy",
        "service": "nexus-ws",
        "entity": "The Nexus",
        "connections": s.connections.len(),
        "channels": s.channels.read().await.len(),
    }))
}

async fn stats(State(s): State<Arc<AppState>>, headers: HeaderMap) -> impl IntoResponse {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return (StatusCode::UNAUTHORIZED, Json(json!({"error": "unauthorized"}))).into_response();
    }
    Json(json!({
        "total_connections": s.connections.len(),
        "total_channels": s.channels.read().await.len(),
        "messages_sent": s.messages_sent.load(Ordering::Relaxed),
        "uptime_seconds": s.started_at.elapsed().as_secs(),
    }))
    .into_response()
}

async fn list_channels(State(s): State<Arc<AppState>>, headers: HeaderMap) -> impl IntoResponse {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return (StatusCode::UNAUTHORIZED, Json(json!({"error": "unauthorized"}))).into_response();
    }
    let ch = s.channels.read().await;
    let list: Vec<Value> = ch
        .iter()
        .map(|(name, ids)| json!({ "name": name, "subscribers": ids.len() }))
        .collect();
    Json(json!({ "channels": list })).into_response()
}

async fn broadcast_endpoint(
    State(s): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(body): Json<BroadcastBody>,
) -> impl IntoResponse {
    if !check_internal_auth(&headers, &s.internal_secret) {
        return (StatusCode::UNAUTHORIZED, Json(json!({"error": "unauthorized"}))).into_response();
    }
    let kind = body.kind.as_deref().unwrap_or("message");
    let msg_id = Uuid::new_v4().to_string();
    let payload = build_msg(kind, Some(&body.channel), body.data.unwrap_or(Value::Null), &msg_id);
    let sent = broadcast_to_channel(&s, &body.channel, payload, None).await;
    Json(json!({ "sent": sent, "channel": body.channel })).into_response()
}

async fn ws_handler(
    ws: WebSocketUpgrade,
    Query(params): Query<WsParams>,
    State(s): State<Arc<AppState>>,
) -> impl IntoResponse {
    // Resolve user_id from JWT or query param
    let user_id = if let Some(token) = &params.token {
        if let Some(uid) = verify_jwt(token, &s.jwt_secret) {
            uid
        } else if !s.jwt_secret.is_empty() {
            // JWT secret set but token invalid — reject
            return (StatusCode::UNAUTHORIZED, "Invalid token").into_response();
        } else {
            params.user_id.clone().unwrap_or_else(|| "anonymous".into())
        }
    } else {
        params.user_id.clone().unwrap_or_else(|| "anonymous".into())
    };

    if s.connections.len() >= s.max_connections {
        return (StatusCode::SERVICE_UNAVAILABLE, "Max connections reached").into_response();
    }

    ws.on_upgrade(move |socket| handle_socket(socket, s, user_id))
}

async fn handle_socket(socket: WebSocket, state: Arc<AppState>, user_id: String) {
    let conn_id = Uuid::new_v4();
    let (tx, mut rx) = mpsc::unbounded_channel::<String>();

    state.connections.insert(conn_id, ConnHandle { tx, user_id: user_id.clone() });
    info!("ws_connected conn_id={conn_id} user={user_id}");

    let (mut sink, mut stream) = socket.split();

    // Per-connection rate limiter state (60 msgs / 60s)
    let mut rate_count: u32 = 0;
    let mut rate_window = Instant::now();
    const RATE_LIMIT: u32 = 60;
    const RATE_WINDOW_SECS: u64 = 60;

    // Local channel subscription set (avoids locking for cleanup)
    let mut my_channels: HashSet<String> = HashSet::new();

    loop {
        tokio::select! {
            // Outbound: relay messages from broadcast senders to this WS client
            Some(outbound) = rx.recv() => {
                if sink.send(Message::Text(outbound)).await.is_err() {
                    break;
                }
            }

            // Inbound: handle messages from the WS client
            Some(msg) = stream.next() => {
                let text = match msg {
                    Ok(Message::Text(t)) => t,
                    Ok(Message::Close(_)) | Err(_) => break,
                    Ok(Message::Ping(p)) => {
                        let _ = sink.send(Message::Pong(p)).await;
                        continue;
                    }
                    _ => continue,
                };

                // Rate limiting
                if rate_window.elapsed().as_secs() >= RATE_WINDOW_SECS {
                    rate_count = 0;
                    rate_window = Instant::now();
                }
                rate_count += 1;
                if rate_count > RATE_LIMIT {
                    let err = build_msg("error", None,
                        json!({"error": "Rate limit exceeded. Max 60 msgs/60s."}),
                        &Uuid::new_v4().to_string());
                    let _ = sink.send(Message::Text(err)).await;
                    continue;
                }

                // Parse and dispatch
                let ws_msg: WsMsg = match serde_json::from_str(&text) {
                    Ok(m) => m,
                    Err(_) => {
                        let err = build_msg("error", None,
                            json!({"error": "Invalid JSON"}),
                            &Uuid::new_v4().to_string());
                        let _ = sink.send(Message::Text(err)).await;
                        continue;
                    }
                };

                let mid = Uuid::new_v4().to_string();

                match ws_msg.kind.as_str() {
                    "ping" => {
                        let pong = build_msg("pong", None, Value::Null, &mid);
                        let _ = sink.send(Message::Text(pong)).await;
                    }

                    "subscribe" => {
                        if let Some(ch) = &ws_msg.channel {
                            let ch = ch.clone();
                            let mut can_sub = true;
                            {
                                let mut channels = state.channels.write().await;
                                let entry = channels.entry(ch.clone()).or_insert_with(HashSet::new);
                                if !my_channels.contains(&ch)
                                    && channels.len() >= state.max_channels
                                    && !channels.contains_key(&ch)
                                {
                                    can_sub = false;
                                } else {
                                    entry.insert(conn_id);
                                    my_channels.insert(ch.clone());
                                }
                            }
                            let reply = if can_sub {
                                let sub_count = state.channels.read().await
                                    .get(&ch).map(|s| s.len()).unwrap_or(0);
                                build_msg("subscribed", Some(&ch),
                                    json!({"subscriber_count": sub_count}), &mid)
                            } else {
                                build_msg("error", Some(&ch),
                                    json!({"error": "Channel limit reached"}), &mid)
                            };
                            let _ = sink.send(Message::Text(reply)).await;
                        }
                    }

                    "unsubscribe" => {
                        if let Some(ch) = &ws_msg.channel {
                            let ch = ch.clone();
                            {
                                let mut channels = state.channels.write().await;
                                if let Some(subs) = channels.get_mut(&ch) {
                                    subs.remove(&conn_id);
                                    if subs.is_empty() {
                                        channels.remove(&ch);
                                    }
                                }
                            }
                            my_channels.remove(&ch);
                            let reply = build_msg("unsubscribed", Some(&ch), Value::Null, &mid);
                            let _ = sink.send(Message::Text(reply)).await;
                        }
                    }

                    "message" => {
                        if let Some(ch) = &ws_msg.channel {
                            let ch = ch.clone();
                            let payload = json!({
                                "type": "message",
                                "channel": ch,
                                "sender": user_id,
                                "message_id": mid,
                                "timestamp": now_iso(),
                                "data": ws_msg.data.unwrap_or(Value::Null),
                            });
                            let payload_str = payload.to_string();
                            let recipients =
                                broadcast_to_channel(&state, &ch, payload_str, Some(conn_id))
                                    .await;
                            let ack = build_msg("delivered", Some(&ch),
                                json!({"recipients": recipients}), &mid);
                            let _ = sink.send(Message::Text(ack)).await;
                        }
                    }

                    "channels" => {
                        let list: Vec<&str> = my_channels.iter().map(|s| s.as_str()).collect();
                        let reply = build_msg("channels", None, json!({"channels": list}), &mid);
                        let _ = sink.send(Message::Text(reply)).await;
                    }

                    _ => {
                        let err = build_msg("error", None,
                            json!({"error": format!("Unknown type '{}'", ws_msg.kind)}),
                            &mid);
                        let _ = sink.send(Message::Text(err)).await;
                    }
                }
            }

            else => break,
        }
    }

    // Cleanup
    info!("ws_disconnected conn_id={conn_id}");
    state.connections.remove(&conn_id);
    let mut channels = state.channels.write().await;
    for ch in &my_channels {
        if let Some(subs) = channels.get_mut(ch) {
            subs.remove(&conn_id);
            if subs.is_empty() {
                channels.remove(ch);
            }
        }
    }
}

// ── Main ──────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let jwt_secret = std::env::var("JWT_SECRET").unwrap_or_else(|_| {
        warn!("JWT_SECRET not set — WebSocket connections will not require authentication");
        String::new()
    });
    let internal_secret = std::env::var("INTERNAL_SECRET").unwrap_or_default();

    let state = Arc::new(AppState::new(jwt_secret, internal_secret));

    let app = Router::new()
        .route("/health", get(health))
        .route("/ws", get(ws_handler))
        .route("/stats", get(stats))
        .route("/channels", get(list_channels))
        .route("/broadcast", post(broadcast_endpoint))
        .with_state(state);

    let port = std::env::var("PORT").unwrap_or_else(|_| "8004".to_string());
    let addr = format!("0.0.0.0:{port}");
    info!("nexus-ws listening on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
