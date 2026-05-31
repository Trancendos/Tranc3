@echo off
REM CLOUD_ONLY deploy to Fly.io (backend + bots)
setlocal
call "%~dp0run_python.bat" "%~dp0deploy_cloud.py" %*
exit /b %ERRORLEVEL%
