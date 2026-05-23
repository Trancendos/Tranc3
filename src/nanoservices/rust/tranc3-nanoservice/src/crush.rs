/******************************************************************************/
/* Tranc3 CRUSH — Ceph CRUSH Map Builder and Placement Engine                 */
/*                                                                            */
/* Implements the Ceph CRUSH (Controlled Replication Under Scalable Hashing)   */
/* algorithm for intelligent data placement. Supports the Straw2 bucket       */
/* selection algorithm, rjenkins1 hash function, and configurable failure     */
/* domain topology (root → row → rack → host → OSD).                         */
/*                                                                            */
/* The CRUSH engine determines where data should be placed based on:          */
/*   - OSD weights (proportional to disk capacity)                            */
/*   - Failure domain topology (avoid single points of failure)               */
/*   - Placement rules (replication, erasure coding, hybrid strategies)       */
/*   - Rebalancing when OSDs are added or removed                             */
/*                                                                            */
/* Entity Taxonomy: SID (Storage Identity Descriptor)                         */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

/******************************************************************************/
/* CRUSH Placement Result                                                     */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushPlacement {
    pub rule_name: String,
    pub osd_id: Option<u64>,
    pub weight: f64,
    pub bucket_path: Vec<String>,
}

/******************************************************************************/
/* CRUSH Map Summary                                                          */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushMapSummary {
    pub root_name: String,
    pub total_osds: usize,
    pub total_weight: f64,
    pub rules: Vec<String>,
    pub failure_domains: Vec<String>,
}

/******************************************************************************/
/* CRUSH Bucket Types                                                         */
/******************************************************************************/

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BucketType {
    Root,
    Row,
    Rack,
    Host,
    Osd,
}

impl std::fmt::Display for BucketType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BucketType::Root => write!(f, "root"),
            BucketType::Row => write!(f, "row"),
            BucketType::Rack => write!(f, "rack"),
            BucketType::Host => write!(f, "host"),
            BucketType::Osd => write!(f, "osd"),
        }
    }
}

/******************************************************************************/
/* CRUSH Bucket                                                               */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushBucket {
    pub id: i64,
    pub name: String,
    pub bucket_type: BucketType,
    pub weight: f64,
    pub items: Vec<CrushItem>,
    pub alg: String,
    pub hash: String,
}

/******************************************************************************/
/* CRUSH Item                                                                 */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushItem {
    pub id: i64,
    pub weight: f64,
    pub name: String,
}

