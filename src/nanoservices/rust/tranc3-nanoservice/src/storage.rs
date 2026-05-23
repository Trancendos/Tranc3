/******************************************************************************/
/* Tranc3 Storage — Multi-Backend Adaptive Storage Router                     */
/*                                                                            */
/* Provides async multi-backend storage operations across OCI Object Storage,  */
/* Cloudflare R2, MinIO, and Ceph RGW. The StorageRouter implements the       */
/* multi-cloud fallback chain and integrates with the CRUSH engine for        */
/* intelligent placement. Uses AWS Signature Version 4 for S3-compatible      */
/* API signing.                                                               */
/*                                                                            */
/* Entity Taxonomy: SID (Storage Identity Descriptor)                         */
/* Author: Drew Porter / Trancendos                                           */
/* License: MIT                                                               */
/******************************************************************************/

use std::sync::Arc;

use async_trait::async_trait;
use bytes::Bytes;
use chrono::Utc;
use hmac::{Hmac, Mac};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::{debug, info, warn};

use crate::crush::CRUSHEngine;

/******************************************************************************/
/* Error Types                                                                */
/******************************************************************************/

#[derive(Debug, Clone)]
pub enum StorageError {
    ConnectionFailed(String),
    NotFound(String),
    PermissionDenied(String),
    QuotaExceeded { provider: String, used_gb: f64, limit_gb: f64 },
    AllBackendsFailed(String),
    SigningError(String),
    ConfigurationError(String),
    IoError(String),
}

impl std::fmt::Display for StorageError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            StorageError::ConnectionFailed(msg) => write!(f, "Connection failed: {}", msg),
            StorageError::NotFound(msg) => write!(f, "Not found: {}", msg),
            StorageError::PermissionDenied(msg) => write!(f, "Permission denied: {}", msg),
            StorageError::QuotaExceeded { provider, used_gb, limit_gb } => {
                write!(f, "Quota exceeded on {}: {:.1}/{:.1} GB", provider, used_gb, limit_gb)
            }
            StorageError::AllBackendsFailed(msg) => write!(f, "All backends failed: {}", msg),
            StorageError::SigningError(msg) => write!(f, "Signing error: {}", msg),
            StorageError::ConfigurationError(msg) => write!(f, "Configuration error: {}", msg),
            StorageError::IoError(msg) => write!(f, "IO error: {}", msg),
        }
    }
}

impl std::error::Error for StorageError {}

/******************************************************************************/
/* Write Result                                                               */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WriteResult {
    pub path: String,
    pub provider: String,
    pub bytes_written: usize,
    pub timestamp: String,
    pub etag: Option<String>,
    pub crush_placement: Option<CrushPlacementInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrushPlacementInfo {
    pub rule_name: String,
    pub osd_id: Option<u64>,
    pub weight: f64,
    pub primary: bool,
}

/******************************************************************************/
/* Backend Health Status                                                      */
/******************************************************************************/

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendStatus {
    pub provider: String,
    pub healthy: bool,
    pub used_bytes: u64,
    pub limit_bytes: u64,
    pub utilization_percent: f64,
    pub last_checked: String,
    pub endpoint: String,
}

/******************************************************************************/
/* Storage Provider Trait                                                     */
/******************************************************************************/

#[async_trait]
pub trait StorageProvider: Send + Sync {
    fn name(&self) -> &str;
    async fn write(&self, path: &str, data: Bytes) -> Result<WriteResult, StorageError>;
    async fn read(&self, path: &str) -> Result<Bytes, StorageError>;
    async fn delete(&self, path: &str) -> Result<(), StorageError>;
    async fn health_check(&self) -> bool;
    async fn capacity_bytes(&self) -> (u64, u64);
    fn is_ready(&self) -> bool;
}

/******************************************************************************/
/* Local Storage Provider                                                     */
/******************************************************************************/

pub struct LocalStorageProvider {
    base_path: String,
    ready: std::sync::RwLock<bool>,
}

impl LocalStorageProvider {
    pub fn new(base_path: &str) -> Self {
        let ready = std::path::Path::new(base_path).exists();
        Self {
            base_path: base_path.to_string(),
            ready: std::sync::RwLock::new(ready),
        }
    }
}

#[async_trait]
impl StorageProvider for LocalStorageProvider {
    fn name(&self) -> &str { "local" }

    async fn write(&self, path: &str, data: Bytes) -> Result<WriteResult, StorageError> {
        let full_path = format!("{}/{}", self.base_path, path);
        if let Some(parent) = std::path::Path::new(&full_path).parent() {
            tokio::fs::create_dir_all(parent).await.map_err(|e| StorageError::IoError(e.to_string()))?;
        }
        tokio::fs::write(&full_path, &data).await.map_err(|e| StorageError::IoError(e.to_string()))?;
        Ok(WriteResult {
            path: path.to_string(),
            provider: "local".to_string(),
            bytes_written: data.len(),
            timestamp: Utc::now().to_rfc3339(),
            etag: Some(sha256_hash(&data)),
            crush_placement: None,
        })
    }

    async fn read(&self, path: &str) -> Result<Bytes, StorageError> {
        let full_path = format!("{}/{}", self.base_path, path);
        let data = tokio::fs::read(&full_path).await.map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                StorageError::NotFound(path.to_string())
            } else {
                StorageError::IoError(e.to_string())
            }
        })?;
        Ok(Bytes::from(data))
    }

    async fn delete(&self, path: &str) -> Result<(), StorageError> {
        let full_path = format!("{}/{}", self.base_path, path);
        tokio::fs::remove_file(&full_path).await.map_err(|e| StorageError::IoError(e.to_string()))
    }

    async fn health_check(&self) -> bool {
        std::path::Path::new(&self.base_path).exists()
    }

    async fn capacity_bytes(&self) -> (u64, u64) {
        (0, u64::MAX)
    }

    fn is_ready(&self) -> bool {
        *self.ready.read().unwrap()
    }
}

