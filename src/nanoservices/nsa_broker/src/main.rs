//! NSA — Nanoservice Architecture Broker
//! =======================================
//! State-containerized nanoservices sharing memory via high-speed IPC
//! (Inter-Process Communication) rather than network calls, reducing
//! latency to near-zero.
//!
//! Architecture:
//!   - Shared memory segments (/dev/shm/nsa_*) for zero-copy messaging
//!   - Atomic flags for lock-free signalling between services
//!   - Ring buffer pattern for high-throughput message passing
//!   - Service registry for discovery and health monitoring
//!   - HTTP management endpoint for observability

use std::fs::OpenOptions;
use std::io;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::Duration;

use chrono::Utc;
use dashmap::DashMap;
use memmap2::{MmapMut, MmapOptions};
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use tracing::{error, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const SHM_DIR: &str = "/dev/shm";
const SHM_PREFIX: &str = "nsa_";
const DEFAULT_SEGMENT_SIZE: usize = 65536; // 64KB per segment
const MAX_SEGMENTS: usize = 256;
const RING_BUFFER_SLOTS: usize = 64;
const SLOT_SIZE: usize = 1024; // 1KB per slot
const POLL_INTERVAL_US: u64 = 100; // 100μs cooperative poll
const HTTP_PORT: u16 = 7780;

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

/// Unique identifier for a nanoservice
#[derive(Debug, Clone, Serialize, Deserialize, Hash, Eq, PartialEq)]
pub struct ServiceId(String);

impl ServiceId {
    pub fn new(name: &str) -> Self {
        Self(format!("NSA-{}", name.to_uppercase().replace('-', "_")))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Nanoservice registration record
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NanoserviceRecord {
    pub id: ServiceId,
    pub name: String,
    pub tier: u8,
    pub pid: u32,
    pub shm_segment: String,
    pub registered_at: String,
    pub last_heartbeat: String,
    pub status: ServiceStatus,
    pub message_count: u64,
    pub error_count: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ServiceStatus {
    Starting,
    Ready,
    Busy,
    Degraded,
    Offline,
}

/// Message envelope for IPC communication
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IpcMessage {
    pub id: String,
    pub source: ServiceId,
    pub target: ServiceId,
    pub msg_type: String,
    pub payload: String,
    pub timestamp: String,
    pub priority: u8, // 0=highest, 255=lowest
    pub ttl_ms: u64,
}

impl IpcMessage {
    pub fn new(source: ServiceId, target: ServiceId, msg_type: &str, payload: &str) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            source,
            target,
            msg_type: msg_type.to_string(),
            payload: payload.to_string(),
            timestamp: Utc::now().to_rfc3339(),
            priority: 128,
            ttl_ms: 30000, // 30s default
        }
    }
}

/// Ring buffer slot header (lives in shared memory)
#[repr(C)]
struct SlotHeader {
    occupied: AtomicBool,
    sequence: AtomicU64,
    length: u32,
    _padding: u32,
}

const SLOT_HEADER_SIZE: usize = std::mem::size_of::<SlotHeader>();

// ─────────────────────────────────────────────────────────────────────────────
// Shared Memory Segment Manager
// ─────────────────────────────────────────────────────────────────────────────

/// Manages a shared memory segment with ring buffer semantics
pub struct ShmSegment {
    name: String,
    mmap: MmapMut,
    slot_count: usize,
}

impl ShmSegment {
    /// Create or open a shared memory segment
    pub fn create(name: &str, slot_count: usize) -> io::Result<Self> {
        let shm_path = format!("{}/{}{}", SHM_DIR, SHM_PREFIX, name);
        let total_size = slot_count * (SLOT_HEADER_SIZE + SLOT_SIZE);

        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(&shm_path)?;

        file.set_len(total_size as u64)?;

        let mmap = unsafe { MmapOptions::new().map_mut(&file)? };

        // Initialize all slot headers as unoccupied
        let segment = Self {
            name: name.to_string(),
            mmap,
            slot_count,
        };
        segment.initialize_slots();

        info!("Created SHM segment: {} ({} slots, {} bytes)", shm_path, slot_count, total_size);
        Ok(segment)
    }

    fn initialize_slots(&self) {
        for i in 0..self.slot_count {
            let offset = i * (SLOT_HEADER_SIZE + SLOT_SIZE);
            let header = self.slot_header(i);
            header.occupied.store(false, Ordering::Release);
            header.sequence.store(0, Ordering::Release);
            header.length = 0;
        }
    }

    fn slot_offset(&self, index: usize) -> usize {
        index * (SLOT_HEADER_SIZE + SLOT_SIZE)
    }

    fn slot_header(&self, index: usize) -> &SlotHeader {
        let offset = self.slot_offset(index);
        unsafe { &*(self.mmap.as_ptr().add(offset) as *const SlotHeader) }
    }

    /// Write a message to the next available slot
    pub fn write_message(&self, msg: &IpcMessage) -> io::Result<usize> {
        let encoded = serde_json::to_vec(msg)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        if encoded.len() > SLOT_SIZE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("Message too large: {} bytes (max {})", encoded.len(), SLOT_SIZE),
            ));
        }

        // Find an unoccupied slot
        for i in 0..self.slot_count {
            let offset = self.slot_offset(i);
            let header = unsafe {
                &*(self.mmap.as_ptr().add(offset) as *const SlotHeader)
            };

            if !header.occupied.load(Ordering::Acquire) {
                // Write header
                let seq = header.sequence.fetch_add(1, Ordering::AcqRel);
                header.length = encoded.len() as u32;
                header.occupied.store(true, Ordering::Release);

                // Write payload (after header)
                let payload_offset = offset + SLOT_HEADER_SIZE;
                unsafe {
                    let dst = self.mmap.as_ptr().add(payload_offset) as *mut u8;
                    std::ptr::copy_nonoverlapping(encoded.as_ptr(), dst, encoded.len());
                }

                return Ok(i);
            }
        }

        Err(io::Error::new(io::ErrorKind::WouldBlock, "All slots occupied"))
    }

    /// Read and consume a message from a specific slot
    pub fn read_message(&self, slot_index: usize) -> io::Result<Option<IpcMessage>> {
        if slot_index >= self.slot_count {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "Slot index out of range"));
        }

        let offset = self.slot_offset(slot_index);
        let header = unsafe {
            &*(self.mmap.as_ptr().add(offset) as *const SlotHeader)
        };

        if !header.occupied.load(Ordering::Acquire) {
            return Ok(None);
        }

        let length = header.length as usize;
        if length == 0 || length > SLOT_SIZE {
            return Ok(None);
        }

        let payload_offset = offset + SLOT_HEADER_SIZE;
        let mut buf = vec![0u8; length];
        unsafe {
            let src = self.mmap.as_ptr().add(payload_offset);
            std::ptr::copy_nonoverlapping(src, buf.as_mut_ptr(), length);
        }

        // Mark slot as available
        header.occupied.store(false, Ordering::Release);

        let msg: IpcMessage = serde_json::from_slice(&buf)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        Ok(Some(msg))
    }

    /// Get the number of occupied slots
    pub fn occupied_count(&self) -> usize {
        (0..self.slot_count)
            .filter(|&i| self.slot_header(i).occupied.load(Ordering::Acquire))
            .count()
    }

    pub fn name(&self) -> &str { &self.name }
    pub fn slot_count(&self) -> usize { self.slot_count }
}

