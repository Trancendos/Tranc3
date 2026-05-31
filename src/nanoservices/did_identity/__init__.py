"""DID/VC Identity Service — Phase 9.5

Decentralized identity and verifiable credentials (W3C DID Core).
"""

from .did_identity import (
    CredentialIssuer,
    CredentialStatus,
    DIDDocument,
    DIDIdentityService,
    DIDKeyMethod,
    DIDMethod,
    DIDTranc3Method,
    DIDWebMethod,
    VerifiableCredential,
    VerifiablePresentation,
)

__all__ = [
    "DIDMethod",
    "CredentialStatus",
    "DIDDocument",
    "VerifiableCredential",
    "VerifiablePresentation",
    "DIDKeyMethod",
    "DIDWebMethod",
    "DIDTranc3Method",
    "CredentialIssuer",
    "DIDIdentityService",
]
