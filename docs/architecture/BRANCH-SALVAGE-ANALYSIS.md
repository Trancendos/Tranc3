# Branch salvage analysis — what is actually left in 78 stale branches

**Date:** 2026-08-18. **Verdict:** two files of unique content across all of them.

## 1. Result

Across all 78 non-bot branches in Tranc3, CranBania, Magna-Carta and InfinityStyles,
compared three-way (merge-base / branch / `main`):

| Classification | Files | Meaning |
|---|---:|---|
| **BRANCH-ONLY** | **5** | branch changed it, `main` did not — genuinely unique content |
| SUPERSEDED | 49 | branch changed it, `main` now has the identical content — landed by another route |
| DIVERGED | 148 | both sides changed it — staleness, not value |

**63 of 78 branches have zero unique and zero diverged files.** Their work is
entirely in `main` already; they can be deleted with no loss.

Of the 5 BRANCH-ONLY files, 3 are this analysis's own commit. The complete
historical remainder is **two files**:

| Branch | File | Assessment |
|---|---|---|
| `circleci-project-setup` | `.circleci/config.yml` | Genuinely absent from `main`. The estate runs Forgejo (primary) + GitHub Actions; CircleCI is not in the toolchain. Keep only if CircleCI is wanted. |
| `claude/inspiring-cannon-riqbtu` | `CF_WORKER_MIGRATION_ROADMAP.md` | Deliberately relocated — `CLAUDE.md` records it as `wiki-content/Architecture-CF_WORKER_MIGRATION_ROADMAP.md`. Not a loss. |

**Nothing of value is trapped in the branches.**

## 2. Why the obvious tests mislead here

`main` squash-merges, and the branches are 2–3 months stale against a fast-moving
trunk. That breaks every two-ref test:

| Test | Reports | Why it is wrong |
|---|---|---|
| `git branch --merged main` | nothing merged | squash-merge means a merged branch's tip is never an ancestor |
| `git diff main...branch` (three-dot) | full original diff | diffs from the **fork point**; squash-merged work still shows in full |
| `git diff main..branch` (two-dot) | ~750–1000 "live" files *per branch* | mixes *branch has what main lacks* with *main gained this later* |

The two-dot number is the trap. It suggested a large salvage backlog spread
**evenly across unrelated branches** — and that evenness was the tell: it was
measuring `main`'s own three months of progress, not branch content.

Only a three-way comparison against the merge-base separates the four cases:

```
branch == base                    -> branch never changed it
branch != base and main == base   -> BRANCH-ONLY   (real, salvageable)
branch != base and main == branch -> SUPERSEDED    (landed elsewhere)
branch != base and main != base   -> DIVERGED      (both moved; a merge decision)
```

## 3. The shallow-clone trap — read this before repeating the analysis

An earlier pass of this investigation concluded that `main` had been **re-rooted
on 2026-07-18**, orphaning all 59 Tranc3 branches. The evidence looked
overwhelming: `merge-base` failed for every branch, `main` appeared to hold 92
commits, and `rev-list --max-parents=0 origin/main` returned `902a5a91` while the
branches returned `5addbf11`.

**All of it was an artefact of a shallow clone.** `902a5a91` was the shallow graft
boundary, not a root commit. `merge-base` failed because the shared history had
never been fetched, not because it did not exist.

After `git fetch --unshallow`:

- `main` has **1,392 commits**, back to the same `5addbf11` (2026-04-21) the
  branches descend from.
- **All 60 branches share a merge-base.** Zero orphans.
- No rewrite ever happened.

The general lesson: on a shallow clone, git's history commands answer
*confidently and wrongly*. `rev-list --max-parents=0` returns a graft boundary
indistinguishable from a root; `merge-base` reports "unrelated" for related
branches. Nothing errors. Always check:

```
git rev-parse --is-shallow-repository
```

before drawing any conclusion from ancestry. `scripts/check_history_integrity.py`
now encodes this: it deepens `main` itself and refuses to report success on
history it could not read.

## 4. Recommendation

1. **Delete the 63 fully-absorbed branches** — zero unique and zero diverged
   content; nothing is lost.
2. **Decide on `.circleci/config.yml`** — the only genuinely absent file, and only
   relevant if CircleCI is wanted alongside Forgejo and GitHub Actions.
3. **Ignore `CF_WORKER_MIGRATION_ROADMAP.md`** — already relocated to
   `wiki-content/`.
4. **The 13 diverged branches** carry no unique files, only files `main` has since
   changed. `claude/security-fixes-code-scanning` has the most (101), all staleness.
   No merge is warranted.

## 5. Method

`git ls-tree -r` blob-hash comparison across three revisions per branch
(merge-base, branch tip, `main` tip), classified per file, grouped by owning
worker/module so salvage could have been done per deployable unit had the yield
justified it. Cost is O(branches), not O(files).
