@echo off
REM Run a Python script with the best available interpreter (3.9+).
REM Usage: scripts\run_python.bat path\to\script.py [args...]
setlocal
set "PYSCRIPT=%~1"
if "%PYSCRIPT%"=="" (
  echo ERROR: run_python.bat requires a script path
  exit /b 1
)
shift
set "PYARGS="
:collect
if "%~1"=="" goto run
set "PYARGS=%PYARGS% %1"
shift
goto collect

:run
cd /d "%~dp0.."
if not exist "%PYSCRIPT%" (
  echo ERROR: Script not found: %PYSCRIPT%
  exit /b 1
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  for %%V in (3.13 3.12 3.11 3.10 3.9 3) do (
    py -%%V "%PYSCRIPT%" %PYARGS%
    if not errorlevel 103 exit /b %ERRORLEVEL%
  )
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%PYSCRIPT%" %PYARGS%
  exit /b %ERRORLEVEL%
)

echo ERROR: Python 3.9+ not found. Install from https://www.python.org/downloads/
exit /b 1