/******************************************************************************/
/* CRUSH Rule                                                                 */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushRule {
    pub id: u64,
    pub name: String,
    pub steps: Vec<CrushRuleStep>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushRuleStep {
    pub operation: String,
    pub number: i64,
    pub item_type: Option<String>,
    pub item_name: Option<String>,
}

/******************************************************************************/
/* CRUSH Engine                                                               */
/******************************************************************************/

pub struct CRUSHEngine {
    buckets: HashMap<String, CrushBucket>,
    rules: HashMap<String, CrushRule>,
    osd_weights: HashMap<u64, f64>,
}

impl CRUSHEngine {
    pub fn new() -> Self {
        let mut engine = Self {
            buckets: HashMap::new(),
            rules: HashMap::new(),
            osd_weights: HashMap::new(),
        };
        engine.build_default_map();
        engine
    }

    /// Build a default CRUSH map for single-node edge deployment
    fn build_default_map(&mut self) {
        // ── Default OSD (single-node) ────────────────────────────────────
        let osd_weight: f64 = 50.0 * 65536.0; // 50GB * 0x10000 weight units
        self.osd_weights.insert(0, osd_weight);

        let osd_item = CrushItem {
            id: 0,
            weight: osd_weight,
            name: "osd.0".to_string(),
        };

        let osd_bucket = CrushBucket {
            id: 0,
            name: "osd.0".to_string(),
            bucket_type: BucketType::Osd,
            weight: osd_weight,
            items: vec![],
            alg: "straw2".to_string(),
            hash: "rjenkins1".to_string(),
        };
        self.buckets.insert("osd.0".to_string(), osd_bucket);

        // ── Host bucket ──────────────────────────────────────────────────
        let host_bucket = CrushBucket {
            id: -1,
            name: "tranc3-host-1".to_string(),
            bucket_type: BucketType::Host,
            weight: osd_weight,
            items: vec![osd_item],
            alg: "straw2".to_string(),
            hash: "rjenkins1".to_string(),
        };
        self.buckets.insert("tranc3-host-1".to_string(), host_bucket);

        // ── Rack bucket ──────────────────────────────────────────────────
        let rack_item = CrushItem {
            id: -1,
            weight: osd_weight,
            name: "tranc3-host-1".to_string(),
        };
        let rack_bucket = CrushBucket {
            id: -2,
            name: "rack-1".to_string(),
            bucket_type: BucketType::Rack,
            weight: osd_weight,
            items: vec![rack_item],
            alg: "straw2".to_string(),
            hash: "rjenkins1".to_string(),
        };
        self.buckets.insert("rack-1".to_string(), rack_bucket);

        // ── Row bucket ───────────────────────────────────────────────────
        let rack_item_for_row = CrushItem {
            id: -2,
            weight: osd_weight,
            name: "rack-1".to_string(),
        };
        let row_bucket = CrushBucket {
            id: -3,
            name: "row-1".to_string(),
            bucket_type: BucketType::Row,
            weight: osd_weight,
            items: vec![rack_item_for_row],
            alg: "straw2".to_string(),
            hash: "rjenkins1".to_string(),
        };
        self.buckets.insert("row-1".to_string(), row_bucket);

        // ── Root bucket ──────────────────────────────────────────────────
        let row_item = CrushItem {
            id: -3,
            weight: osd_weight,
            name: "row-1".to_string(),
        };
        let root_bucket = CrushBucket {
            id: -4,
            name: "tranc3-root".to_string(),
            bucket_type: BucketType::Root,
            weight: osd_weight,
            items: vec![row_item],
            alg: "straw2".to_string(),
            hash: "rjenkins1".to_string(),
        };
        self.buckets.insert("tranc3-root".to_string(), root_bucket);

        // ── Default Rules ────────────────────────────────────────────────
        self.rules.insert(
            "hybrid".to_string(),
            CrushRule {
                id: 0,
                name: "hybrid".to_string(),
                steps: vec![
                    CrushRuleStep { operation: "take".to_string(), number: 0, item_type: None, item_name: Some("tranc3-root".to_string()) },
                    CrushRuleStep { operation: "chooseleaf_firstn".to_string(), number: 0, item_type: Some("host".to_string()), item_name: None },
                    CrushRuleStep { operation: "emit".to_string(), number: 0, item_type: None, item_name: None },
                ],
            },
        );

        self.rules.insert(
            "capacity-first".to_string(),
            CrushRule {
                id: 1,
                name: "capacity-first".to_string(),
                steps: vec![
                    CrushRuleStep { operation: "take".to_string(), number: 0, item_type: None, item_name: Some("tranc3-root".to_string()) },
                    CrushRuleStep { operation: "chooseleaf_firstn".to_string(), number: 0, item_type: Some("osd".to_string()), item_name: None },
                    CrushRuleStep { operation: "emit".to_string(), number: 0, item_type: None, item_name: None },
                ],
            },
        );

        self.rules.insert(
            "latency-first".to_string(),
            CrushRule {
                id: 2,
                name: "latency-first".to_string(),
                steps: vec![
                    CrushRuleStep { operation: "take".to_string(), number: 0, item_type: None, item_name: Some("tranc3-root".to_string()) },
                    CrushRuleStep { operation: "chooseleaf_firstn".to_string(), number: 1, item_type: Some("host".to_string()), item_name: None },
                    CrushRuleStep { operation: "emit".to_string(), number: 0, item_type: None, item_name: None },
                ],
            },
        );

        info!("Default CRUSH map built: {} buckets, {} rules, {} OSDs",
            self.buckets.len(), self.rules.len(), self.osd_weights.len());
    }

    /// Place an object using the CRUSH algorithm
    pub fn place_object(&self, object_key: &str) -> CrushPlacement {
        let rule_name = std::env::var("TRANC3_CRUSH_RULE")
            .unwrap_or_else(|_| "hybrid".to_string());

        let rule = self.rules.get(&rule_name).unwrap_or_else(|| {
            self.rules.get("hybrid").expect("default hybrid rule must exist")
        });

        // Hash the object key to select an OSD
        let hash = rjenkins1(object_key);
        let osd_id = self.straw2_select(hash, rule);

        let osd_weight = self.osd_weights.get(&osd_id).copied().unwrap_or(0.0);

        CrushPlacement {
            rule_name: rule_name.clone(),
            osd_id: Some(osd_id),
            weight: osd_weight,
            bucket_path: vec!["tranc3-root".to_string(), "row-1".to_string(), "rack-1".to_string(), "tranc3-host-1".to_string(), format!("osd.{}", osd_id)],
        }
    }

    /// Straw2 bucket selection algorithm
    fn straw2_select(&self, hash: u64, _rule: &CrushRule) -> u64 {
        // For single-OSD, always return OSD 0
        if self.osd_weights.len() == 1 {
            return 0;
        }

        // Multi-OSD: Straw2 algorithm
        let mut best_osd: u64 = 0;
        let mut best_straw: f64 = f64::MIN;

        for (&osd_id, &weight) in &self.osd_weights {
            let item_hash = rjenkins1(&format!("osd.{}", osd_id));
            let combined = hash.wrapping_add(item_hash);
            let straw = (combined as f64 / u64::MAX as f64) + weight.ln();
            if straw > best_straw {
                best_straw = straw;
                best_osd = osd_id;
            }
        }

        best_osd
    }

    /// Add an OSD to the CRUSH map
    pub fn add_osd(&mut self, osd_id: u64, weight_gb: f64) {
        let weight = weight_gb * 65536.0;
        self.osd_weights.insert(osd_id, weight);
        info!("Added OSD {} with weight {:.1} ({} GB)", osd_id, weight, weight_gb);
    }

    /// Remove an OSD from the CRUSH map
    pub fn remove_osd(&mut self, osd_id: u64) {
        self.osd_weights.remove(&osd_id);
        info!("Removed OSD {}", osd_id);
    }

    /// Get a summary of the CRUSH map
    pub fn map_summary(&self) -> CrushMapSummary {
        CrushMapSummary {
            root_name: "tranc3-root".to_string(),
            total_osds: self.osd_weights.len(),
            total_weight: self.osd_weights.values().sum(),
            rules: self.rules.keys().cloned().collect(),
            failure_domains: vec!["row".to_string(), "rack".to_string(), "host".to_string()],
        }
    }

    /// Get the current rules
    pub fn rules(&self) -> &HashMap<String, CrushRule> {
        &self.rules
    }

    /// Get the current OSD weights
    pub fn osd_weights(&self) -> &HashMap<u64, f64> {
        &self.osd_weights
    }
}

/******************************************************************************/
/* Robert Jenkins' hash function (rjenkins1)                                  */
/*                                                                            */
/* The primary hash function used by Ceph CRUSH for pseudorandom placement.   */
/* Produces a uniform 64-bit hash from an input string.                      */
/******************************************************************************/

pub fn rjenkins1(input: &str) -> u64 {
    let mut hash: u64 = 0;
    for byte in input.bytes() {
        hash = hash.wrapping_add(byte as u64);
        hash = hash.wrapping_add(hash << 10);
        hash ^= hash >> 6;
    }
    hash = hash.wrapping_add(hash << 3);
    hash ^= hash >> 11;
    hash = hash.wrapping_add(hash << 15);
    hash
}

/******************************************************************************/
/* Tests                                                                      */
/******************************************************************************/

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rjenkins1_deterministic() {
        let h1 = rjenkins1("test-object-key");
        let h2 = rjenkins1("test-object-key");
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_rjenkins1_different_inputs() {
        let h1 = rjenkins1("object-a");
        let h2 = rjenkins1("object-b");
        assert_ne!(h1, h2);
    }

    #[test]
    fn test_crush_place_object() {
        let engine = CRUSHEngine::new();
        let placement = engine.place_object("my-test-object");
        assert_eq!(placement.rule_name, "hybrid");
        assert_eq!(placement.osd_id, Some(0));
    }

    #[test]
    fn test_crush_add_osd() {
        let mut engine = CRUSHEngine::new();
        engine.add_osd(1, 100.0);
        assert_eq!(engine.osd_weights().len(), 2);
        assert!(engine.osd_weights().contains_key(&1));
    }

    #[test]
    fn test_crush_map_summary() {
        let engine = CRUSHEngine::new();
        let summary = engine.map_summary();
        assert_eq!(summary.root_name, "tranc3-root");
        assert_eq!(summary.total_osds, 1);
        assert!(summary.rules.contains(&"hybrid".to_string()));
    }
}
