/*
 * tranc3_crypto — Memory-safe, constant-time AES-256-GCM crypto nanoservice
 *
 * Replaces the Python cryptography-library hot path for The Void (infinity-void)
 * with a Rust implementation that:
 *   - Never leaks key material through Python GIL or memory copies
 *   - Uses zeroize::Zeroize to wipe key bytes on drop
 *   - Is constant-time via the aes-gcm crate (hardware AES when available)
 *   - Derives keys with PBKDF2-HMAC-SHA256 (100k iterations) and HKDF-SHA256
 *
 * Python API:
 *   tranc3_crypto.encrypt(plaintext: bytes, key_seed: str) -> bytes
 *   tranc3_crypto.decrypt(ciphertext: bytes, key_seed: str) -> bytes
 *   tranc3_crypto.derive_key_pbkdf2(seed: str, salt: bytes) -> bytes
 *   tranc3_crypto.derive_key_hkdf(seed: bytes, salt: bytes, info: bytes) -> bytes
 *   tranc3_crypto.hmac_sha256(key: bytes, data: bytes) -> bytes
 *   tranc3_crypto.constant_time_eq(a: bytes, b: bytes) -> bool
 */

use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Key, Nonce,
};
use hkdf::Hkdf;
use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyBytes;
use rand::RngCore;
use sha2::Sha256;
use zeroize::ZeroizeOnDrop;

// ---------------------------------------------------------------------------
// Key derivation helpers
// ---------------------------------------------------------------------------

#[derive(ZeroizeOnDrop)]
struct KeyMaterial([u8; 32]);

fn pbkdf2_derive(seed: &str, salt: &[u8]) -> KeyMaterial {
    let mut key = KeyMaterial([0u8; 32]);
    pbkdf2_hmac::<Sha256>(seed.as_bytes(), salt, 100_000, &mut key.0);
    key
}

fn hkdf_derive(seed: &[u8], salt: &[u8], info: &[u8]) -> KeyMaterial {
    let hk = Hkdf::<Sha256>::new(Some(salt), seed);
    let mut key = KeyMaterial([0u8; 32]);
    hk.expand(info, &mut key.0).expect("HKDF expand failed");
    key
}

// ---------------------------------------------------------------------------
// Wire format: SALT(32) ++ NONCE(12) ++ CIPHERTEXT_WITH_TAG
// Matches the Python vault-service format (hex-encoded variant uses same layout).
// ---------------------------------------------------------------------------

const SALT_LEN: usize = 32;
const NONCE_LEN: usize = 12;
const MIN_CT_LEN: usize = SALT_LEN + NONCE_LEN + 16; // 16 = GCM auth tag

fn pack(salt: &[u8; SALT_LEN], nonce: &[u8; NONCE_LEN], ct: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(SALT_LEN + NONCE_LEN + ct.len());
    out.extend_from_slice(salt);
    out.extend_from_slice(nonce);
    out.extend_from_slice(ct);
    out
}

fn unpack(data: &[u8]) -> PyResult<(&[u8; SALT_LEN], &[u8; NONCE_LEN], &[u8])> {
    if data.len() < MIN_CT_LEN {
        return Err(PyValueError::new_err("tranc3_crypto: ciphertext too short — corrupted"));
    }
    let salt: &[u8; SALT_LEN] = data[..SALT_LEN].try_into().unwrap();
    let nonce: &[u8; NONCE_LEN] = data[SALT_LEN..SALT_LEN + NONCE_LEN].try_into().unwrap();
    Ok((salt, nonce, &data[SALT_LEN + NONCE_LEN..]))
}

// ---------------------------------------------------------------------------
// Python-exposed functions
// ---------------------------------------------------------------------------

#[pyfunction]
fn encrypt(py: Python<'_>, plaintext: &[u8], key_seed: &str) -> PyResult<PyObject> {
    let mut salt = [0u8; SALT_LEN];
    OsRng.fill_bytes(&mut salt);
    let key_mat = pbkdf2_derive(key_seed, &salt);
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&key_mat.0));
    let mut nonce_bytes = [0u8; NONCE_LEN];
    OsRng.fill_bytes(&mut nonce_bytes);
    let ct = cipher
        .encrypt(Nonce::from_slice(&nonce_bytes), plaintext)
        .map_err(|e| PyValueError::new_err(format!("AES-GCM encrypt: {e}")))?;
    Ok(PyBytes::new_bound(py, &pack(&salt, &nonce_bytes, &ct)).into())
}

#[pyfunction]
fn decrypt(py: Python<'_>, ciphertext: &[u8], key_seed: &str) -> PyResult<PyObject> {
    let (salt, nonce_bytes, ct) = unpack(ciphertext)?;
    let key_mat = pbkdf2_derive(key_seed, salt);
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&key_mat.0));
    let pt = cipher
        .decrypt(Nonce::from_slice(nonce_bytes), ct)
        .map_err(|_| PyValueError::new_err("AES-GCM decrypt failed — bad key or corrupted data"))?;
    Ok(PyBytes::new_bound(py, &pt).into())
}

#[pyfunction]
fn derive_key_pbkdf2(py: Python<'_>, seed: &str, salt: &[u8]) -> PyResult<PyObject> {
    let key = pbkdf2_derive(seed, salt);
    Ok(PyBytes::new_bound(py, &key.0).into())
}

#[pyfunction]
fn derive_key_hkdf(py: Python<'_>, seed: &[u8], salt: &[u8], info: &[u8]) -> PyResult<PyObject> {
    let key = hkdf_derive(seed, salt, info);
    Ok(PyBytes::new_bound(py, &key.0).into())
}

#[pyfunction]
fn hmac_sha256(py: Python<'_>, key: &[u8], data: &[u8]) -> PyResult<PyObject> {
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(key)
        .map_err(|e| PyValueError::new_err(format!("HMAC key: {e}")))?;
    mac.update(data);
    Ok(PyBytes::new_bound(py, &mac.finalize().into_bytes()).into())
}

#[pyfunction]
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    use subtle::ConstantTimeEq;
    a.ct_eq(b).into()
}

// ---------------------------------------------------------------------------
// Module
// ---------------------------------------------------------------------------

#[pymodule]
fn tranc3_crypto(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(encrypt, m)?)?;
    m.add_function(wrap_pyfunction!(decrypt, m)?)?;
    m.add_function(wrap_pyfunction!(derive_key_pbkdf2, m)?)?;
    m.add_function(wrap_pyfunction!(derive_key_hkdf, m)?)?;
    m.add_function(wrap_pyfunction!(hmac_sha256, m)?)?;
    m.add_function(wrap_pyfunction!(constant_time_eq, m)?)?;
    m.add("__version__", "0.1.0")?;
    m.add("__doc__", "Memory-safe AES-256-GCM crypto nanoservice (Rust/PyO3)")?;
    Ok(())
}