/******************************************************************************/
/* S3-Compatible Storage Provider                                             */
/*                                                                            */
/* Generic S3-compatible provider supporting Ceph RGW, MinIO, and Cloudflare  */
/* R2. Uses AWS Signature Version 4 for request authentication.              */
/******************************************************************************/

pub struct S3CompatProvider {
    name: String,
    endpoint: String,
    bucket: String,
    region: String,
    access_key: String,
    secret_key: String,
    client: Client,
    ready: std::sync::RwLock<bool>,
}

impl S3CompatProvider {
    pub fn new(
        name: &str,
        endpoint: &str,
        bucket: &str,
        region: &str,
        access_key: &str,
        secret_key: &str,
    ) -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .expect("Failed to create HTTP client");
        Self {
            name: name.to_string(),
            endpoint: endpoint.trim_end_matches('/').to_string(),
            bucket: bucket.to_string(),
            region: region.to_string(),
            access_key: access_key.to_string(),
            secret_key: secret_key.to_string(),
            client,
            ready: std::sync::RwLock::new(false),
        }
    }

    /// AWS Signature Version 4 signing for S3-compatible APIs
    fn sign_request(
        &self,
        method: &str,
        url_path: &str,
        _host: &str,
        headers: &mut Vec<(String, String)>,
        payload_hash: &str,
    ) -> Result<(), StorageError> {
        let now = Utc::now();
        let date_stamp = now.format("%Y%m%d").to_string();
        let amz_date = now.format("%Y%m%dT%H%M%SZ").to_string();

        let service = "s3";
        let credential_scope = format!("{}/{}/{}/aws4_request", date_stamp, self.region, service);

        // Canonical headers
        headers.push(("x-amz-date".to_string(), amz_date.clone()));
        headers.push(("x-amz-content-sha256".to_string(), payload_hash.to_string()));
        headers.sort_by(|a, b| a.0.cmp(&b.0));

        let signed_headers: String = headers.iter().map(|(k, _)| k.as_str()).collect::<Vec<_>>().join(";");
        let canonical_headers: String = headers
            .iter()
            .map(|(k, v)| format!("{}:{}", k.to_lowercase(), v.trim()))
            .collect::<Vec<_>>()
            .join("\n");

        // Canonical request
        let canonical_request = format!(
            "{}\n{}\n\n{}\n\n{}\n{}",
            method, url_path, canonical_headers, signed_headers, payload_hash
        );

        let canonical_request_hash = sha256_hex(&canonical_request);

        // String to sign
        let string_to_sign = format!(
            "AWS4-HMAC-SHA256\n{}\n{}\n{}",
            amz_date, credential_scope, canonical_request_hash
        );

        // Signing key
        let signing_key = derive_signing_key(&self.secret_key, &date_stamp, &self.region, service);

        // Signature
        let signature = hmac_sha256_hex(&signing_key, &string_to_sign);

        // Authorization header
        let auth_header = format!(
            "AWS4-HMAC-SHA256 Credential={}/{}, SignedHeaders={}, Signature={}",
            self.access_key, credential_scope, signed_headers, signature
        );
        headers.push(("Authorization".to_string(), auth_header));

        Ok(())
    }

    fn build_url(&self, key: &str) -> String {
        format!("{}/{}/{}", self.endpoint, self.bucket, key)
    }
}

