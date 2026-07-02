# Infinity Admin OS

Desktop-style administrative shell served at `/dashboard/infinity-admin-os.html` on **tranc3-backend** (port 8000 on Fly).

## Features

| App | API prefix | Description |
|-----|------------|-------------|
| **Domain Model** | `/admin-os/domain-model` | View/edit 43 platform entities; changes persist to `data/infinity_admin.db` |
| **Files** | `/admin-os/files` | Sandboxed workspace (`data/admin_os_workspace`) — list, read, write, mkdir, delete |
| **Backups** | `/admin-os/backups` | Manual + auto backup (workspace + entity DB) to `data/admin_os_backups` |
| **System Viewer** | `/admin-os/system` | Host info, `PLATFORM_INFRA_MODE`, worker port catalog |
| **Event Viewer** | `/admin-os/events` | Audit feed from **The Observatory**; live via `/observatory/sse` |

## Environment

| Variable | Default |
|----------|---------|
| `ADMIN_OS_WORKSPACE_ROOT` | `data/admin_os_workspace` |
| `ADMIN_OS_BACKUP_DIR` | `data/admin_os_backups` |
| `ADMIN_OS_AUTO_BACKUP_HOURS` | `24` |
| `ENTITY_OVERRIDES_DB` | `data/infinity_admin.db` |

## Open locally

```text
http://localhost:8000/dashboard/infinity-admin-os.html
```

After Fly deploy:

```text
https://tranc3-backend.fly.dev/dashboard/infinity-admin-os.html
```

## Related

- `workers/infinity-admin-service/` (port 8044) — extended admin API when Citadel stack runs
- `src/entities/effective.py` — merged display names
- `src/observability/` — The Observatory event source
