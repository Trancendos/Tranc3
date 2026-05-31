# Windows deploy (CLOUD_ONLY / Fly.io)

Use this guide from **Command Prompt** on Windows. You do not need `make` or Docker for cloud deploy.

## One-time setup

1. **Clone** (if you have not already):

```cmd
cd %USERPROFILE%\Documents
git clone https://github.com/Trancendos/Tranc3.git
cd Tranc3
```

2. **Python 3.12 or 3.13** (3.11 is not required). Install from [python.org](https://www.python.org/downloads/) or use the Microsoft Store build.

3. **Install dependencies and gate tools** (first time only; large download because of PyTorch):

```cmd
cd %USERPROFILE%\Documents\Tranc3
py -3.12 -m pip install -r requirements.txt ruff bandit pytest pytest-asyncio pip-audit
```

4. **Fly.io CLI** (for deploy):

```cmd
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
fly auth login
```

Set a real API token (not a placeholder):

```cmd
set FLY_API_TOKEN=<paste_from_fly.io_dashboard>
```

## Run the quality gate (CLOUD_ONLY)

Always run from the repo root, not `C:\Windows\System32`:

```cmd
cd %USERPROFILE%\Documents\Tranc3
git pull origin main
py -3.12 scripts\pre_deploy_quality_gate.py --cloud-only
```

Expected output ends with:

```text
PASS — no critical blockers for P0 deploy (CLOUD_ONLY)
```

**Equivalent wrappers** (they pass `--cloud-only` when mode is CLOUD_ONLY):

```cmd
scripts\citadel_deploy_all.bat --gate-only
scripts\deploy_cloud.bat
```

`--cloud-only` skips Docker Compose validation (Citadel). That is intentional for Fly/cloud deploy.

If you see `Unknown pytest.mark.asyncio`, install the async plugin:

```cmd
py -3.12 -m pip install pytest-asyncio
```

If the gate fails on **pytest**, read the `--- pytest (last lines) ---` section in the output, then run:

```cmd
py -3.12 -m pytest tests/test_smoke.py tests/test_infrastructure_mode.py -v --tb=short
```

If tools are missing:

```cmd
py -3.12 scripts\citadel_deploy_all.py --gate-only --install-deps
```

## Deploy to Fly.io

After the gate passes:

```cmd
cd %USERPROFILE%\Documents\Tranc3
set FLY_API_TOKEN=<your_real_token>
py -3.12 scripts\deploy_cloud.py
```

Or:

```cmd
scripts\deploy_cloud.bat
```

First deploy may require secrets on the Fly app (replace placeholders with real Supabase/Upstash values):

```cmd
fly secrets set SECRET_KEY=... JWT_SECRET=... DATABASE_URL=... REDIS_URL=... --app tranc3-backend
```

## Common mistakes

| Problem | Fix |
|--------|-----|
| `The system cannot find the path specified` for `cd C:\path\to\Tranc3` | Use `%USERPROFILE%\Documents\Tranc3` |
| `make` is not recognized | Use `scripts\*.bat` or `py -3.12 scripts\...` |
| `Python 3.11 not found` | Use `py -3.12` or pull latest `main` and use `scripts\run_python.bat` |
| `citadel_compose_validate failed` | Run gate with `--cloud-only` or use `deploy_cloud.bat` |
| `pytest` / `ruff` not found | Run the `pip install` line in setup step 3 |
| Deploy blocked with placeholder token | `set FLY_API_TOKEN=` must be a real Fly token |

## Infrastructure modes

Default is **CLOUD_ONLY** (no local Docker stack). When you are ready for The Citadel on your own server:

```cmd
set PLATFORM_INFRA_MODE=LOCAL_ONLY
scripts\citadel_deploy_all.bat --local
```

See [PLATFORM_INFRASTRUCTURE_MODE.md](PLATFORM_INFRASTRUCTURE_MODE.md).
