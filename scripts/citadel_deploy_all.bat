@echo off
REM Tranc3 Citadel — one-click gate + deploy (Windows CMD)
REM Usage: scripts\citadel_deploy_all.bat [--gate-only] [--local] ...

setlocal
call "%~dp0run_python.bat" "%~dp0citadel_deploy_all.py" %*
exit /b %ERRORLEVEL%
