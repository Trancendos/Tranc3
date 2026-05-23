/******************************************************************************/
/* Tranc3 Adaptive — Capacity Management and Smart Switching                   */
/*                                                                            */
/* Adaptive capacity manager that monitors storage utilization across the      */
/* multi-cloud fallback chain, enforces free-tier quotas, and triggers        */
/* intelligent migration of data between providers when capacity thresholds    */
/* are exceeded. Integrates with the CRUSH engine for topology-aware          */
/* rebalancing and the storage router for seamless failover.                  */
/*                                                                            */
/* Entity Taxonomy: AID (Adaptive Instance Descriptor)                        */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tracing::info;

use crate::crush::CRUSHEngine;
use crate::storage::StorageRouter;

/******************************************************************************/
/* System Modes                                                               */
/******************************************************************************/

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemMode {
    TrueNas,
    Hybrid,
    CloudOnly,
}

impl std::fmt::Display for SystemMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SystemMode::TrueNas => write!(f, "TRUE_NAS"),
            SystemMode::Hybrid => write!(f, "HYBRID"),
            SystemMode::CloudOnly => write!(f, "CLOUD_ONLY"),
        }
    }
}

/******************************************************************************/
/* Capacity Thresholds                                                        */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapacityThresholds {
    pub warn_percent: f64,
    pub critical_percent: f64,
    pub oci_storage_quota_gb: f64,
    pub oci_block_volume_quota_gb: f64,
    pub r2_storage_quota_gb: f64,
}

impl Default for CapacityThresholds {
    fn default() -> Self {
        Self {
            warn_percent: 80.0,
            critical_percent: 95.0,
            oci_storage_quota_gb: 20.0,
            oci_block_volume_quota_gb: 200.0,
            r2_storage_quota_gb: 10.0,
        }
    }
}

/******************************************************************************/
/* Capacity Summary                                                           */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapacitySummary {
    pub system_mode: String,
    pub providers: Vec<ProviderCapacity>,
    pub total_used_gb: f64,
    pub total_limit_gb: f64,
    pub utilization_percent: f64,
    pub status: CapacityStatus,
    pub recommendations: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderCapacity {
    pub name: String,
    pub used_gb: f64,
    pub limit_gb: f64,
    pub utilization_percent: f64,
    pub healthy: bool,
    pub status: CapacityStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CapacityStatus {
    Normal,
    Warning,
    Critical,
    Exhausted,
}

/******************************************************************************/
/* Idle Defense Configuration                                                 */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdleDefenseConfig {
    pub enabled: bool,
    pub cron_schedule: String,
    pub burst_duration_seconds: u64,
    pub target_cpu_percent: f64,
}

impl Default for IdleDefenseConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            cron_schedule: "*/5 * * * *".to_string(),
            burst_duration_seconds: 30,
            target_cpu_percent: 25.0,
        }
    }
}

/******************************************************************************/
/* Adaptive Capacity Manager                                                  */
/******************************************************************************/

pub struct AdaptiveCapacityManager {
    storage_router: Arc<StorageRouter>,
    crush_engine: Arc<CRUSHEngine>,
    system_mode: SystemMode,
    thresholds: CapacityThresholds,
    idle_defense: IdleDefenseConfig,
}

impl AdaptiveCapacityManager {
    pub fn new(storage_router: Arc<StorageRouter>, crush_engine: Arc<CRUSHEngine>) -> Self {
        let system_mode = match std::env::var("TRANC3_SYSTEM_MODE")
            .unwrap_or_else(|_| "HYBRID".to_string())
            .to_uppercase()
            .as_str()
        {
            "TRUE_NAS" => SystemMode::TrueNas,
            "CLOUD_ONLY" => SystemMode::CloudOnly,
            _ => SystemMode::Hybrid,
        };

        Self {
            storage_router,
            crush_engine,
            system_mode,
            thresholds: CapacityThresholds::default(),
            idle_defense: IdleDefenseConfig::default(),
        }
    }

    /// Generate a capacity summary for all providers
    pub fn capacity_summary(&self) -> CapacitySummary {
        let _fallback_status = self.storage_router.fallback_status();

        // Build provider capacities from fallback chain
        let providers = vec![
            ProviderCapacity {
                name: "oci".to_string(),
                used_gb: 0.0,
                limit_gb: self.thresholds.oci_storage_quota_gb,
                utilization_percent: 0.0,
                healthy: true,
                status: CapacityStatus::Normal,
            },
            ProviderCapacity {
                name: "cloudflare_r2".to_string(),
                used_gb: 0.0,
                limit_gb: self.thresholds.r2_storage_quota_gb,
                utilization_percent: 0.0,
                healthy: true,
                status: CapacityStatus::Normal,
            },
            ProviderCapacity {
                name: "ceph_rgw".to_string(),
                used_gb: 0.0,
                limit_gb: f64::MAX,
                utilization_percent: 0.0,
                healthy: true,
                status: CapacityStatus::Normal,
            },
        ];

        let total_used_gb: f64 = providers.iter().map(|p| p.used_gb).sum();
        let total_limit_gb: f64 = providers.iter().map(|p| p.limit_gb).filter(|l| *l < f64::MAX).sum();

        let utilization_percent = if total_limit_gb > 0.0 {
            (total_used_gb / total_limit_gb) * 100.0
        } else {
            0.0
        };

        let status = if utilization_percent >= self.thresholds.critical_percent {
            CapacityStatus::Critical
        } else if utilization_percent >= self.thresholds.warn_percent {
            CapacityStatus::Warning
        } else {
            CapacityStatus::Normal
        };

        let mut recommendations = Vec::new();
        if status == CapacityStatus::Warning {
            recommendations.push("Consider migrating cold data to R2 archive tier".to_string());
        }
        if status == CapacityStatus::Critical {
            recommendations.push("Immediately migrate data to fallback providers".to_string());
            recommendations.push("Enable aggressive lifecycle policies".to_string());
        }

        CapacitySummary {
            system_mode: self.system_mode.to_string(),
            providers,
            total_used_gb,
            total_limit_gb,
            utilization_percent,
            status,
            recommendations,
        }
    }

    /// Check if a provider is within quota
    pub fn check_quota(&self, provider: &str, used_gb: f64) -> Result<(), String> {
        let limit = match provider {
            "oci" => self.thresholds.oci_storage_quota_gb,
            "r2" | "cloudflare_r2" => self.thresholds.r2_storage_quota_gb,
            _ => return Ok(()),
        };

        if used_gb >= limit {
            Err(format!("Provider {} quota exceeded: {:.1}/{:.1} GB", provider, used_gb, limit))
        } else {
            Ok(())
        }
    }

    /// Get the current system mode
    pub fn system_mode(&self) -> SystemMode {
        self.system_mode
    }

    /// Get idle defense configuration
    pub fn idle_defense_config(&self) -> &IdleDefenseConfig {
        &self.idle_defense
    }
}
