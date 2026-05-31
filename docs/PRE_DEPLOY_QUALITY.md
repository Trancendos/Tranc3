# Pre-deploy quality (846 IDE issues explained)

The IDE problem panel often shows **~800+ issues**. That number is **not** a deploy blocker by itself.

## What the ~846 usually is

| Source | Typical count | Deploy blocker? |
|--------|---------------|-----------------|
| **mypy** (stub routes, nanoservices, planned modules) | ~200–470 | No — scoped/overridden in `pyproject.toml` |
| **bandit** (B110 try/except, B311 random for ML) | ~250–600 | Only **HIGH** confidence |
| **ruff** (style, imports) | ~5–75 on P0 paths | Yes on **P0 paths** — must be clean |

## What blocks deploy

Run the **single gate** used before Citadel:

```bash
make pre-deploy-gate
```

This fails only on:

1. Production gate pytest subset
2. Ruff clean on P0 paths (`src/`, `api.py`, core workers)
3. Bandit **HIGH** on P0 paths
4. `pip-audit` CVEs (when installed)
5. `citadel_compose_validate.py`

Auto-fix style on P0 paths:

```bash
make pre-deploy-fix
```

## Critical fixes applied (2026-05-31)

- Bandit **B324**: `usedforsecurity=False` on MD5/SHA1 used for etags/hashing (not passwords)
- **api.py**: `EnhancedPersonalityMatrix` + `get_brain()` / dream-cycle hook
- **mypy**: exclude `Dimensional/`, ignore stub `src.*.routes` modules
- **bandit**: skip B311/B324 where documented; exclude non-production trees

## Full repo scans (informational)

```bash
ruff check .          # may show 70+ — many outside deploy scope
bandit -r .           # 600+ — mostly LOW/MEDIUM
mypy src/ api.py      # 200+ after overrides — stub modules
```

Use **`make pre-deploy-gate`** for go/no-go, not the raw IDE total.
