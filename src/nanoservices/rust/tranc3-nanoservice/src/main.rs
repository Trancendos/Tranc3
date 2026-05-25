/******************************************************************************/
/* Tranc3 Nanoservice — Main Entry Point                                      */
/*                                                                            */
/* Tokio-based async runtime for the Tranc3 adaptive storage nanoservice.     */
/* Initializes the storage router, CRUSH engine, adaptive capacity manager,   */
/* HSM security module, HTTP health/metrics server, and ecosystem protocols   */
/* (A2A relay, Three-Bridge routing, Sentinel Station health).                */
/*                                                                            */
/* Entity Taxonomy: PID/AID/SID/NID                                           */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

mod a2a;
mod adaptive;
mod bridge;
mod crush;
mod hsm;
mod storage;

use std::net::SocketAddr;
use std::sync::Arc;

use http_body_util::BodyExt;
use http_body_util::Full;
use hyper::body::Bytes;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Request, Response};
use hyper_util::rt::TokioIo;
use prometheus::{Encoder, Registry, TextEncoder};
use tokio::net::TcpListener;
use tracing::{error, info};

use crate::a2a::A2ARouter;
use crate::adaptive::AdaptiveCapacityManager;
use crate::bridge::SentinelStation;
use crate::crush::CRUSHEngine;
use crate::storage::StorageRouter;

/******************************************************************************/
/* Application State                                                          */
/******************************************************************************/

struct AppState {
    storage_router: Arc<StorageRouter>,
    crush_engine: Arc<CRUSHEngine>,
    adaptive_manager: Arc<AdaptiveCapacityManager>,
    a2a_router: Arc<A2ARouter>,
    sentinel_station: Arc<SentinelStation>,
    registry: Arc<Registry>,
}

/******************************************************************************/
/* Body Type Alias                                                            */
/******************************************************************************/

type BoxBody = Full<Bytes>;

fn full<T: Into<Bytes>>(chunk: T) -> BoxBody {
    Full::new(chunk.into())
}

/******************************************************************************/
/* Main                                                                       */
/******************************************************************************/

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // ── Logging ──────────────────────────────────────────────────────────
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("tranc3_nanoservice=info,warn"));

    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .init();

    info!("Tranc3 Nanoservice starting...");
    info!(
        "System Mode: {}",
        std::env::var("TRANC3_SYSTEM_MODE").unwrap_or_else(|_| "HYBRID".into())
    );

    // ── CRUSH Engine ──────────────────────────────────────────────────────
    let crush_engine = Arc::new(CRUSHEngine::new());
    info!("CRUSH engine initialized");

    // ── Storage Router ────────────────────────────────────────────────────
    let storage_router = Arc::new(StorageRouter::new(
        vec![
            "oci".to_string(),
            "cloudflare_r2".to_string(),
            "minio".to_string(),
            "ceph_rgw".to_string(),
        ],
        crush_engine.clone(),
    ));
    info!("Storage router initialized with fallback chain");

    // ── Adaptive Capacity Manager ─────────────────────────────────────────
    let adaptive_manager = Arc::new(AdaptiveCapacityManager::new(
        storage_router.clone(),
        crush_engine.clone(),
    ));
    info!("Adaptive capacity manager initialized");

    // ── A2A Router ────────────────────────────────────────────────────────
    let a2a_router = Arc::new(A2ARouter::new());
    info!("A2A router initialized");

    // ── Sentinel Station (Three-Bridge Coordinator) ──────────────────────
    let sentinel_station = Arc::new(SentinelStation::new());
    info!("Sentinel Station initialized — Three-Bridge architecture active");

    // ── Metrics Registry ──────────────────────────────────────────────────
    let registry = Arc::new(Registry::new());
    info!("Prometheus metrics registry initialized");

    // ── Application State ─────────────────────────────────────────────────
    let state = Arc::new(AppState {
        storage_router,
        crush_engine,
        adaptive_manager,
        a2a_router,
        sentinel_station,
        registry,
    });

    // ── HTTP Server ───────────────────────────────────────────────────────
    let listen_addr: SocketAddr = std::env::var("NANO_LISTEN_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:8080".into())
        .parse()
        .unwrap_or_else(|_| "0.0.0.0:8080".parse().unwrap());

    info!("Binding HTTP server to {}", listen_addr);

    let listener = TcpListener::bind(listen_addr).await?;

    info!("Tranc3 Nanoservice ready — listening on {}", listen_addr);

    loop {
        let (stream, remote_addr) = listener.accept().await?;
        let state = state.clone();

        tokio::spawn(async move {
            let io = TokioIo::new(stream);
            let service = service_fn(move |req: Request<hyper::body::Incoming>| {
                let state = state.clone();
                async move { handle_request(req, &state).await }
            });

            if let Err(err) = http1::Builder::new().serve_connection(io, service).await {
                error!("Error serving connection from {}: {}", remote_addr, err);
            }
        });
    }
}

