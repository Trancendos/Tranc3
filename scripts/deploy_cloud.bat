@echo off
REM CLOUD_ONLY deploy to Fly.io (backend + bots)
cd /d "%~dp0.."
where py >nul 2>&1 && py -3.11 scripts\deploy_cloud.py %* && exit /b %ERRORLEVEL%
where python >nul 2>&1 && python scripts\deploy_cloud.py %* && exit /b %ERRORLEVEL%
echo ERROR: Python 3.11+ required
exit /b 1
