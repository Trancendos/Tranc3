//! PKCS#11 HSM Integration Module for Tranc3 Nanoservice
//!
//! Provides hardware-backed cryptographic operations via PKCS#11 interface.
//! Supports SoftHSM2 for development and YubiHSM2 for production deployments.
//! All key operations are performed inside the HSM boundary — private key
//! material never leaves the token.

use cryptoki::context::{CInitializeArgs, Pkcs11};
use cryptoki::error::Error as Pkcs11Error;
use cryptoki::object::{Attribute, AttributeInfo, AttributeType, ObjectClass};
use cryptoki::session::{UserType, Session};
use cryptoki::slot::Slot;
use cryptoki::types::AuthPin;
use cryptoki::mechanism::Mechanism;
use cryptoki::mechanism::rsa::{PkcsMgfType, PkcsPssParams};
use cryptoki::object::KeyType;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_SOFTHSM_MODULE: &str = "/usr/lib/softhsm/libsofthsm2.so";
const DEFAULT_YUBIHSM_MODULE: &str = "/usr/lib/yubihsm/libyubihsm_pkcs11.so";
const DEFAULT_TOKEN_LABEL: &str = "tranc3-hsm";
const DEFAULT_PIN: &str = "tranc3-hsm-pin";
const DEFAULT_SO_PIN: &str = "tranc3-hsm-so-pin";
const KEY_LABEL_PREFIX: &str = "tranc3-key-";

/// HSM provider type — determines which PKCS#11 module to load
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HsmProviderType {
    SoftHsm2,
    YubiHsm2,
    Custom(String),
    Disabled,
}

impl Default for HsmProviderType {
    fn default() -> Self {
        match std::env::var("TRANC3_HSM_PROVIDER")
            .unwrap_or_else(|_| "softhsm2".to_string())
            .to_lowercase()
            .as_str()
        {
            "softhsm2" | "soft" => HsmProviderType::SoftHsm2,
            "yubihsm2" | "yubi" => HsmProviderType::YubiHsm2,
            "disabled" | "off" | "none" => HsmProviderType::Disabled,
            path if path.starts_with('/') => HsmProviderType::Custom(path.to_string()),
            _ => HsmProviderType::SoftHsm2,
        }
    }
}

/// HSM configuration — loaded from environment or defaults
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HsmConfig {
    pub provider: HsmProviderType,
    pub module_path: PathBuf,
    pub token_label: String,
    pub pin: String,
    pub so_pin: String,
    pub session_pool_size: usize,
    #[serde(skip)]
    pub key_id_counter_next: u64,
}