/******************************************************************************/
/* HTTP Request Handler                                                       */
/******************************************************************************/

async fn handle_request(
    req: Request<hyper::body::Incoming>,
    state: &AppState,
) -> Result<Response<BoxBody>, hyper::Error> {
    let path = req.uri().path().to_string();
    let method = req.method().clone();

    match (method.as_str(), path.as_str()) {
        // ── Health Check ──────────────────────────────────────────────────
        ("GET", "/healthz") => Ok(Response::builder()
            .status(200)
            .header("Content-Type", "text/plain")
            .body(full("ok"))
            .unwrap()),

        // ── Readiness Check ───────────────────────────────────────────────
        ("GET", "/readyz") => {
            let ready = state.storage_router.is_ready();
            if ready {
                Ok(Response::builder()
                    .status(200)
                    .header("Content-Type", "text/plain")
                    .body(full("ready"))
                    .unwrap())
            } else {
                Ok(Response::builder()
                    .status(503)
                    .header("Content-Type", "text/plain")
                    .body(full("not ready"))
                    .unwrap())
            }
        }

        // ── Metrics ───────────────────────────────────────────────────────
        ("GET", "/metrics") => {
            let encoder = TextEncoder::new();
            let metric_families = state.registry.gather();
            let mut buffer = Vec::new();
            encoder.encode(&metric_families, &mut buffer).unwrap();
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "text/plain; version=0.0.4")
                .body(full(buffer))
                .unwrap())
        }

        // ── Adaptive Write ────────────────────────────────────────────────
        ("PUT", path) if path.starts_with("/v1/write/") => {
            let object_path = path.trim_start_matches("/v1/write/");
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match state.storage_router.adaptive_write(object_path, body).await {
                Ok(result) => Ok(Response::builder()
                    .status(200)
                    .header("Content-Type", "application/json")
                    .body(full(serde_json::to_string(&result).unwrap_or_default()))
                    .unwrap()),
                Err(e) => {
                    error!("Write error: {:?}", e);
                    Ok(Response::builder()
                        .status(500)
                        .body(full(format!("write error: {:?}", e)))
                        .unwrap())
                }
            }
        }

        // ── Adaptive Read ─────────────────────────────────────────────────
        ("GET", path) if path.starts_with("/v1/read/") => {
            let object_path = path.trim_start_matches("/v1/read/");
            match state.storage_router.adaptive_read(object_path).await {
                Ok(data) => Ok(Response::builder()
                    .status(200)
                    .header("Content-Type", "application/octet-stream")
                    .body(full(data))
                    .unwrap()),
                Err(e) => {
                    error!("Read error: {:?}", e);
                    Ok(Response::builder()
                        .status(404)
                        .body(full(format!("read error: {:?}", e)))
                        .unwrap())
                }
            }
        }

        // ── CRUSH Map Info ────────────────────────────────────────────────
        ("GET", "/v1/crush/map") => {
            let map_info = state.crush_engine.map_summary();
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "application/json")
                .body(full(serde_json::to_string_pretty(&map_info).unwrap_or_default()))
                .unwrap())
        }

        // ── Capacity Status ───────────────────────────────────────────────
        ("GET", "/v1/capacity") => {
            let cap = state.adaptive_manager.capacity_summary();
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "application/json")
                .body(full(serde_json::to_string_pretty(&cap).unwrap_or_default()))
                .unwrap())
        }

        // ── Fallback Chain Status ─────────────────────────────────────────
        ("GET", "/v1/fallback/status") => {
            let status = state.storage_router.fallback_status();
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "application/json")
                .body(full(serde_json::to_string_pretty(&status).unwrap_or_default()))
                .unwrap())
        }

        // ── A2A: Relay Message ────────────────────────────────────────────
        ("POST", "/v1/a2a/relay") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<crate::a2a::A2AMessage>(&body) {
                Ok(message) => {
                    match state.a2a_router.relay_message(message).await {
                        Ok(response) => Ok(Response::builder()
                            .status(200)
                            .header("Content-Type", "application/json")
                            .body(full(serde_json::to_string_pretty(&response).unwrap_or_default()))
                            .unwrap()),
                        Err(e) => Ok(Response::builder()
                            .status(503)
                            .header("Content-Type", "application/json")
                            .body(full(serde_json::to_string_pretty(&serde_json::json!({
                                "error": e,
                            })).unwrap_or_default()))
                            .unwrap()),
                    }
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .header("Content-Type", "application/json")
                    .body(full(serde_json::to_string_pretty(&serde_json::json!({
                        "error": format!("Invalid A2A message: {}", e),
                    })).unwrap_or_default()))
                    .unwrap()),
            }
        }

        // ── A2A: Register Agent ──────────────────────────────────────────
        ("POST", "/v1/a2a/register") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<crate::a2a::AgentCard>(&body) {
                Ok(card) => {
                    state.a2a_router.register_agent(card).await;
                    Ok(Response::builder()
                        .status(201)
                        .header("Content-Type", "application/json")
                        .body(full("{\"status\":\"registered\"}"))
                        .unwrap())
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .header("Content-Type", "application/json")
                    .body(full(serde_json::to_string_pretty(&serde_json::json!({
                        "error": format!("Invalid agent card: {}", e),
                    })).unwrap_or_default()))
                    .unwrap()),
            }
        }

        // ── A2A: Broadcast ────────────────────────────────────────────────
        ("POST", "/v1/a2a/broadcast") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<serde_json::Value>(&body) {
                Ok(payload) => {
                    let sender = payload.get("sender").and_then(|v| v.as_str()).unwrap_or("unknown");
                    let skill = payload.get("skill").and_then(|v| v.as_str());
                    let tier = payload.get("tier").and_then(|v| v.as_u64()).map(|t| t as u8);
                    let broadcast_payload = payload.get("payload").cloned().unwrap_or(serde_json::json!({}));
                    let responses = state.a2a_router.broadcast(sender, skill, tier, broadcast_payload).await;
                    Ok(Response::builder()
                        .status(200)
                        .header("Content-Type", "application/json")
                        .body(full(serde_json::to_string_pretty(&responses).unwrap_or_default()))
                        .unwrap())
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .header("Content-Type", "application/json")
                    .body(full(format!("Invalid broadcast payload: {}", e)))
                    .unwrap()),
            }
        }

        // ── A2A: Health / Status ──────────────────────────────────────────
        ("GET", "/v1/a2a/health") => {
            let health = state.a2a_router.health_check().await;
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "application/json")
                .body(full(serde_json::to_string_pretty(&health).unwrap_or_default()))
                .unwrap())
        }

        // ── Three-Bridge: Route Traffic ───────────────────────────────────
        ("POST", "/v1/bridge/route") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<crate::bridge::BridgeTrafficPacket>(&body) {
                Ok(packet) => {
                    match state.sentinel_station.route_traffic(packet).await {
                        Ok(result) => Ok(Response::builder()
                            .status(200)
                            .header("Content-Type", "application/json")
                            .body(full(serde_json::to_string_pretty(&result).unwrap_or_default()))
                            .unwrap()),
                        Err(e) => Ok(Response::builder()
                            .status(503)
                            .header("Content-Type", "application/json")
                            .body(full(serde_json::to_string_pretty(&serde_json::json!({
                                "error": e,
                            })).unwrap_or_default()))
                            .unwrap()),
                    }
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .header("Content-Type", "application/json")
                    .body(full(serde_json::to_string_pretty(&serde_json::json!({
                        "error": format!("Invalid traffic packet: {}", e),
                    })).unwrap_or_default()))
                    .unwrap()),
            }
        }

        // ── Three-Bridge: Classify Traffic ────────────────────────────────
        ("POST", "/v1/bridge/classify") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<serde_json::Value>(&body) {
                Ok(payload) => {
                    let traffic_class_str = payload.get("traffic_class")
                        .and_then(|v| v.as_str())
                        .unwrap_or("user_request");
                    // Attempt to parse the traffic class
                    let result = match traffic_class_str {
                        "user_request" => Some(crate::bridge::TrafficClass::UserRequest),
                        "user_auth" => Some(crate::bridge::TrafficClass::UserAuth),
                        "user_dashboard" => Some(crate::bridge::TrafficClass::UserDashboard),
                        "agent_request" => Some(crate::bridge::TrafficClass::AgentRequest),
                        "agent_broadcast" => Some(crate::bridge::TrafficClass::AgentBroadcast),
                        "agent_discovery" => Some(crate::bridge::TrafficClass::AgentDiscovery),
                        "bot_delegation" => Some(crate::bridge::TrafficClass::BotDelegation),
                        "a2a_message" => Some(crate::bridge::TrafficClass::A2AMessage),
                        "data_queue" => Some(crate::bridge::TrafficClass::DataQueue),
                        "data_transport" => Some(crate::bridge::TrafficClass::DataTransport),
                        "swarm_dispatch" => Some(crate::bridge::TrafficClass::SwarmDispatch),
                        "swarm_consensus" => Some(crate::bridge::TrafficClass::SwarmConsensus),
                        "estate_scan" => Some(crate::bridge::TrafficClass::EstateScan),
                        "escalation" => Some(crate::bridge::TrafficClass::Escalation),
                        _ => None,
                    };

                    match result {
                        Some(tc) => {
                            let bridge = state.sentinel_station.classify_traffic(&tc);
                            Ok(Response::builder()
                                .status(200)
                                .header("Content-Type", "application/json")
                                .body(full(serde_json::to_string_pretty(&serde_json::json!({
                                    "traffic_class": traffic_class_str,
                                    "target_bridge": format!("{}", bridge),
                                })).unwrap_or_default()))
                                .unwrap())
                        }
                        None => Ok(Response::builder()
                            .status(400)
                            .header("Content-Type", "application/json")
                            .body(full(format!("Unknown traffic class: {}", traffic_class_str)))
                            .unwrap()),
                    }
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .body(full(format!("Invalid JSON: {}", e)))
                    .unwrap()),
            }
        }

        // ── Sentinel Station: Health Aggregation ──────────────────────────
        ("GET", "/v1/sentinel/health") => {
            let health = state.sentinel_station.aggregate_health();
            Ok(Response::builder()
                .status(200)
                .header("Content-Type", "application/json")
                .body(full(serde_json::to_string_pretty(&health).unwrap_or_default()))
                .unwrap())
        }

        // ── Sentinel Station: Add Routing Rule ────────────────────────────
        ("POST", "/v1/sentinel/routing-rule") => {
            let body = req.into_body()
                .collect()
                .await?
                .to_bytes();
            match serde_json::from_slice::<crate::bridge::RoutingRule>(&body) {
                Ok(rule) => {
                    state.sentinel_station.add_routing_rule(rule).await;
                    Ok(Response::builder()
                        .status(201)
                        .header("Content-Type", "application/json")
                        .body(full("{\"status\":\"rule_added\"}"))
                        .unwrap())
                }
                Err(e) => Ok(Response::builder()
                    .status(400)
                    .header("Content-Type", "application/json")
                    .body(full(serde_json::to_string_pretty(&serde_json::json!({
                        "error": format!("Invalid routing rule: {}", e),
                    })).unwrap_or_default()))
                    .unwrap()),
            }
        }

        // ── 404 ────────────────────────────────────────────────────────────
        _ => Ok(Response::builder()
            .status(404)
            .body(full("not found"))
            .unwrap()),
    }
}
