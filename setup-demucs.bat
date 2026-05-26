@echo off
setlocal enabledelayedexpansion

echo Stem Desk Setup for Windows

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating virtual environment...
python -m venv .venv-demucs
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to create virtual environment.
    pause
    exit /b 1
)

:: Upgrade pip
echo Upgrading pip...
.venv-demucs\Scripts\python -m pip install --upgrade pip

:: Install soundfile
echo Installing soundfile...
.venv-demucs\Scripts\python -m pip install soundfile

:: Detect NVIDIA GPU
where nvidia-smi >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo NVIDIA GPU detected. Installing with CUDA support...
    .venv-demucs\Scripts\python -m pip install "torchaudio<2.5.0" --extra-index-url https://download.pytorch.org/whl/cu121
    .venv-demucs\Scripts\python -m pip install demucs "audio-separator[gpu]"
) else (
    echo No NVIDIA GPU detected. Installing standard versions...
    .venv-demucs\Scripts\python -m pip install "torchaudio<2.5.0"
    .venv-demucs\Scripts\python -m pip install demucs "audio-separator[cpu]" onnxruntime
)

:: Uninstall torchcodec if present
.venv-demucs\Scripts\python -m pip uninstall -y torchcodec

echo.
echo Demucs is ready for Stem Desk.
echo.
pause