#[async_trait]
impl StorageProvider for S3CompatProvider {
    fn name(&self) -> &str { &self.name }

    async fn write(&self, path: &str, data: Bytes) -> Result<WriteResult, StorageError> {
        let url = self.build_url(path);
        let parsed = reqwest::Url::parse(&url).map_err(|e| StorageError::ConfigurationError(e.to_string()))?;
        let host = parsed.host_str().unwrap_or("").to_string();
        let url_path = parsed.path().to_string();
        let payload_hash = sha256_hash(&data);

        let mut headers = vec![("host".to_string(), host.clone())];
        self.sign_request("PUT", &url_path, &host, &mut headers, &payload_hash)?;

        let mut req = self.client.put(&url).body(data.clone());
        for (k, v) in headers {
            req = req.header(k, v);
        }

        let resp = req.send().await.map_err(|e| StorageError::ConnectionFailed(e.to_string()))?;

        if resp.status().is_success() {
            let etag = resp.headers().get("etag")
                .and_then(|v| v.to_str().ok())
                .map(|s| s.to_string());
            Ok(WriteResult {
                path: path.to_string(),
                provider: self.name.clone(),
                bytes_written: data.len(),
                timestamp: Utc::now().to_rfc3339(),
                etag,
                crush_placement: None,
            })
        } else {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            Err(StorageError::ConnectionFailed(format!("PUT {} returned {}: {}", path, status, body)))
        }
    }

    async fn read(&self, path: &str) -> Result<Bytes, StorageError> {
        let url = self.build_url(path);
        let parsed = reqwest::Url::parse(&url).map_err(|e| StorageError::ConfigurationError(e.to_string()))?;
        let host = parsed.host_str().unwrap_or("").to_string();
        let url_path = parsed.path().to_string();

        let mut headers = vec![("host".to_string(), host.clone())];
        self.sign_request("GET", &url_path, &host, &mut headers, &EMPTY_SHA256)?;

        let mut req = self.client.get(&url);
        for (k, v) in headers {
            req = req.header(k, v);
        }

        let resp = req.send().await.map_err(|e| StorageError::ConnectionFailed(e.to_string()))?;

        if resp.status().is_success() {
            let bytes = resp.bytes().await.map_err(|e| StorageError::IoError(e.to_string()))?;
            Ok(bytes)
        } else if resp.status().as_u16() == 404 {
            Err(StorageError::NotFound(path.to_string()))
        } else {
            let status = resp.status();
            Err(StorageError::ConnectionFailed(format!("GET {} returned {}", path, status)))
        }
    }

    async fn delete(&self, path: &str) -> Result<(), StorageError> {
        let url = self.build_url(path);
        let parsed = reqwest::Url::parse(&url).map_err(|e| StorageError::ConfigurationError(e.to_string()))?;
        let host = parsed.host_str().unwrap_or("").to_string();
        let url_path = parsed.path().to_string();

        let mut headers = vec![("host".to_string(), host.clone())];
        self.sign_request("DELETE", &url_path, &host, &mut headers, &EMPTY_SHA256)?;

        let mut req = self.client.delete(&url);
        for (k, v) in headers {
            req = req.header(k, v);
        }

        let resp = req.send().await.map_err(|e| StorageError::ConnectionFailed(e.to_string()))?;
        if resp.status().is_success() || resp.status().as_u16() == 204 {
            Ok(())
        } else {
            Err(StorageError::ConnectionFailed(format!("DELETE {} failed", path)))
        }
    }

