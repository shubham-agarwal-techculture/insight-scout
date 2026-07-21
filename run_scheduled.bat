@echo off
setlocal enabledelayedexpansion

REM Start Insight Scout and run scouts on startup, then every hour.
REM Usage: run_scheduled.bat [--host HOST] [--port PORT] [--interval SECONDS] [--once]

set "SCRIPT_DIR=%~dp0"
REM Remove trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%\run_scheduled.py" %*
) else (
  python "%SCRIPT_DIR%\run_scheduled.py" %*
)

endlocal

