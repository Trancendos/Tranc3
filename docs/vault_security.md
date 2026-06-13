# Vault Security Implementation — Tranc3 Ecosystem

## Overview

The Tranc3 Vault Security layer provides defense-in-depth secret management with memory zeroization, Hardware Security Module (HSM) integration, and append-only audit logging. The implementation follows the zero-cost mandate by using self-hosted solutions exclusively.

## Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                    Vault Security Layer                        │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ SecretLoader │  │  HSM Module  │  │ AuditLogger  │        │
│  │ (zeroize)    │  │ (PKCS#11)    │  │ (chain)      │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                 │                  │                │
│  ┌──────┴─────────────────┴──────────────────┴───────┐        │
│  │              SecureBytes (zeroize on del)          │        │
│  │  mlock() · explicit_bzero() · constant-time cmp   │        │
│  └───────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```python

## Components

### 1. SecureBytes — Self-Zeroizing Secure Container

A byte container that automatically zeroizes its memory contents when deleted or when leaving a context manager scope.

**Features:**
- Automatic memory zeroization via `explicit_bzero()` (Linux/glibc) or `memset_s` (C11)
- Optional `mlock()` to prevent memory from being swapped to disk
- Constant-time comparison via `hmac.compare_digest()` to prevent timing attacks
- Thread-safe with internal locking
- Context manager support for guaranteed cleanup

**Usage:**
```python
from Dimensional.architecture.vault_security import SecureBytes

# Context manager — auto-zeroize on exit
with SecureBytes(b"sensitive_data", lock_memory=True) as secret:
    data = secret.reveal()
    # Use data...
# Memory is now zeroized

# Manual zeroization
secret = SecureBytes(b"sensitive_data")
# Use secret...
del secret  # Memory zeroized in __del__
```python

### 2. VaultSecretLoader — Secure Secret Retrieval

Loads secrets from multiple sources with automatic memory zeroization. The context manager pattern ensures secrets are zeroized even if an exception occurs.

**Secret Sources (priority order):**
1. **Environment variables** — for container deployments (Kubernetes, Docker)
2. **`.env` files** — for local development
3. **Infinity Void vault** — self-hosted encrypted secrets service (AES-256-GCM + SQLite)
4. **HSM-encrypted files** — secrets encrypted by HSM keys on disk

**Usage:**
```python
from Dimensional.architecture.vault_security import VaultSecretLoader, SoftHSM2Provider

loader = VaultSecretLoader(
    hsm_provider=SoftHSM2Provider(token="tranc3", pin="123456"),
    infinity_void_url="http://infinity-void:8002",
    infinity_void_secret="internal-dev-secret",
    lock_memory=True,
)

# Load a single secret — auto-zeroize after use
async with loader.secret("DATABASE_URL") as secret:
    db_url = secret.reveal().decode()
    # Use db_url...
# secret memory is now zeroized

# Load multiple secrets at once
async with loader.secrets(["DB_HOST", "DB_PORT", "DB_USER", "DB_PASS"]) as secrets:
    host = secrets["DB_HOST"].reveal().decode()
    port = secrets["DB_PORT"].reveal().decode()
# All secrets zeroized on exit

# Store a secret (HSM-encrypted)
loader.store_secret("new_api_key", b"sk-xxxxx", source=SecretSource.HSM)

# Rotate a secret
loader.rotate_secret("api_key", b"sk-new-key-value")
```python

### 3. PKCS#11 HSM Integration

#### SoftHSM2 (Development/Testing)

Software-based PKCS#11 HSM. Free, open-source. Zero-cost.

**Setup:**
```bash
# Install SoftHSM2
apt install softhsm2

# Initialize a token
softhsm2-util --init-token --slot 0 --label "tranc3" \
    --pin 123456 --so-pin 12345678

# Install Python bindings
pip install python-pkcs11
```text

**Usage:**
```python
from Dimensional.architecture.vault_security import SoftHSM2Provider, HSMKeyType

hsm = SoftHSM2Provider(token="tranc3", pin="123456")
hsm.initialize()

# Generate an AES-256 key inside the HSM
key_handle = hsm.generate_key(HSMKeyType.AES, 256, label="master-key")

# Encrypt/decrypt — keys never leave the HSM
ciphertext = hsm.encrypt(key_handle, b"secret data")
plaintext = hsm.decrypt(key_handle, ciphertext)

# Sign/verify
sig_key = hsm.generate_key(HSMKeyType.EC, 256, label="signing-key")
signature = hsm.sign(sig_key, b"message to sign")
is_valid = hsm.verify(sig_key, b"message to sign", signature)

# Cleanup
hsm.close()  # Zeroizes PIN from memory
```python

#### YubiHSM 2 (Production)

Hardware Security Module with FIPS 140-2 Level 3 tamper resistance. One-time cost (~$650 USD), no recurring fees.

**Setup:**
```bash
# Install YubiHSM SDK
apt install yubihsm-shell

# Start the connector daemon
yubihsm-connector --daemon

# Initialize the HSM (first time only)
yubihsm-setup
```text

**Usage:**
```python
from Dimensional.architecture.vault_security import YubiHSM2Provider, HSMKeyType

hsm = YubiHSM2Provider(
    connector_url="http://localhost:12345",
    auth_key_id=1,
    auth_key_password=b"password",
)
hsm.initialize()
# Same API as SoftHSM2 — transparent provider switching
key_handle = hsm.generate_key(HSMKeyType.AES, 256, label="master-key")
ciphertext = hsm.encrypt(key_handle, b"secret data")
hsm.close()
```python

### 4. VaultAuditLogger — Append-Only Audit Trail

Records all vault access events in a chain-linked, append-only log.

**Features:**
- Append-only: Records cannot be modified or deleted
- Chain-linked: Each record contains SHA-256 hash of previous record
- Tamper-evident: Chain integrity can be verified at any time
- Daily rotation: Separate log file per day
- Compatible with the existing AuditLedger architecture

**Audit Event Types:**
| Event Type | Description |
|---|---|
| `secret_read` | Secret was accessed |
| `secret_write` | Secret was stored |
| `secret_delete` | Secret was deleted |
| `hsm_key_generate` | HSM key was generated |
| `hsm_key_use` | HSM key was used for operation |
| `hsm_key_delete` | HSM key was deleted |
| `hsm_sign` | Data was signed with HSM key |
| `hsm_verify` | Signature was verified with HSM key |
| `hsm_encrypt` | Data was encrypted with HSM key |
| `hsm_decrypt` | Data was decrypted with HSM key |
| `vault_unlock` | Vault/HSM session was opened |
| `vault_lock` | Vault/HSM session was closed |
| `vault_rotate` | Secret was rotated |
| `access_denied` | Access attempt was denied |
| `integrity_check` | Chain integrity was verified |

**Usage:**
```python
from Dimensional.architecture.vault_security import VaultAuditLogger

audit = VaultAuditLogger(log_dir="logs/vault-audit")

# Verify chain integrity
is_valid = audit.verify_chain()
print(f"Chain integrity: {is_valid}")

# Verify specific date
is_valid = audit.verify_chain(date="2024-01-15")
```python

## Security Properties

### Memory Zeroization

All sensitive data is stored in `SecureBytes` objects that:
1. Use `explicit_bzero()` (Linux) or `memset_s` (C11) for secure memory wiping
2. Fall back to volatile `ctypes` memset if C functions are unavailable
3. Zeroize automatically on `__del__` and context manager exit
4. Prevent double-zeroize with internal flag tracking

### Memory Locking (mlock)

When `lock_memory=True`:
- `mlock()` system call prevents memory pages from being swapped to disk
- Requires `CAP_IPC_LOCK` capability or root privileges on Linux
- Gracefully degrades: if `mlock()` fails, a warning is logged but operations continue

### Constant-Time Comparison

All secret comparisons use `hmac.compare_digest()`:
- Prevents timing attacks that could leak secret values
- Returns as soon as length mismatch is detected (length is not secret)
- Used in `SecureBytes.__eq__()` and internal comparisons

### HSM Boundary

All cryptographic operations with HSM keys:
- Keys are generated inside the HSM and never leave in plaintext
- Encryption, decryption, signing, and verification are performed by the HSM
- Key material is protected by the HSM's tamper-resistant storage
- SoftHSM2 provides the same API boundary for development

## Zero-Cost Mandate

### Zero-Cost Baseline (All components below are free - no cost whatsoever)

| Component | Cost | Notes |
|---|---|---|
| SecureBytes | Free | Software-only memory protection |
| VaultSecretLoader | Free | Uses self-hosted sources only |
| SoftHSM2 | Free | Open-source software HSM |
| VaultAuditLogger | Free | Local file storage (JSONL) |
| Infinity Void | Free | Self-hosted encrypted vault |

No paid cloud services are used in the baseline. AWS Secrets Manager, Azure Key Vault, HashiCorp Vault Enterprise, and GCP Secret Manager are NOT used.

### Optional Hardening (One-time hardware cost - no recurring fees)

| Component | Cost | Notes |
|---|---|---|
| YubiHSM 2 | ~$650 one-time | FIPS 140-2 Level 3 HSM, no recurring fees |

YubiHSM 2 is an optional production hardening upgrade. The full vault security stack operates at zero cost using SoftHSM2 for development and testing. YubiHSM 2 is only recommended for deployments requiring FIPS 140-2 Level 3 compliance or hardware-bound key storage.

## File Structure

```text
Dimensional/architecture/
├── vault_security.py        # Main vault security module
├── audit_ledger.py          # Existing audit ledger (complementary)
├── sentinel.py              # Security sentinel daemon
├── smart_storage.py         # Smart storage orchestrator
├── storage_factory.py       # Original storage factory
└── oci_storage.py           # OCI object storage provider

logs/vault-audit/
├── vault-audit-2024-01-15.jsonl
├── vault-audit-2024-01-16.jsonl
└── ...

secrets/hsm/
├── database_password.enc    # HSM-encrypted secret files
└── api_key.enc
```python

## Integration with Smart Storage

The Vault Security layer integrates with the Smart Storage architecture:

1. **Storage credentials** are loaded via VaultSecretLoader
2. **MinIO access keys** are stored as HSM-encrypted secrets
3. **Ceph credentials** are loaded from the Infinity Void vault
4. **Cloud free-tier tokens** (R2, OCI) are rotated automatically
5. **All storage access** is recorded in the vault audit log

## Future Enhancements

### Zero-Cost (Self-hosted / Open-source)
- [ ] Shamir's Secret Sharing for multi-party key recovery
- [ ] TPM 2.0 integration for platform-bound keys (available on most modern hardware)

### Optional / Paid
- [ ] Secret scanning integration with GitHub Advanced Security (requires GitHub Enterprise)
- [ ] Automated compliance reporting (SOC 2, ISO 27001) (requires commercial tooling)