    async fn health_check(&self) -> bool {
        let url = format!("{}/{}", self.endpoint, self.bucket);
        match self.client.head(&url).send().await {
            Ok(resp) => resp.status().is_success() || resp.status().as_u16() == 404,
            Err(_) => false,
        }
    }

    async fn capacity_bytes(&self) -> (u64, u64) {
        (0, u64::MAX)
    }

    fn is_ready(&self) -> bool {
        *self.ready.read().unwrap()
    }
}

/******************************************************************************/
/* OCI Storage Provider                                                       */
/*                                                                            */
/* Oracle Cloud Infrastructure Object Storage provider using the S3-compatible*/
/* API endpoint. Falls within the Always Free tier (20GB Standard storage).   */
/******************************************************************************/

pub struct OCIStorageProvider {
    s3: S3CompatProvider,
    namespace: String,
    compartment_id: String,
}

impl OCIStorageProvider {
    pub fn new(
        namespace: &str,
        compartment_id: &str,
        region: &str,
        access_key: &str,
        secret_key: &str,
        bucket: &str,
    ) -> Self {
        let endpoint = format!(
            "https://{}.compat.objectstorage.{}.oraclecloud.com",
            namespace, region
        );
        let s3 = S3CompatProvider::new(
            "oci",
            &endpoint,
            bucket,
            region,
            access_key,
            secret_key,
        );
        Self {
            s3,
            namespace: namespace.to_string(),
            compartment_id: compartment_id.to_string(),
        }
    }
}

#[async_trait]
impl StorageProvider for OCIStorageProvider {
    fn name(&self) -> &str { self.s3.name() }

    async fn write(&self, path: &str, data: Bytes) -> Result<WriteResult, StorageError> {
        self.s3.write(path, data).await
    }

    async fn read(&self, path: &str) -> Result<Bytes, StorageError> {
        self.s3.read(path).await
    }

    async fn delete(&self, path: &str) -> Result<(), StorageError> {
        self.s3.delete(path).await
    }

    async fn health_check(&self) -> bool {
        self.s3.health_check().await
    }

    async fn capacity_bytes(&self) -> (u64, u64) {
        // OCI Always Free: 20GB object storage
        (0, 20 * 1024 * 1024 * 1024)
    }

    fn is_ready(&self) -> bool {
        self.s3.is_ready()
    }
}

/******************************************************************************/
/* Storage Router                                                             */
/*                                                                            */
/* Routes storage operations across multiple backends using the fallback       */
/* chain. Integrates with the CRUSH engine for intelligent placement and      */
/* the adaptive capacity manager for quota enforcement.                       */
/******************************************************************************/

pub struct StorageRouter {
    backends: Vec<Arc<dyn StorageProvider>>,
    fallback_order: Vec<String>,
    crush_engine: Arc<CRUSHEngine>,
}

impl StorageRouter {
    pub fn new(fallback_order: Vec<String>, crush_engine: Arc<CRUSHEngine>) -> Self {
        Self {
            backends: Vec::new(),
            fallback_order,
            crush_engine,
        }
    }

    pub fn add_backend(&mut self, provider: Arc<dyn StorageProvider>) {
        info!("Adding storage backend: {}", provider.name());
        self.backends.push(provider);
    }

    pub fn is_ready(&self) -> bool {
        !self.backends.is_empty()
    }

    fn get_backend(&self, id: &str) -> Option<Arc<dyn StorageProvider>> {
        self.backends.iter().find(|b| b.name() == id).cloned()
    }

