# Orphaned Branch Recovery — why 59 branches cannot be merged, and what is actually in them

**Status:** analysis complete, 2026-08-18. Recovery decision outstanding (§5).

## 1. The finding

`main` was re-rooted on **2026-07-18**. It now holds **92 commits**, every one dated
2026-07-18 or later, under root commit `902a5a91`. The 59 non-bot branches carry
**763+ commits** back to 2026-04-21 under a *different* root, `5addbf11`.

The two graphs share no commit at all:

```
$ git merge-base origin/main origin/claude/core-api-100
$ echo $?
1
```

Every ancestry-based operation fails with that. You cannot merge, rebase,
cherry-pick or three-way diff a branch against a trunk it has no basis in.
**All 59 of 59** non-bot branches are in this state.

This is the whole explanation for "why is every branch unmergeable?". It was never
59 independent judgement calls about 59 branches — it is one structural event.

## 2. Why the usual tests all gave the wrong answer

This bit matters, because three plausible methods each produce a confident, wrong
number here:

| Test | What it reports | Why it misleads |
|---|---|---|
| `git branch --merged main` | nothing merged | `main` squash-merges, so a merged branch's tip is never an ancestor |
| `git diff main...branch` (three-dot) | full original diff | diffs from the **fork point**; squash-merged work still shows entirely |
| `git diff main..branch` (two-dot) | ~750–1000 "live" files per branch | mixes *branch has what main lacks* with *main gained this later*; a stale branch reads as proposing to revert `main` |

The two-dot figure is the dangerous one: it looked like a rich salvage backlog
spread evenly across unrelated branches. That evenness was the tell — it was
measuring `main`'s own three months of evolution, not branch value.

With no merge-base available, ancestry cannot arbitrate. **Only content can.**

## 3. What the branches actually contain

Comparing trees directly — every path present in a branch and absent from `main`:

- `main` holds **2,906** files.
- Across all 59 branches, **150** paths exist that `main` does not have.

By subsystem:

| Subsystem | Paths | In ≥50% of branches | Verdict |
|---|---:|---:|---|
| docs | 103 | 22 | `PHASE25_*`/`PHASE26_*` status snapshots. Superseded — `main`'s `docs/` tree carries architecture, cab, compliance, governance, policies, runbooks, services and templates, plus 62 `wiki-content/` files |
| root-config | 24 | 21 | `todo.md`, `PROJECT_PULSE.md`, `REVERT_LOG.md`, `VERIFICATION.md` — process ephemera. `RESEARCH_FINDINGS.md` and `SECURITY-ASSESSMENT.md` already exist under `docs/` |
| worker:the-void | 5 | 4 | **Only genuine candidate** — see §4 |
| worker:monitoring-go | 3 | 3 | Deliberately removed. `workers/monitoring/` (Python) is live |
| worker:queue-service-go | 2 | 2 | Deliberately removed. `workers/queue-service/` is live |
| worker:rate-limit-service-go | 2 | 2 | Deliberately removed. `workers/rate-limit-service/` is live |
| src:core, src:routers, monitoring | 3 | 3 | **Moved, not lost** — see below |

Three apparent losses dissolve on inspection, all of them relocations:

| Branch path | Where it actually lives on `main` |
|---|---|
| `monitoring/prometheus/alerts/tranc3-core.yml` | `monitoring/alerts/tranc3-core.yml` |
| `src/core/consciousness_integration.py` | `src/bio_neural/consciousness_integration.py` |
| `src/routers/admin_os.py` | `src/admin_os/` package + `workers/infinity-admin-service/` |

The Go workers are the same story in reverse: they were removed on purpose as
duplicates of the Python implementations, which are all present.

**The headline features of the 27 closed-unmerged PRs are already on `main`** —
`aeonmind/`, `Dimensional/`, `src/observability/`, `src/nanoservices/`,
AlertManager, the OTel collector and SLO rules all exist, and `cache-service`
already declares `/cache/status` before the `/cache/{key}` catch-all, which was
PR #209's route-shadowing fix. The work was re-done on the new trunk rather than
merged from these branches.

## 4. The one real candidate

`workers/the-void/rust_crypto/` — a 142-line PyO3 extension (`tranc3-vault-crypto`)
implementing AES-256-GCM with PBKDF2-HMAC-SHA256 key derivation.

It is **not missing functionality**. `workers/infinity-void/worker.py` implements
the same algorithms — AES-256-GCM, PBKDF2 at 100k iterations — in Python. The Rust
module is a **native-speed alternative**, and adopting it means adding a Rust
toolchain and a PyO3 build to the vault's image.

That is a cost/benefit call, not an automatic win, and it should be decided on
whether vault crypto is actually hot enough to justify the build complexity.

`src/cloud/cost_optimizer.py` (112 lines, `MultiCloudCostOptimizer`) estimates
**EKS/AKS/GKE** costs. The platform is zero-cost, self-hosted, Cloudflare + Fly.
Recommend discard as architecturally irrelevant.

## 5. Recommendation

1. **Do not attempt to merge any of the 59 branches.** There is no basis to merge
   against, and the content yield does not justify reconstructing one.
2. **Decide on `rust_crypto`** — the single component worth a conscious choice.
   If wanted, it is lifted as files into `workers/infinity-void/`, not merged.
3. **Treat the rest as archived.** The branches remain readable for
   forensics; nothing is deleted by this document.
4. **`scripts/check_history_integrity.py` now guards the root cause.** It fails CI
   if `main`'s root commit changes again, and reports orphan counts. Wired into
   `ci.yml`'s `topology` job.

## 6. Scope note

Only Tranc3 is affected. CranBania (10 branches), Magna-Carta (7) and
InfinityStyles (1) all share history with their `main` normally — verified by
`git merge-base` succeeding for every branch in each.
