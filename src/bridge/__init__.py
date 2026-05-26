"""
Python-TypeScript Bridge — Tranc3 Ecosystem
=============================================

Provides seamless communication between the Python and TypeScript
codebases using JSON-RPC 2.0 over HTTP or stdio.

Architecture:
  Python ←→ JSON-RPC ←→ HTTP/stdio ←→ TypeScript

The bridge uses a shared message format so that both sides can
understand each other without translation layers.
"""

from .ecosystem_bridge import (
    BridgeConfig,
    BridgeEndpoint,
    BridgeTransport,
    JsonRpcRequest,
    JsonRpcResponse,
    EcosystemBridge,
    EcosystemRegistry,
    EcosystemEntity,
)

__all__ = [
    "BridgeConfig",
    "BridgeEndpoint",
    "BridgeTransport",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "EcosystemBridge",
    "EcosystemRegistry",
    "EcosystemEntity",
]
