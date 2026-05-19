@echo off
setlocal enabledelayedexpansion

echo Starting Stem Desk...

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Check if setup is needed
if not exist ".venv-demucs" (
    echo First-time setup detected. Running setup-demucs.bat...
    call setup-demucs.bat
)

if not exist ".venv-demucs" (
    echo Error: Setup failed or .venv-demucs directory missing.
    pause
    exit /b 1
)

:: Determine venv python
set VENV_PYTHON=.venv-demucs\Scripts\python.exe
if not exist "!VENV_PYTHON!" (
    set VENV_PYTHON=python
)

:: Open browser in a separate process after a short delay
echo Opening browser...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8765/index.html"

:: Start the server
echo Starting server...
"!VENV_PYTHON!" server.py --port 8765

if %ERRORLEVEL% neq 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%
    pause
)