    /// Write data using adaptive fallback across providers
    pub async fn adaptive_write(&self, path: &str, data: Bytes) -> Result<WriteResult, StorageError> {
        let mut last_error: Option<StorageError> = None;

        // Try primary provider first (CRUSH-aware)
        for provider_name in &self.fallback_order {
            if let Some(backend) = self.get_backend(provider_name) {
                if !backend.health_check().await {
                    warn!("Backend {} unhealthy, skipping", provider_name);
                    continue;
                }

                // Check capacity
                let (used, limit) = backend.capacity_bytes().await;
                if limit > 0 && used >= limit {
                    warn!("Backend {} at capacity ({:.1}/{:.1} GB)", provider_name, used as f64 / 1e9, limit as f64 / 1e9);
                    continue;
                }

                match backend.write(path, data.clone()).await {
                    Ok(mut result) => {
                        // Enrich with CRUSH placement info
                        let placement = self.crush_engine.place_object(path);
                        let crush_rule = placement.rule_name.clone();
                        result.crush_placement = Some(CrushPlacementInfo {
                            rule_name: placement.rule_name,
                            osd_id: placement.osd_id,
                            weight: placement.weight,
                            primary: true,
                        });
                        info!("Wrote {} to {} (CRUSH rule: {})", path, provider_name, crush_rule);
                        return Ok(result);
                    }
                    Err(e) => {
                        warn!("Write to {} failed: {:?}", provider_name, e);
                        last_error = Some(e);
                    }
                }
            }
        }

        // Fallback to local if all cloud backends fail
        if let Some(local) = self.get_backend("local") {
            match local.write(path, data).await {
                Ok(result) => {
                    warn!("Fallback: wrote {} to local storage", path);
                    return Ok(result);
                }
                Err(e) => last_error = Some(e),
            }
        }

        Err(last_error.unwrap_or(StorageError::AllBackendsFailed(
            "No backends available".to_string(),
        )))
    }

    /// Read data using adaptive fallback across providers
    pub async fn adaptive_read(&self, path: &str) -> Result<Bytes, StorageError> {
        for provider_name in &self.fallback_order {
            if let Some(backend) = self.get_backend(provider_name) {
                match backend.read(path).await {
                    Ok(data) => {
                        debug!("Read {} from {}", path, provider_name);
                        return Ok(data);
                    }
                    Err(StorageError::NotFound(_)) => continue,
                    Err(e) => {
                        warn!("Read from {} failed: {:?}", provider_name, e);
                        continue;
                    }
                }
            }
        }

        Err(StorageError::NotFound(path.to_string()))
    }

    /// Get fallback chain status
    pub fn fallback_status(&self) -> serde_json::Value {
        let status: Vec<serde_json::Value> = self.fallback_order
            .iter()
            .map(|name| {
                let backend = self.get_backend(name);
                serde_json::json!({
                    "provider": name,
                    "registered": backend.is_some(),
                })
            })
            .collect();

        serde_json::json!({
            "fallback_order": self.fallback_order,
            "backends": status,
            "total_backends": self.backends.len(),
        })
    }

    pub fn crush_engine(&self) -> &Arc<CRUSHEngine> {
        &self.crush_engine
    }
}

/******************************************************************************/
/* Crypto Helpers (also used by hsm.rs)                                       */
/******************************************************************************/

/// SHA-256 hash of data, returned as hex string
pub fn sha256_hash(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

/// SHA-256 hash returning hex string
pub fn sha256_hex(data: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data.as_bytes());
    hex::encode(hasher.finalize())
}

/// HMAC-SHA256 returning raw bytes
pub fn hmac_sha256(key: &[u8], data: &[u8]) -> Vec<u8> {
    type HmacSha256 = Hmac<Sha256>;
    let mut mac = HmacSha256::new_from_slice(key).expect("HMAC key error");
    mac.update(data);
    mac.finalize().into_bytes().to_vec()
}

/// HMAC-SHA256 returning hex string
pub fn hmac_sha256_hex(key: &[u8], data: &str) -> String {
    hex::encode(hmac_sha256(key, data.as_bytes()))
}

/// Derive AWS Signature Version 4 signing key
fn derive_signing_key(secret_key: &str, date_stamp: &str, region: &str, service: &str) -> Vec<u8> {
    let k_date = hmac_sha256(format!("AWS4{}", secret_key).as_bytes(), date_stamp.as_bytes());
    let k_region = hmac_sha256(&k_date, region.as_bytes());
    let k_service = hmac_sha256(&k_region, service.as_bytes());
    hmac_sha256(&k_service, b"aws4_request")
}

/// URL-encode a string component (simple version for S3 keys)
fn urlencoding_encode(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '_' | '-' | '~' | '.' | '/' => c.to_string(),
            _ => format!("%{:02X}", c as u8),
        })
        .collect()
}

/// Empty payload SHA-256 hash (for GET/DELETE requests)
const EMPTY_SHA256: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