impl Default for HsmConfig {
    fn default() -> Self {
        let provider = HsmProviderType::default();
        let module_path = match &provider {
            HsmProviderType::SoftHsm2 => PathBuf::from(
                std::env::var("TRANC3_HSM_MODULE")
                    .unwrap_or_else(|_| DEFAULT_SOFTHSM_MODULE.to_string()),
            ),
            HsmProviderType::YubiHsm2 => PathBuf::from(
                std::env::var("TRANC3_HSM_MODULE")
                    .unwrap_or_else(|_| DEFAULT_YUBIHSM_MODULE.to_string()),
            ),
            HsmProviderType::Custom(path) => PathBuf::from(path),
            HsmProviderType::Disabled => PathBuf::from("/dev/null"),
        };
        Self {
            provider,
            module_path,
            token_label: std::env::var("TRANC3_HSM_TOKEN_LABEL")
                .unwrap_or_else(|_| DEFAULT_TOKEN_LABEL.to_string()),
            pin: std::env::var("TRANC3_HSM_PIN")
                .unwrap_or_else(|_| DEFAULT_PIN.to_string()),
            so_pin: std::env::var("TRANC3_HSM_SO_PIN")
                .unwrap_or_else(|_| DEFAULT_SO_PIN.to_string()),
            session_pool_size: std::env::var("TRANC3_HSM_SESSION_POOL_SIZE")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(4),
            key_id_counter_next: 1,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Key Types & Metadata
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum KeyPurpose {
    DataEncryption,
    RequestSigning,
    TlsIdentity,
    CrushMapSigning,
    GenericSecret,
}

impl KeyPurpose {
    fn label_suffix(&self) -> &str {
        match self {
            KeyPurpose::DataEncryption => "enc",
            KeyPurpose::RequestSigning => "sig",
            KeyPurpose::TlsIdentity => "tls",
            KeyPurpose::CrushMapSigning => "crush",
            KeyPurpose::GenericSecret => "gen",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyMetadata {
    pub key_id: u64,
    pub label: String,
    pub purpose: KeyPurpose,
    pub algorithm: String,
    pub key_size_bits: usize,
    pub created_at: String,
    pub extractable: bool,
    pub persistent: bool,
}

// ─────────────────────────────────────────────────────────────────────────────
// HSM Operation Results
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum HsmError {
    #[error("HSM is disabled — operation not available")]
    Disabled,
    #[error("PKCS#11 module not found at {path}: {reason}")]
    ModuleNotFound { path: String, reason: String },
    #[error("Failed to initialize PKCS#11 context: {0}")]
    InitFailed(String),
    #[error("No slot available with token label '{label}'")]
    SlotNotFound { label: String },
    #[error("Login failed: {0}")]
    LoginFailed(String),
    #[error("Key not found: {label}")]
    KeyNotFound { label: String },
    #[error("Object not found with ID {id}")]
    ObjectNotFound { id: u64 },
    #[error("Encryption error: {0}")]
    EncryptionError(String),
    #[error("Decryption error: {0}")]
    DecryptionError(String),
    #[error("Signing error: {0}")]
    SigningError(String),
    #[error("Verification error: {0}")]
    VerificationError(String),
    #[error("Key generation failed: {0}")]
    KeyGenerationFailed(String),
    #[error("Session pool exhausted")]
    SessionPoolExhausted,
    #[error("PKCS#11 error: {0}")]
    Pkcs11(#[from] Pkcs11Error),
    #[error("Internal error: {0}")]
    Internal(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeyGenResult {
    pub key_id: u64,
    pub label: String,
    pub purpose: KeyPurpose,
    pub algorithm: String,
    pub key_size_bits: usize,
}

#[derive(Debug, Clone)]
pub struct EncryptResult {
    pub ciphertext: Vec<u8>,
    pub iv: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct DecryptResult {
    pub plaintext: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct SignResult {
    pub signature: Vec<u8>,
    pub algorithm: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerifyResult {
    Valid,
    Invalid,
}

// ─────────────────────────────────────────────────────────────────────────────
// HSM Engine — Main Interface
// ─────────────────────────────────────────────────────────────────────────────

pub struct HsmEngine {
    config: HsmConfig,
    pkcs11: Arc<Mutex<Option<Pkcs11>>>,
    slot: Arc<Mutex<Option<Slot>>>,
    initialized: Arc<Mutex<bool>>,
    key_id_counter: Arc<Mutex<u64>>,
}

impl HsmEngine {
    pub fn new(config: HsmConfig) -> Self {
        let start = config.key_id_counter_next;
        Self {
            config,
            pkcs11: Arc::new(Mutex::new(None)),
            slot: Arc::new(Mutex::new(None)),
            initialized: Arc::new(Mutex::new(false)),
            key_id_counter: Arc::new(Mutex::new(start)),
        }
    }

    pub fn from_env() -> Self {
        Self::new(HsmConfig::default())
    }

    pub fn disabled() -> Self {
        Self::new(HsmConfig {
            provider: HsmProviderType::Disabled,
            ..HsmConfig::default()
        })
    }

    /// Initialize the PKCS#11 context and find the slot
    pub async fn initialize(&self) -> Result<(), HsmError> {
        if self.config.provider == HsmProviderType::Disabled {
            warn!("HSM is disabled — cryptographic operations will not be available");
            return Ok(());
        }

        let module_path = self.config.module_path.clone();
        if !module_path.exists() {
            return Err(HsmError::ModuleNotFound {
                path: module_path.display().to_string(),
                reason: "File does not exist".to_string(),
            });
        }

        info!(
            provider = ?self.config.provider,
            module = %module_path.display(),
            "Initializing PKCS#11 HSM context"
        );

        let pkcs11 = Pkcs11::new(&module_path).map_err(|e| {
            HsmError::InitFailed(format!("Failed to load module: {}", e))
        })?;

        pkcs11.initialize(CInitializeArgs::OsThreads).map_err(|e| {
            HsmError::InitFailed(format!("C_Initialize failed: {}", e))
        })?;

        let slots = pkcs11.get_slots_with_initialized_token().map_err(|e| {
            HsmError::InitFailed(format!("Failed to enumerate slots: {}", e))
        })?;

        let target_slot = slots.into_iter().find(|slot| {
            if let Ok(info) = pkcs11.get_token_info(*slot) {
                let label = info.label().trim();
                label == self.config.token_label
            } else {
                false
            }
        }).ok_or_else(|| HsmError::SlotNotFound {
            label: self.config.token_label.clone(),
        })?;

        debug!("Found HSM slot with matching token label");

        *self.pkcs11.lock().await = Some(pkcs11);
        *self.slot.lock().await = Some(target_slot);
        *self.initialized.lock().await = true;

        info!("HSM engine initialized successfully");
        Ok(())
    }

    pub async fn is_available(&self) -> bool {
        *self.initialized.lock().await
    }

    pub fn provider_type(&self) -> &HsmProviderType {
        &self.config.provider
    }

    /// Open a new RW session and login
    async fn open_session(&self) -> Result<Session, HsmError> {
        let pkcs11_guard = self.pkcs11.lock().await;
        let pkcs11 = pkcs11_guard.as_ref().ok_or(HsmError::Disabled)?;
        let slot_guard = self.slot.lock().await;
        let slot = slot_guard.as_ref().ok_or(HsmError::Disabled)?;

        // open_rw_session takes Slot by value — we must clone or copy the slot ID
        // Slot is not Copy, so we use slot.id() to reconstruct
        let slot_id = slot.id();
        drop(slot_guard);
        drop(pkcs11_guard);

        // Re-acquire pkcs11 lock and open session
        let pkcs11_guard = self.pkcs11.lock().await;
        let pkcs11 = pkcs11_guard.as_ref().ok_or(HsmError::Disabled)?;

        // Get slots again and find matching one
        let slots = pkcs11.get_slots_with_initialized_token().map_err(|e| {
            HsmError::Internal(format!("Failed to enumerate slots: {}", e))
        })?;
        let slot = slots.into_iter().find(|s| s.id() == slot_id)
            .ok_or_else(|| HsmError::SlotNotFound {
                label: self.config.token_label.clone(),
            })?;

        let session = pkcs11.open_rw_session(slot).map_err(|e| {
            HsmError::Internal(format!("Failed to open session: {}", e))
        })?;

        let pin = AuthPin::new(self.config.pin.clone());
        session.login(UserType::User, Some(&pin)).map_err(|e| {
            HsmError::LoginFailed(format!("Login failed: {}", e))
        })?;

        Ok(session)
    }

    /// Generate an AES key inside the HSM
    pub async fn generate_aes_key(
        &self,
        purpose: KeyPurpose,
        key_size_bits: usize,
    ) -> Result<KeyGenResult, HsmError> {
        self.ensure_available()?;

        let key_id = self.next_key_id().await;
        let label = format!("{}{}-{}", KEY_LABEL_PREFIX, purpose.label_suffix(), key_id);

        info!(key_id, label = %label, key_size = key_size_bits, "Generating AES key in HSM");

        let session = self.open_session().await?;
        let key_size_bytes = key_size_bits / 8;
        let object_id = key_id.to_be_bytes().to_vec();
        let label_bytes = label.as_bytes().to_vec();

        let template = vec![
            Attribute::Class(ObjectClass::SECRET_KEY),
            Attribute::KeyType(KeyType::AES),
            Attribute::ValueLen(cryptoki::types::Ulong::from(key_size_bytes as u64)),
            Attribute::Label(label_bytes),
            Attribute::Id(object_id),
            Attribute::Token(true.into()),
            Attribute::Private(true.into()),
            Attribute::Sensitive(true.into()),
            Attribute::Extractable(false.into()),
            Attribute::NeverExtractable(true.into()),
            Attribute::Encrypt(true.into()),
            Attribute::Decrypt(true.into()),
            Attribute::Wrap(false.into()),
            Attribute::Unwrap(false.into()),
        ];

        let _key_handle = session.generate_key(&Mechanism::AesKeyGen, &template).map_err(|e| {
            HsmError::KeyGenerationFailed(format!("AES key generation failed: {}", e))
        })?;

        session.close();

        info!(key_id, label = %label, "AES key generated successfully in HSM");

        Ok(KeyGenResult {
            key_id,
            label,
            purpose,
            algorithm: "AES".to_string(),
            key_size_bits,
        })
    }

    /// Generate an RSA key pair inside the HSM
    pub async fn generate_rsa_keypair(
        &self,
        purpose: KeyPurpose,
        key_size_bits: usize,
    ) -> Result<KeyGenResult, HsmError> {
        self.ensure_available()?;

        let key_id = self.next_key_id().await;
        let label = format!("{}{}-{}", KEY_LABEL_PREFIX, purpose.label_suffix(), key_id);

        info!(key_id, label = %label, key_size = key_size_bits, "Generating RSA key pair in HSM");

        let session = self.open_session().await?;
        let object_id = key_id.to_be_bytes().to_vec();
        let label_bytes = label.as_bytes().to_vec();

        let public_template = vec![
            Attribute::Class(ObjectClass::PUBLIC_KEY),
            Attribute::KeyType(KeyType::RSA),
            Attribute::Label(label_bytes.clone()),
            Attribute::Id(object_id.clone()),
            Attribute::Token(true.into()),
            Attribute::Encrypt(true.into()),
            Attribute::Verify(true.into()),
            Attribute::Wrap(true.into()),
            Attribute::ModulusBits(cryptoki::types::Ulong::from(key_size_bits as u64)),
        ];

        let private_template = vec![
            Attribute::Class(ObjectClass::PRIVATE_KEY),
            Attribute::KeyType(KeyType::RSA),
            Attribute::Label(label_bytes),
            Attribute::Id(object_id),
            Attribute::Token(true.into()),
            Attribute::Private(true.into()),
            Attribute::Sensitive(true.into()),
            Attribute::Extractable(false.into()),
            Attribute::Decrypt(true.into()),
            Attribute::Sign(true.into()),
            Attribute::Unwrap(true.into()),
        ];

        let (_pub_key, _priv_key) = session
            .generate_key_pair(&Mechanism::RsaPkcsKeyPairGen, &public_template, &private_template)
            .map_err(|e| {
                HsmError::KeyGenerationFailed(format!("RSA key pair generation failed: {}", e))
            })?;

        session.close();

        info!(key_id, label = %label, "RSA key pair generated successfully in HSM");

        Ok(KeyGenResult {
            key_id,
            label,
            purpose,
            algorithm: "RSA".to_string(),
            key_size_bits,
        })
    }

    /// Encrypt data using an AES key stored in the HSM
    pub async fn encrypt(
        &self,
        key_id: u64,
        plaintext: &[u8],
        mechanism: &str,
    ) -> Result<EncryptResult, HsmError> {
        self.ensure_available()?;

        debug!(key_id, mechanism, data_len = plaintext.len(), "Encrypting data via HSM");

        let session = self.open_session().await?;
        let key_handle = self.find_key_by_id(&session, key_id)?;

        let iv = rand_iv();
        let mech = match mechanism {
            "ecb" => Mechanism::AesEcb,
            _ => Mechanism::AesCbcPad(iv),
        };

        let ciphertext = session.encrypt(&mech, key_handle, plaintext).map_err(|e| {
            HsmError::EncryptionError(format!("Encryption failed: {}", e))
        })?;

        session.close();

        Ok(EncryptResult {
            ciphertext,
            iv: iv.to_vec(),
        })
    }

    /// Decrypt data using an AES key stored in the HSM
    pub async fn decrypt(
        &self,
        key_id: u64,
        ciphertext: &[u8],
        iv: &[u8],
        mechanism: &str,
    ) -> Result<DecryptResult, HsmError> {
        self.ensure_available()?;

        debug!(key_id, mechanism, data_len = ciphertext.len(), "Decrypting data via HSM");

        let session = self.open_session().await?;
        let key_handle = self.find_key_by_id(&session, key_id)?;

        let mech = if mechanism == "ecb" {
            Mechanism::AesEcb
        } else {
            let mut iv_arr = [0u8; 16];
            iv_arr.copy_from_slice(&iv[..16.min(iv.len())]);
            Mechanism::AesCbcPad(iv_arr)
        };

        let plaintext = session.decrypt(&mech, key_handle, ciphertext).map_err(|e| {
            HsmError::DecryptionError(format!("Decryption failed: {}", e))
        })?;

        session.close();

        Ok(DecryptResult { plaintext })
    }

    /// Sign data using a key stored in the HSM
    pub async fn sign(
        &self,
        key_id: u64,
        data: &[u8],
        mechanism: &str,
    ) -> Result<SignResult, HsmError> {
        self.ensure_available()?;

        debug!(key_id, mechanism, data_len = data.len(), "Signing data via HSM");

        let session = self.open_session().await?;
        let key_handle = self.find_key_by_id(&session, key_id)?;

        let mech = match mechanism {
            "sha256" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA256_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA256,
                s_len: cryptoki::types::Ulong::from(32u64),
            }),
            "sha384" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA384_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA384,
                s_len: cryptoki::types::Ulong::from(48u64),
            }),
            "sha512" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA512_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA512,
                s_len: cryptoki::types::Ulong::from(64u64),
            }),
            _ => Mechanism::RsaPkcs,
        };

        let signature = session.sign(&mech, key_handle, data).map_err(|e| {
            HsmError::SigningError(format!("Signing failed: {}", e))
        })?;

        session.close();

        Ok(SignResult {
            signature,
            algorithm: mechanism.to_string(),
        })
    }

    /// Verify a signature using a key stored in the HSM
    pub async fn verify(
        &self,
        key_id: u64,
        data: &[u8],
        signature: &[u8],
        mechanism: &str,
    ) -> Result<VerifyResult, HsmError> {
        self.ensure_available()?;

        debug!(key_id, mechanism, data_len = data.len(), "Verifying signature via HSM");

        let session = self.open_session().await?;
        let key_handle = self.find_key_by_id(&session, key_id)?;

        let mech = match mechanism {
            "sha256" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA256_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA256,
                s_len: cryptoki::types::Ulong::from(32u64),
            }),
            "sha384" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA384_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA384,
                s_len: cryptoki::types::Ulong::from(48u64),
            }),
            "sha512" => Mechanism::RsaPkcsPss(PkcsPssParams {
                hash_alg: cryptoki::mechanism::MechanismType::SHA512_RSA_PKCS,
                mgf: PkcsMgfType::MGF1_SHA512,
                s_len: cryptoki::types::Ulong::from(64u64),
            }),
            _ => Mechanism::RsaPkcs,
        };

        let result = session.verify(&mech, key_handle, data, signature);
        session.close();

        match result {
            Ok(()) => Ok(VerifyResult::Valid),
            Err(Pkcs11Error::Pkcs11(rv, _function)) => {
                match rv {
                    cryptoki::error::RvError::SignatureInvalid
                    | cryptoki::error::RvError::SignatureLenRange => Ok(VerifyResult::Invalid),
                    e => Err(HsmError::VerificationError(format!("Verification failed: {}", e))),
                }
            }
            Err(e) => Err(HsmError::VerificationError(format!("Verification failed: {}", e))),
        }
    }

    fn find_key_by_id(
        &self,
        session: &Session,
        key_id: u64,
    ) -> Result<cryptoki::object::ObjectHandle, HsmError> {
        let id_bytes = key_id.to_be_bytes().to_vec();
        let template = vec![Attribute::Id(id_bytes)];

        let objects = session.find_objects(&template).map_err(|_e| {
            HsmError::ObjectNotFound { id: key_id }
        })?;

        objects.into_iter().next().ok_or_else(|| {
            HsmError::KeyNotFound {
                label: format!("key-{}", key_id),
            }
        })
    }

    /// List all keys in the HSM token
    pub async fn list_keys(&self) -> Result<Vec<KeyMetadata>, HsmError> {
        self.ensure_available()?;

        let session = self.open_session().await?;

        let template = vec![
            Attribute::Class(ObjectClass::SECRET_KEY),
            Attribute::Token(true.into()),
        ];

        let objects = session.find_objects(&template).map_err(|e| {
            HsmError::Internal(format!("Failed to list keys: {}", e))
        })?;

        let mut keys = Vec::new();
        for obj in objects {
            let label = session
                .get_attributes(obj, &[AttributeType::Label])
                .ok()
                .and_then(|vals| {
                    vals.into_iter().next().and_then(|attr| {
                        if let Attribute::Label(bytes) = attr {
                            Some(String::from_utf8_lossy(&bytes).to_string())
                        } else {
                            None
                        }
                    })
                })
                .unwrap_or_else(|| "<unknown>".to_string());

            let id = session
                .get_attributes(obj, &[AttributeType::Id])
                .ok()
                .and_then(|vals| {
                    vals.into_iter().next().and_then(|attr| {
                        if let Attribute::Id(bytes) = attr {
                            if bytes.len() == 8 {
                                let mut arr = [0u8; 8];
                                arr.copy_from_slice(&bytes);
                                Some(u64::from_be_bytes(arr))
                            } else {
                                None
                            }
                        } else {
                            None
                        }
                    })
                })
                .unwrap_or(0);

            keys.push(KeyMetadata {
                key_id: id,
                label,
                purpose: KeyPurpose::GenericSecret,
                algorithm: "AES".to_string(),
                key_size_bits: 256,
                created_at: chrono::Utc::now().to_rfc3339(),
                extractable: false,
                persistent: true,
            });
        }

        session.close();
        Ok(keys)
    }

    /// Destroy a key by its ID
    pub async fn destroy_key(&self, key_id: u64) -> Result<(), HsmError> {
        self.ensure_available()?;

        info!(key_id, "Destroying key in HSM");

        let session = self.open_session().await?;
        let key_handle = self.find_key_by_id(&session, key_id)?;
        session.destroy_object(key_handle).map_err(|e| {
            HsmError::Internal(format!("Failed to destroy key: {}", e))
        })?;

        session.close();

        info!(key_id, "Key destroyed successfully");
        Ok(())
    }

    /// Get health status of the HSM
    pub async fn health_check(&self) -> HsmHealthStatus {
        let available = self.is_available().await;
        let provider = self.config.provider.clone();

        if !available {
            return HsmHealthStatus {
                available: false,
                provider: format!("{:?}", provider),
                slot_count: 0,
                session_pool_available: 0,
                error: Some("HSM not initialized or disabled".to_string()),
            };
        }

        HsmHealthStatus {
            available: true,
            provider: format!("{:?}", provider),
            slot_count: 1,
            session_pool_available: self.config.session_pool_size,
            error: None,
        }
    }

    fn ensure_available(&self) -> Result<(), HsmError> {
        if self.config.provider == HsmProviderType::Disabled {
            return Err(HsmError::Disabled);
        }
        Ok(())
    }

    async fn next_key_id(&self) -> u64 {
        let mut counter = self.key_id_counter.lock().await;
        let id = *counter;
        *counter += 1;
        id
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HsmHealthStatus {
    pub available: bool,
    pub provider: String,
    pub slot_count: usize,
    pub session_pool_available: usize,
    pub error: Option<String>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility Functions
// ─────────────────────────────────────────────────────────────────────────────

fn rand_iv() -> [u8; 16] {
    use std::time::{SystemTime, UNIX_EPOCH};
    let seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64;

    let mut iv = [0u8; 16];
    let mut state = seed;
    for byte in iv.iter_mut() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        *byte = (state & 0xFF) as u8;
    }
    iv
}

/// Derive a key encryption key context from a master key ID and namespace
pub fn derive_kek_context(key_id: u64, namespace: &str) -> Vec<u8> {
    let context = format!("tranc3-kek:{}:{}", key_id, namespace);
    crate::storage::sha256_hash(context.as_bytes()).into_bytes()
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hsm_provider_type_default() {
        std::env::remove_var("TRANC3_HSM_PROVIDER");
        let provider = HsmProviderType::default();
        assert!(matches!(provider, HsmProviderType::SoftHsm2));
    }

    #[test]
    fn test_hsm_config_default() {
        let config = HsmConfig::default();
        assert_eq!(config.token_label, "tranc3-hsm");
        assert_eq!(config.session_pool_size, 4);
    }

    #[test]
    fn test_key_purpose_label_suffix() {
        assert_eq!(KeyPurpose::DataEncryption.label_suffix(), "enc");
        assert_eq!(KeyPurpose::RequestSigning.label_suffix(), "sig");
        assert_eq!(KeyPurpose::TlsIdentity.label_suffix(), "tls");
        assert_eq!(KeyPurpose::CrushMapSigning.label_suffix(), "crush");
        assert_eq!(KeyPurpose::GenericSecret.label_suffix(), "gen");
    }

    #[test]
    fn test_disabled_engine() {
        let engine = HsmEngine::disabled();
        assert_eq!(engine.provider_type(), &HsmProviderType::Disabled);
    }

    #[tokio::test]
    async fn test_disabled_engine_health_check() {
        let engine = HsmEngine::disabled();
        let health = engine.health_check().await;
        assert!(!health.available);
    }

    #[test]
    fn test_rand_iv_length() {
        let iv = rand_iv();
        assert_eq!(iv.len(), 16);
    }

    #[test]
    fn test_derive_kek_context() {
        let ctx = derive_kek_context(42, "test-namespace");
        assert_eq!(ctx.len(), 32);
        let ctx2 = derive_kek_context(42, "test-namespace");
        assert_eq!(ctx, ctx2);
        let ctx3 = derive_kek_context(43, "test-namespace");
        assert_ne!(ctx, ctx3);
    }

    #[test]
    fn test_hsm_health_status_serialization() {
        let status = HsmHealthStatus {
            available: true,
            provider: "SoftHsm2".to_string(),
            slot_count: 1,
            session_pool_available: 3,
            error: None,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("SoftHsm2"));
    }
}
