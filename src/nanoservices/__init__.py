"""
Tranc3 Nanoservices — Phase 7 Advanced Architecture
====================================================

Modules:
  - nsa_broker: Rust-based shared-memory IPC broker (port 7780)
  - nsa_client: Python nanoservice client library
  - nsa_registry: Capability-based service discovery & health monitoring
  - shi_gateway: Self-Hosted Inference gateway (Ollama/vLLM, port 7781)
  - dnf_orchestrator: Distributed Nano-Flows (replaces cloud FaaS, port 7782)
  - fmd_distiller: Federated Model Distillation pipeline
  - daas_stream: Data as a Service with sovereignty (OPA + Redpanda)
  - igi_gitops: Immutable GitOps Infrastructure (Forgejo + FluxCD)
  - genetic_optimizer: DEAP-based adaptive optimization
  - quantum_solver: Qiskit-based hybrid quantum computing
"""

__all__ = [
    "nsa_client",
    "nsa_registry",
    "shi_gateway",
    "dnf_orchestrator",
    "fmd_distiller",
    "daas_stream",
    "igi_gitops",
    "genetic_optimizer",
    "quantum_solver",
]
