/******************************************************************************/
/* Tranc3 Nanoservice — Main Entry Point                                      */
/*                                                                            */
/* Tokio-based async runtime for the Tranc3 adaptive storage nanoservice.     */
/* Initializes the storage router, CRUSH engine, adaptive capacity manager,   */
/* HSM security module, and HTTP health/metrics server.                       */
/*                                                                            */
/* Entity Taxonomy: PID/AID/SID/NID                                           */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

mod adaptive;
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

use crate::adaptive::AdaptiveCapacityManager;
use crate::crush::CRUSHEngine;
use crate::storage::StorageRouter;

/******************************************************************************/
/* Application State                                                          */
/******************************************************************************/

struct AppState {
    storage_router: Arc<StorageRouter>,
    crush_engine: Arc<CRUSHEngine>,
    adaptive_manager: Arc<AdaptiveCapacityManager>,
    registry: Arc<Registry>,
}

/******************************************************************************/
/* Body Type Alias                                                            */
/*                                                                            */
/* In hyper 1.x, Response<B> requires B: Body. bytes::Bytes does not         */
/* implement Body. We use http_body_util::Full<Bytes> which does.            */
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

    // ── Metrics Registry ──────────────────────────────────────────────────
    let registry = Arc::new(Registry::new());
    info!("Prometheus metrics registry initialized");

    // ── Application State ─────────────────────────────────────────────────
    let state = Arc::new(AppState {
        storage_router,
        crush_engine,
        adaptive_manager,
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

        // ── 404 ────────────────────────────────────────────────────────────
        _ => Ok(Response::builder()
            .status(404)
            .body(full("not found"))
            .unwrap()),
    }
}
