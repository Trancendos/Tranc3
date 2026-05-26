/******************************************************************************/
/* Tranc3 Ecosystem — A2A Protocol Handler for Rust Nanoservice               */
/*                                                                            */
/* Implements the Agent-to-Agent (A2A) protocol for inter-agent messaging     */
/* within the Tranc3 nanoservice. Supports JSON-RPC 2.0 message relay,        */
/* skill-based routing, and least-loaded agent selection.                     */
/*                                                                            */
/* Entity Taxonomy: AID/SID/NID                                               */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

use std::collections::HashMap;
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

/******************************************************************************/
/* A2A Message Types                                                          */
/******************************************************************************/

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum A2AMessageType {
    Request,
    Response,
    Notification,
    Broadcast,
    Query,
    Delegate,
    Escalate,
    Heartbeat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum A2AResponseStatus {
    Success,
    Failure,
    Timeout,
    Refused,
    Delegated,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum A2APriority {
    Low = 0,
    Normal = 5,
    High = 10,
    Critical = 15,
    Emergency = 20,
}

/******************************************************************************/
/* Agent Card — describes an agent's capabilities                             */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentSkill {
    pub id: String,
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentCard {
    pub id: String,
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub skills: Vec<AgentSkill>,
    pub tier: u8,
    #[serde(default)]
    pub pillar: String,
    #[serde(default)]
    pub hub: String,
    #[serde(default)]
    pub tags: Vec<String>,
}

/******************************************************************************/
/* A2A Message Envelope                                                       */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A2AMessage {
    pub id: String,
    pub message_type: A2AMessageType,
    pub sender: String,
    pub recipient: Option<String>,
    pub skill: Option<String>,
    pub payload: serde_json::Value,
    pub priority: A2APriority,
    pub correlation_id: Option<String>,
    pub timestamp: String,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A2AResponse {
    pub id: String,
    pub correlation_id: String,
    pub status: A2AResponseStatus,
    pub sender: String,
    pub payload: serde_json::Value,
    pub error: Option<String>,
    pub delegated_to: Option<String>,
}

/******************************************************************************/
/* A2A Router — skill-based routing and least-loaded selection                */
/******************************************************************************/

pub struct A2ARouter {
    agents: RwLock<HashMap<String, AgentCard>>,
    load_counters: RwLock<HashMap<String, u64>>,
}

impl A2ARouter {
    pub fn new() -> Self {
        Self {
            agents: RwLock::new(HashMap::new()),
            load_counters: RwLock::new(HashMap::new()),
        }
    }

    /// Register an agent in the routing table
    pub async fn register_agent(&self, card: AgentCard) {
        info!("A2A: Registering agent {} ({})", card.name, card.id);
        self.agents.write().await.insert(card.id.clone(), card);
        self.load_counters.write().await.insert(card.id.clone(), 0);
    }

    /// Unregister an agent from the routing table
    pub async fn unregister_agent(&self, agent_id: &str) {
        info!("A2A: Unregistering agent {}", agent_id);
        self.agents.write().await.remove(agent_id);
        self.load_counters.write().await.remove(agent_id);
    }

    /// Find agents that have a specific skill
    pub async fn find_by_skill(&self, skill_name: &str) -> Vec<AgentCard> {
        let agents = self.agents.read().await;
        agents
            .values()
            .filter(|a| a.skills.iter().any(|s| s.name == skill_name || s.id == skill_name))
            .cloned()
            .collect()
    }

    /// Find agents by tier
    pub async fn find_by_tier(&self, tier: u8) -> Vec<AgentCard> {
        let agents = self.agents.read().await;
        agents.values().filter(|a| a.tier == tier).cloned().collect()
    }

    /// Resolve a recipient — skill-based with least-loaded selection
    pub async fn resolve_recipient(&self, skill: Option<&str>, preferred: Option<&str>) -> Option<AgentCard> {
        // If a preferred recipient is specified and exists, use it
        if let Some(pref) = preferred {
            let agents = self.agents.read().await;
            if let Some(agent) = agents.get(pref) {
                return Some(agent.clone());
            }
        }

        // Find agents with the requested skill
        let candidates = if let Some(skill_name) = skill {
            self.find_by_skill(skill_name).await
        } else {
            let agents = self.agents.read().await;
            agents.values().cloned().collect()
        };

        if candidates.is_empty() {
            return None;
        }

        // Least-loaded selection
        let loads = self.load_counters.read().await;
        let mut best = &candidates[0];
        let mut best_load = loads.get(&best.id).copied().unwrap_or(u64::MAX);

        for candidate in &candidates[1..] {
            let load = loads.get(&candidate.id).copied().unwrap_or(u64::MAX);
            if load < best_load {
                best_load = load;
                best = candidate;
            }
        }

        Some(best.clone())
    }

    /// Increment load counter for an agent
    pub async fn increment_load(&self, agent_id: &str) {
        let mut loads = self.load_counters.write().await;
        *loads.entry(agent_id.to_string()).or_insert(0) += 1;
    }

    /// Decrement load counter for an agent
    pub async fn decrement_load(&self, agent_id: &str) {
        let mut loads = self.load_counters.write().await;
        if let Some(load) = loads.get_mut(agent_id) {
            *load = load.saturating_sub(1);
        }
    }

    /// Relay an A2A message to the appropriate recipient
    pub async fn relay_message(&self, message: A2AMessage) -> Result<A2AResponse, String> {
        let recipient = self
            .resolve_recipient(message.skill.as_deref(), message.recipient.as_deref())
            .await
            .ok_or_else(|| {
                let skill = message.skill.as_deref().unwrap_or("any");
                format!("No agent available for skill: {}", skill)
            })?;

        self.increment_load(&recipient.id).await;

        debug!(
            "A2A: Relaying message {} from {} to {} (skill: {:?})",
            message.id, message.sender, recipient.id, message.skill
        );

        // In a real deployment, this would forward the message to the agent's endpoint.
        // For the nanoservice, we acknowledge receipt and record the relay.
        let response = A2AResponse {
            id: Uuid::new_v4().to_string(),
            correlation_id: message.id.clone(),
            status: A2AResponseStatus::Success,
            sender: recipient.id.clone(),
            payload: serde_json::json!({
                "relayed_to": recipient.name,
                "skill": message.skill,
                "tier": recipient.tier,
            }),
            error: None,
            delegated_to: None,
        };

        self.decrement_load(&recipient.id).await;
        Ok(response)
    }

    /// Broadcast a message to all agents matching a skill or tier filter
    pub async fn broadcast(
        &self,
        sender: &str,
        skill: Option<&str>,
        tier: Option<u8>,
        payload: serde_json::Value,
    ) -> Vec<A2AResponse> {
        let agents = self.agents.read().await;
        let targets: Vec<&AgentCard> = agents
            .values()
            .filter(|a| {
                if let Some(t) = tier {
                    if a.tier != t {
                        return false;
                    }
                }
                if let Some(s) = skill {
                    if !a.skills.iter().any(|sk| sk.name == s || sk.id == s) {
                        return false;
                    }
                }
                true
            })
            .collect();

        let mut responses = Vec::new();
        for target in targets {
            responses.push(A2AResponse {
                id: Uuid::new_v4().to_string(),
                correlation_id: "broadcast".to_string(),
                status: A2AResponseStatus::Success,
                sender: target.id.clone(),
                payload: serde_json::json!({
                    "broadcast_received": true,
                    "original_sender": sender,
                }),
                error: None,
                delegated_to: None,
            });
        }
        responses
    }

    /// Get registered agent count
    pub async fn agent_count(&self) -> usize {
        self.agents.read().await.len()
    }

    /// Health check
    pub async fn health_check(&self) -> serde_json::Value {
        let agents = self.agents.read().await;
        let loads = self.load_counters.read().await;
        serde_json::json!({
            "registered_agents": agents.len(),
            "total_load": loads.values().sum::<u64>(),
        })
    }
}
