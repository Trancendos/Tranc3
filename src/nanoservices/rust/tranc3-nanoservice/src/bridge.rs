/******************************************************************************/
/* Tranc3 Ecosystem — Three-Bridge Coordinator & Sentinel Station             */
/*                                                                            */
/* Implements the Three-Bridge architecture for the Rust nanoservice:         */
/*   - InfinityBridge: User/human traffic (requests, auth, dashboard)         */
/*   - NexusBridge: AI/Agent/Bot traffic (inter-entity communication)         */
/*   - HIVEBridge: Data movement/swarm coordination                          */
/* All bridges are managed by the Sentinel Station which handles routing,     */
/* health aggregation, and cross-bridge escalation.                           */
/*                                                                            */
/* Entity Taxonomy: PID/AID/SID/NID                                           */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

/******************************************************************************/
/* Bridge Domain & Status                                                     */
/******************************************************************************/

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BridgeDomain {
    Infinity,
    Nexus,
    Hive,
}

impl std::fmt::Display for BridgeDomain {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BridgeDomain::Infinity => write!(f, "infinity"),
            BridgeDomain::Nexus => write!(f, "nexus"),
            BridgeDomain::Hive => write!(f, "hive"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BridgeStatus {
    Active,
    Degraded,
    Offline,
    Maintenance,
}

/******************************************************************************/
/* Traffic Classification                                                     */
/******************************************************************************/

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TrafficClass {
    // Infinity Bridge
    UserRequest,
    UserAuth,
    UserDashboard,
    // Nexus Bridge
    AgentRequest,
    AgentBroadcast,
    AgentDiscovery,
    BotDelegation,
    A2AMessage,
    // HIVE Bridge
    DataQueue,
    DataTransport,
    SwarmDispatch,
    SwarmConsensus,
    EstateScan,
    // Cross-bridge
    Escalation,
}

/// Maps each TrafficClass to its BridgeDomain
fn traffic_to_bridge(tc: &TrafficClass) -> BridgeDomain {
    match tc {
        TrafficClass::UserRequest | TrafficClass::UserAuth | TrafficClass::UserDashboard => {
            BridgeDomain::Infinity
        }
        TrafficClass::AgentRequest
        | TrafficClass::AgentBroadcast
        | TrafficClass::AgentDiscovery
        | TrafficClass::BotDelegation
        | TrafficClass::A2AMessage => BridgeDomain::Nexus,
        TrafficClass::DataQueue
        | TrafficClass::DataTransport
        | TrafficClass::SwarmDispatch
        | TrafficClass::SwarmConsensus
        | TrafficClass::EstateScan => BridgeDomain::Hive,
        TrafficClass::Escalation => BridgeDomain::Infinity,
    }
}

/******************************************************************************/
/* Bridge Traffic Packet                                                      */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeTrafficPacket {
    pub id: String,
    pub traffic_class: TrafficClass,
    pub target_bridge: BridgeDomain,
    pub source: String,
    pub destination: Option<String>,
    pub payload: serde_json::Value,
    pub priority: u8,
    pub requires_escalation: bool,
    pub timestamp: String,
}

/******************************************************************************/
/* Bridge Health Report                                                       */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeHealthReport {
    pub domain: BridgeDomain,
    pub status: BridgeStatus,
    pub packets_processed: u64,
    pub packets_failed: u64,
    pub active_sessions: usize,
    pub uptime_seconds: f64,
}

/******************************************************************************/
/* Infinity Bridge — User/Human Traffic                                       */
/******************************************************************************/

pub struct InfinityBridge {
    status: RwLock<BridgeStatus>,
    packets_processed: RwLock<u64>,
    packets_failed: RwLock<u64>,
    active_sessions: RwLock<HashMap<String, Instant>>,
    started_at: Instant,
}

impl InfinityBridge {
    pub fn new() -> Self {
        Self {
            status: RwLock::new(BridgeStatus::Active),
            packets_processed: RwLock::new(0),
            packets_failed: RwLock::new(0),
            active_sessions: RwLock::new(HashMap::new()),
            started_at: Instant::now(),
        }
    }

    pub async fn process_packet(&self, packet: &BridgeTrafficPacket) -> Result<serde_json::Value, String> {
        match packet.traffic_class {
            TrafficClass::UserRequest | TrafficClass::UserAuth | TrafficClass::UserDashboard => {
                *self.packets_processed.write().await += 1;
                self.active_sessions
                    .write()
                    .await
                    .insert(packet.source.clone(), Instant::now());
                Ok(serde_json::json!({
                    "bridge": "infinity",
                    "action": format!("{:?}", packet.traffic_class),
                    "source": packet.source,
                    "status": "processed",
                }))
            }
            TrafficClass::Escalation => {
                *self.packets_processed.write().await += 1;
                Ok(serde_json::json!({
                    "bridge": "infinity",
                    "action": "escalation",
                    "source": packet.source,
                    "status": "escalated_to_human",
                }))
            }
            _ => {
                *self.packets_failed.write().await += 1;
                Err(format!("InfinityBridge cannot handle traffic class: {:?}", packet.traffic_class))
            }
        }
    }

    pub fn health_check_sync(&self) -> BridgeHealthReport {
        let status = *self.status.blocking_read();
        let processed = *self.packets_processed.blocking_read();
        let failed = *self.packets_failed.blocking_read();
        let sessions = self.active_sessions.blocking_read().len();
        BridgeHealthReport {
            domain: BridgeDomain::Infinity,
            status,
            packets_processed: processed,
            packets_failed: failed,
            active_sessions: sessions,
            uptime_seconds: self.started_at.elapsed().as_secs_f64(),
        }
    }
}

/******************************************************************************/
/* Nexus Bridge — AI/Agent/Bot Traffic                                        */
/******************************************************************************/

pub struct NexusBridge {
    status: RwLock<BridgeStatus>,
    packets_processed: RwLock<u64>,
    packets_failed: RwLock<u64>,
    channels: RwLock<HashMap<String, Vec<String>>>,
    discovered_agents: RwLock<HashMap<String, Instant>>,
    started_at: Instant,
}

impl NexusBridge {
    pub fn new() -> Self {
        Self {
            status: RwLock::new(BridgeStatus::Active),
            packets_processed: RwLock::new(0),
            packets_failed: RwLock::new(0),
            channels: RwLock::new(HashMap::new()),
            discovered_agents: RwLock::new(HashMap::new()),
            started_at: Instant::now(),
        }
    }

    pub async fn process_packet(&self, packet: &BridgeTrafficPacket) -> Result<serde_json::Value, String> {
        match packet.traffic_class {
            TrafficClass::AgentRequest
            | TrafficClass::AgentBroadcast
            | TrafficClass::AgentDiscovery
            | TrafficClass::BotDelegation
            | TrafficClass::A2AMessage => {
                *self.packets_processed.write().await += 1;
                self.discovered_agents
                    .write()
                    .await
                    .insert(packet.source.clone(), Instant::now());
                Ok(serde_json::json!({
                    "bridge": "nexus",
                    "action": format!("{:?}", packet.traffic_class),
                    "source": packet.source,
                    "destination": packet.destination,
                    "status": "processed",
                }))
            }
            _ => {
                *self.packets_failed.write().await += 1;
                Err(format!("NexusBridge cannot handle traffic class: {:?}", packet.traffic_class))
            }
        }
    }

    pub fn health_check_sync(&self) -> BridgeHealthReport {
        let status = *self.status.blocking_read();
        let processed = *self.packets_processed.blocking_read();
        let failed = *self.packets_failed.blocking_read();
        let sessions = self.discovered_agents.blocking_read().len();
        BridgeHealthReport {
            domain: BridgeDomain::Nexus,
            status,
            packets_processed: processed,
            packets_failed: failed,
            active_sessions: sessions,
            uptime_seconds: self.started_at.elapsed().as_secs_f64(),
        }
    }
}

/******************************************************************************/
/* HIVE Bridge — Data/Swarm Traffic                                           */
/******************************************************************************/

pub struct HIVEBridge {
    status: RwLock<BridgeStatus>,
    packets_processed: RwLock<u64>,
    packets_failed: RwLock<u64>,
    queue_depth: RwLock<u64>,
    estates: RwLock<HashMap<String, serde_json::Value>>,
    started_at: Instant,
}

impl HIVEBridge {
    pub fn new() -> Self {
        Self {
            status: RwLock::new(BridgeStatus::Active),
            packets_processed: RwLock::new(0),
            packets_failed: RwLock::new(0),
            queue_depth: RwLock::new(0),
            estates: RwLock::new(HashMap::new()),
            started_at: Instant::now(),
        }
    }

    pub async fn process_packet(&self, packet: &BridgeTrafficPacket) -> Result<serde_json::Value, String> {
        match packet.traffic_class {
            TrafficClass::DataQueue
            | TrafficClass::DataTransport
            | TrafficClass::SwarmDispatch
            | TrafficClass::SwarmConsensus
            | TrafficClass::EstateScan => {
                *self.packets_processed.write().await += 1;

                match packet.traffic_class {
                    TrafficClass::DataQueue => {
                        *self.queue_depth.write().await += 1;
                    }
                    TrafficClass::DataTransport => {
                        let mut qd = self.queue_depth.write().await;
                        *qd = qd.saturating_sub(1);
                    }
                    TrafficClass::EstateScan => {
                        self.estates.write().await.insert(
                            packet.source.clone(),
                            packet.payload.clone(),
                        );
                    }
                    _ => {}
                }

                Ok(serde_json::json!({
                    "bridge": "hive",
                    "action": format!("{:?}", packet.traffic_class),
                    "source": packet.source,
                    "queue_depth": *self.queue_depth.blocking_read(),
                    "status": "processed",
                }))
            }
            _ => {
                *self.packets_failed.write().await += 1;
                Err(format!("HIVEBridge cannot handle traffic class: {:?}", packet.traffic_class))
            }
        }
    }

    pub fn health_check_sync(&self) -> BridgeHealthReport {
        let status = *self.status.blocking_read();
        let processed = *self.packets_processed.blocking_read();
        let failed = *self.packets_failed.blocking_read();
        let sessions = self.estates.blocking_read().len();
        BridgeHealthReport {
            domain: BridgeDomain::Hive,
            status,
            packets_processed: processed,
            packets_failed: failed,
            active_sessions: sessions,
            uptime_seconds: self.started_at.elapsed().as_secs_f64(),
        }
    }
}

/******************************************************************************/
/* Routing Rule                                                               */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingRule {
    pub sender_pattern: String,
    pub recipient_pattern: String,
    pub skill_pattern: Option<String>,
    pub target_bridge: BridgeDomain,
    pub priority_boost: i8,
    pub enabled: bool,
}

/******************************************************************************/
/* Sentinel Station — Three-Bridge Coordinator                                */
/******************************************************************************/

pub struct SentinelStation {
    infinity: Arc<InfinityBridge>,
    nexus: Arc<NexusBridge>,
    hive: Arc<HIVEBridge>,
    routing_rules: RwLock<Vec<RoutingRule>>,
}

impl SentinelStation {
    pub fn new() -> Self {
        Self {
            infinity: Arc::new(InfinityBridge::new()),
            nexus: Arc::new(NexusBridge::new()),
            hive: Arc::new(HIVEBridge::new()),
            routing_rules: RwLock::new(Vec::new()),
        }
    }

    /// Classify traffic and determine which bridge should handle it
    pub fn classify_traffic(&self, traffic_class: &TrafficClass) -> BridgeDomain {
        traffic_to_bridge(traffic_class)
    }

    /// Route a traffic packet to the appropriate bridge (async)
    pub async fn route_traffic(&self, mut packet: BridgeTrafficPacket) -> Result<serde_json::Value, String> {
        // Apply routing rules
        {
            let rules = self.routing_rules.read().await;
            for rule in rules.iter().filter(|r| r.enabled) {
                if rule.sender_pattern == "*" || rule.sender_pattern == packet.source {
                    if let Some(ref dest) = packet.destination {
                        if rule.recipient_pattern == "*" || rule.recipient_pattern == dest.as_str() {
                            packet.target_bridge = rule.target_bridge;
                            if rule.priority_boost > 0 {
                                packet.priority = packet.priority.saturating_add(rule.priority_boost as u8);
                            }
                        }
                    }
                }
            }
        }

        match packet.target_bridge {
            BridgeDomain::Infinity => self.infinity.process_packet(&packet).await,
            BridgeDomain::Nexus => self.nexus.process_packet(&packet).await,
            BridgeDomain::Hive => self.hive.process_packet(&packet).await,
        }
    }

    /// Escalate a packet to a higher-tier bridge
    pub async fn escalate(&self, packet: &BridgeTrafficPacket, reason: &str) -> Result<serde_json::Value, String> {
        let escalation_packet = BridgeTrafficPacket {
            id: uuid::Uuid::new_v4().to_string(),
            traffic_class: TrafficClass::Escalation,
            target_bridge: BridgeDomain::Infinity,
            source: packet.source.clone(),
            destination: None,
            payload: serde_json::json!({
                "original_traffic_class": format!("{:?}", packet.traffic_class),
                "original_bridge": format!("{}", packet.target_bridge),
                "reason": reason,
                "original_payload": packet.payload,
            }),
            priority: packet.priority.saturating_add(5),
            requires_escalation: true,
            timestamp: chrono::Utc::now().to_rfc3339(),
        };
        self.infinity.process_packet(&escalation_packet).await
    }

    /// Aggregate health from all three bridges
    pub fn aggregate_health(&self) -> serde_json::Value {
        let infinity_health = self.infinity.health_check_sync();
        let nexus_health = self.nexus.health_check_sync();
        let hive_health = self.hive.health_check_sync();

        let all_active = infinity_health.status == BridgeStatus::Active
            && nexus_health.status == BridgeStatus::Active
            && hive_health.status == BridgeStatus::Active;

        serde_json::json!({
            "sentinel_station": {
                "overall_status": if all_active { "healthy" } else { "degraded" },
                "bridges": {
                    "infinity": infinity_health,
                    "nexus": nexus_health,
                    "hive": hive_health,
                },
                "total_packets_processed": infinity_health.packets_processed
                    + nexus_health.packets_processed
                    + hive_health.packets_processed,
                "total_packets_failed": infinity_health.packets_failed
                    + nexus_health.packets_failed
                    + hive_health.packets_failed,
            }
        })
    }

    /// Add a routing rule
    pub async fn add_routing_rule(&self, rule: RoutingRule) {
        info!(
            "Sentinel: Adding routing rule: {} → {} (bridge: {})",
            rule.sender_pattern, rule.recipient_pattern, rule.target_bridge
        );
        self.routing_rules.write().await.push(rule);
    }

    /// Get references to individual bridges
    pub fn infinity_bridge(&self) -> &Arc<InfinityBridge> {
        &self.infinity
    }

    pub fn nexus_bridge(&self) -> &Arc<NexusBridge> {
        &self.nexus
    }

    pub fn hive_bridge(&self) -> &Arc<HIVEBridge> {
        &self.hive
    }
}