// ─────────────────────────────────────────────────────────────────────────────
// NSA Broker — Core
// ─────────────────────────────────────────────────────────────────────────────

pub struct NsaBroker {
    segments: DashMap<String, ShmSegment>,
    registry: DashMap<ServiceId, NanoserviceRecord>,
    stats: Mutex<BrokerStats>,
}

#[derive(Debug, Default)]
struct BrokerStats {
    total_messages_routed: u64,
    total_errors: u64,
    segments_created: u64,
    services_registered: u64,
}

impl NsaBroker {
    pub fn new() -> Self {
        Self {
            segments: DashMap::new(),
            registry: DashMap::new(),
            stats: Mutex::new(BrokerStats::default()),
        }
    }

    /// Register a new nanoservice and allocate its SHM segment
    pub fn register_service(
        &self,
        name: &str,
        tier: u8,
        pid: u32,
    ) -> io::Result<ServiceId> {
        let id = ServiceId::new(name);
        let segment_name = format!("{}_seg", name.to_lowercase().replace('-', "_"));

        // Create dedicated SHM segment for this service
        let segment = ShmSegment::create(&segment_name, RING_BUFFER_SLOTS)?;

        let record = NanoserviceRecord {
            id: id.clone(),
            name: name.to_string(),
            tier,
            pid,
            shm_segment: segment_name.clone(),
            registered_at: Utc::now().to_rfc3339(),
            last_heartbeat: Utc::now().to_rfc3339(),
            status: ServiceStatus::Ready,
            message_count: 0,
            error_count: 0,
        };

        self.segments.insert(segment_name, segment);
        self.registry.insert(id.clone(), record);

        let mut stats = self.stats.lock();
        stats.segments_created += 1;
        stats.services_registered += 1;

        info!("Registered nanoservice: {} (tier={}, pid={})", id.as_str(), tier, pid);
        Ok(id)
    }

