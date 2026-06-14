/// vault_crypto — PyO3 Rust extension for AES-256-GCM encryption used by The Void.
///
/// All key material is zeroed after use via the `zeroize` crate.
/// Output format for `encrypt`: hex(salt[32] || iv[12] || tag[16] || ciphertext)
use aes_gcm::{
    aead::{Aead, KeyInit, OsRng as AeadOsRng},
    Aes256Gcm, Key, Nonce,
};
use pbkdf2::pbkdf2_hmac;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rand::RngCore;
use sha2::Sha256;
use zeroize::Zeroizing;

const PBKDF2_ITERATIONS: u32 = 100_000;
const SALT_LEN: usize = 32;
const IV_LEN: usize = 12;
const TAG_LEN: usize = 16;
const KEY_LEN: usize = 32;

/// Derive a 256-bit key from `password` and `salt` using PBKDF2-HMAC-SHA256.
fn derive_key_internal(password: &[u8], salt: &[u8]) -> Zeroizing<[u8; KEY_LEN]> {
    let mut key = Zeroizing::new([0u8; KEY_LEN]);
    pbkdf2_hmac::<Sha256>(password, salt, PBKDF2_ITERATIONS, key.as_mut());
    key
}

/// encrypt(plaintext, master_key_hex) -> hex string
///
/// Generates a random 32-byte salt and 12-byte IV, derives a key via PBKDF2-HMAC-SHA256
/// (100 000 iterations), then AES-256-GCM encrypts `plaintext`.
///
/// Returns: hex(salt[32] || iv[12] || tag[16] || ciphertext)
#[pyfunction]
fn encrypt(plaintext: &str, master_key_hex: &str) -> PyResult<String> {
    let master_key_bytes = Zeroizing::new(
        hex::decode(master_key_hex)
            .map_err(|e| PyValueError::new_err(format!("invalid master_key_hex: {e}")))?,
    );
    if master_key_bytes.is_empty() {
        return Err(PyValueError::new_err("master_key_hex must not be empty"));
    }

    // Random salt + IV
    let mut salt = [0u8; SALT_LEN];
    let mut iv_bytes = [0u8; IV_LEN];
    rand::thread_rng().fill_bytes(&mut salt);
    rand::thread_rng().fill_bytes(&mut iv_bytes);

    // Derive key
    let key_material = derive_key_internal(master_key_bytes.as_ref(), &salt);
    let key = Key::<Aes256Gcm>::from_slice(key_material.as_ref());
    let cipher = Aes256Gcm::new(key);
    let nonce = Nonce::from_slice(&iv_bytes);

    // Encrypt — AES-GCM appends the 16-byte tag to ciphertext
    let ciphertext_with_tag = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|e| PyValueError::new_err(format!("encryption failed: {e}")))?;

    // Layout: salt || iv || tag || ciphertext
    // aes-gcm appends tag at the END of ciphertext_with_tag
    let ct_len = ciphertext_with_tag.len() - TAG_LEN;
    let (ct, tag) = ciphertext_with_tag.split_at(ct_len);

    let mut out = Vec::with_capacity(SALT_LEN + IV_LEN + TAG_LEN + ct_len);
    out.extend_from_slice(&salt);
    out.extend_from_slice(&iv_bytes);
    out.extend_from_slice(tag);
    out.extend_from_slice(ct);

    Ok(hex::encode(out))
}

/// decrypt(ciphertext_hex, master_key_hex) -> plaintext string
///
/// Expects the output format produced by `encrypt`.
#[pyfunction]
fn decrypt(ciphertext_hex: &str, master_key_hex: &str) -> PyResult<String> {
    let master_key_bytes = Zeroizing::new(
        hex::decode(master_key_hex)
            .map_err(|e| PyValueError::new_err(format!("invalid master_key_hex: {e}")))?,
    );
    if master_key_bytes.is_empty() {
        return Err(PyValueError::new_err("master_key_hex must not be empty"));
    }
    let blob =
        hex::decode(ciphertext_hex).map_err(|e| PyValueError::new_err(format!("invalid ciphertext_hex: {e}")))?;

    let min_len = SALT_LEN + IV_LEN + TAG_LEN;
    if blob.len() < min_len {
        return Err(PyValueError::new_err(format!(
            "ciphertext too short: expected at least {min_len} bytes, got {}",
            blob.len()
        )));
    }

    let salt = &blob[..SALT_LEN];
    let iv_bytes = &blob[SALT_LEN..SALT_LEN + IV_LEN];
    let tag = &blob[SALT_LEN + IV_LEN..SALT_LEN + IV_LEN + TAG_LEN];
    let ct = &blob[SALT_LEN + IV_LEN + TAG_LEN..];

    // Derive key
    let key_material = derive_key_internal(master_key_bytes.as_ref(), salt);
    let key = Key::<Aes256Gcm>::from_slice(key_material.as_ref());
    let cipher = Aes256Gcm::new(key);
    let nonce = Nonce::from_slice(iv_bytes);

    // Re-assemble ciphertext||tag as aes-gcm expects
    let mut ct_with_tag = Vec::with_capacity(ct.len() + TAG_LEN);
    ct_with_tag.extend_from_slice(ct);
    ct_with_tag.extend_from_slice(tag);

    let plaintext_bytes = cipher
        .decrypt(nonce, ct_with_tag.as_ref())
        .map_err(|e| PyValueError::new_err(format!("decryption failed (bad key or tampered data): {e}")))?;

    String::from_utf8(plaintext_bytes)
        .map_err(|e| PyValueError::new_err(format!("plaintext is not valid UTF-8: {e}")))
}

/// derive_key(password, salt_hex) -> hex-encoded 32-byte key
///
/// Standalone PBKDF2-HMAC-SHA256 key derivation (100 000 iterations).
#[pyfunction]
fn derive_key(password: &str, salt_hex: &str) -> PyResult<String> {
    let salt =
        hex::decode(salt_hex).map_err(|e| PyValueError::new_err(format!("invalid salt_hex: {e}")))?;
    let key = derive_key_internal(password.as_bytes(), &salt);
    Ok(hex::encode(key.as_ref()))
}

/// vault_crypto Python module
#[pymodule]
fn vault_crypto(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encrypt, m)?)?;
    m.add_function(wrap_pyfunction!(decrypt, m)?)?;
    m.add_function(wrap_pyfunction!(derive_key, m)?)?;
    m.add("__version__", "0.1.0")?;
    Ok(())
}
