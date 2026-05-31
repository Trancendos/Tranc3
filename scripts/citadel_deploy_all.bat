@echo off
REM Tranc3 Citadel — one-click gate + deploy (Windows CMD)
REM Usage: scripts\citadel_deploy_all.bat
REM        scripts\citadel_deploy_all.bat --gate-only

setlocal
cd /d "%~dp0.."

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3.11 scripts\citadel_deploy_all.py %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python scripts\citadel_deploy_all.py %*
  exit /b %ERRORLEVEL%
)

echo ERROR: Python 3.11+ not found. Install from https://www.python.org/downloads/
echo Then run: py -3.11 scripts\citadel_deploy_all.py
exit /b 1