    /// Send a message from one service to another via shared memory
    pub fn send_message(&self, msg: &IpcMessage) -> io::Result<()> {
        // Find the target service's segment
        let target = self.registry.get(&msg.target);
        if target.is_none() {
            warn!("Target service not found: {}", msg.target.as_str());
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("Service {} not registered", msg.target.as_str()),
            ));
        }

        let target = target.unwrap();
        let segment_name = &target.shm_segment;

        let segment = self.segments.get(segment_name);
        if segment.is_none() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("SHM segment {} not found", segment_name),
            ));
        }

        let segment = segment.unwrap();
        segment.write_message(msg)?;

        let mut stats = self.stats.lock();
        stats.total_messages_routed += 1;

        Ok(())
    }

    /// Read the next message from a service's segment
    pub fn read_message(&self, service_id: &ServiceId) -> io::Result<Option<IpcMessage>> {
        let target = self.registry.get(service_id);
        if target.is_none() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("Service {} not registered", service_id.as_str()),
            ));
        }

        let segment_name = &target.unwrap().shm_segment;
        let segment = self.segments.get(segment_name);
        if segment.is_none() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("SHM segment {} not found", segment_name),
            ));
        }

        let segment = segment.unwrap();
        // Scan for the first occupied slot
        for i in 0..segment.slot_count() {
            if let Some(msg) = segment.read_message(i)? {
                return Ok(Some(msg));
            }
        }
        Ok(None)
    }

    /// Update heartbeat for a service
    pub fn heartbeat(&self, service_id: &ServiceId) -> io::Result<()> {
        let mut record = self.registry.get_mut(service_id).ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotFound, "Service not found")
        })?;
        record.last_heartbeat = Utc::now().to_rfc3339();
        record.status = ServiceStatus::Ready;
        Ok(())
    }

    /// Get all registered services
    pub fn list_services(&self) -> Vec<NanoserviceRecord> {
        self.registry.iter().map(|r| r.value().clone()).collect()
    }

    /// Get broker statistics
    pub fn get_stats(&self) -> BrokerStats {
        self.stats.lock().clone()
    }

    /// Health check — verify all segments are accessible
    pub fn health_check(&self) -> bool {
        self.segments.iter().all(|s| s.value().occupied_count() < s.value().slot_count())
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// HTTP Management Endpoint
// ─────────────────────────────────────────────────────────────────────────────

async fn serve_http(broker: &NsaBroker) -> io::Result<()> {
    use http_body_util::Full;
    use hyper::body::Bytes;
    use hyper::server::conn::http1;
    use hyper::service::service_fn;
    use hyper::{Request, Response};
    use std::convert::Infallible;
    use std::net::SocketAddr;

    let addr = SocketAddr::from(([0, 0, 0, 0], HTTP_PORT));
    let listener = hyper::util::rt::TokioTcpListener::bind(addr).await?;

    info!("NSA Broker HTTP endpoint listening on {}", addr);

    loop {
        let (stream, _) = listener.accept().await?;
        let broker_services = broker.list_services();
        let broker_stats = broker.get_stats();
        let broker_healthy = broker.health_check();

        let service = service_fn(move |req: Request<hyper::body::Incoming>| {
            let services = broker_services.clone();
            let stats = broker_stats.clone();
            let healthy = broker_healthy;

            async move {
                let path = req.uri().path();
                let response = match path {
                    "/health" => {
                        let body = serde_json::json!({
                            "status": if healthy { "healthy" } else { "degraded" },
                            "timestamp": Utc::now().to_rfc3339(),
                        });
                        Response::builder()
                            .status(if healthy { 200 } else { 503 })
                            .header("content-type", "application/json")
                            .body(Full::new(Bytes::from(serde_json::to_vec(&body).unwrap())))
                            .unwrap()
                    }
                    "/services" => {
                        let body = serde_json::json!({
                            "services": services,
                            "count": services.len(),
                        });
                        Response::builder()
                            .status(200)
                            .header("content-type", "application/json")
                            .body(Full::new(Bytes::from(serde_json::to_vec(&body).unwrap())))
                            .unwrap()
                    }
                    "/stats" => {
                        let body = serde_json::json!({
                            "messages_routed": stats.total_messages_routed,
                            "total_errors": stats.total_errors,
                            "segments_created": stats.segments_created,
                            "services_registered": stats.services_registered,
                        });
                        Response::builder()
                            .status(200)
                            .header("content-type", "application/json")
                            .body(Full::new(Bytes::from(serde_json::to_vec(&body).unwrap())))
                            .unwrap()
                    }
                    _ => Response::builder()
                        .status(404)
                        .body(Full::new(Bytes::from("Not Found")))
                        .unwrap(),
                };
                Ok::<_, Infallible>(response)
            }
        });

        tokio::spawn(async move {
            if let Err(err) = http1::Builder::new()
                .serve_connection(stream, service)
                .await
            {
                error!("HTTP connection error: {:?}", err);
            }
        });
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> io::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter("nsa_broker=info")
        .init();

    info!("╔══════════════════════════════════════════════════╗");
    info!("║  NSA Broker — Nanoservice Architecture          ║");
    info!("║  Shared Memory IPC / Zero-Copy Messaging        ║");
    info!("╚══════════════════════════════════════════════════╝");

    let broker = NsaBroker::new();

    // Register built-in services
    broker.register_service("sentinel_station", 1, std::process::id())?;
    broker.register_service("infinity_bridge", 3, std::process::id())?;
    broker.register_service("nexus_bridge", 4, std::process::id())?;
    broker.register_service("hive_bridge", 5, std::process::id())?;

    info!("Built-in services registered. Starting HTTP endpoint...");

    serve_http(&broker).await
}
