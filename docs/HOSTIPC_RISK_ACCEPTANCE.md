# hostIPC Risk Acceptance — Nanoservice Shared Memory

**Status:** ACCEPTED (with controls)  
**Review date:** 2026-06-14  
**Owner:** Platform / The Citadel  
**Next review:** 2026-09-14

## Context

Three nanoservice deployments use `hostIPC: true` and a `hostPath` volume for `/dev/shm`:

- `nsa-broker` (NSA Broker)
- `shi-gateway` (SHI Gateway)
- `dnf-orchestrator` (DNF Orchestrator)

Locations:

- `flux/base/deployments.yaml`
- `src/nanoservices/igi_gitops/flux/base/deployments.yaml`

## Why hostIPC is required

Nanoservices coordinate via POSIX shared memory segments (`/dev/shm`). Without `hostIPC`, pods cannot attach to the same IPC namespace and the broker/gateway/orchestrator pipeline fails.

## Threat model

| Risk | Mitigation |
|------|------------|
| Cross-pod IPC snooping on same node | NetworkPolicy restricts ingress; only required ports between nanoservice pods |
| Container escape via IPC | Non-root UIDs, dropped capabilities, `allowPrivilegeEscalation: false` |
| Host namespace abuse | `seccompProfile: RuntimeDefault`, no `privileged`, no `hostPID` |
| Lateral movement | Citadel Traefik + internal-only routes; no public exposure of nanoservice ports |

## Compensating controls (implemented)

1. Pod `securityContext`: `runAsNonRoot`, `seccompProfile: RuntimeDefault`
2. Container `securityContext`: `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, capability drops
3. Resource limits on all nanoservice workloads
4. Documented in `ARCHITECTURE_THREAT_MODEL.md` cross-reference

## Alternatives considered

| Alternative | Verdict |
|-------------|---------|
| Unix domain sockets only | Rejected — requires full nanoservice protocol rewrite |
| Kubernetes emptyDir for shm | Insufficient for cross-pod POSIX shm without hostIPC |
| Single pod (all-in-one) | Rejected — breaks independent scaling of broker/gateway/orchestrator |

## Decision

**Accept hostIPC** for the three nanoservice deployments until a socket-based IPC redesign is scheduled. Security score treats this as documented acceptance, not an open Critical finding.
