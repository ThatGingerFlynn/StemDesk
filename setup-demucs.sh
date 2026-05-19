#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname)" == "Darwin" ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required for the one-command setup on this Mac."
    echo "Install Python 3.11 yourself, then run:"
    echo "  python3.11 -m venv .venv-demucs"
    echo "  .venv-demucs/bin/python -m pip install --upgrade pip"
    echo "  .venv-demucs/bin/python -m pip install demucs"
    exit 1
  fi

  if ! command -v python3.11 >/dev/null 2>&1; then
    brew install python@3.11
  fi

  if ! command -v ffmpeg >/dev/null 2>&1; then
    brew install ffmpeg
  fi
fi

# Create or update the virtual environment
# Using 'python3' as a fallback if 'python3.11' is not explicitly available
PYTHON_EXE=$(command -v python3.11 || command -v python3 || command -v python)
$PYTHON_EXE -m venv .venv-demucs

# Detect venv python path
if [[ -f ".venv-demucs/Scripts/python" ]]; then
  VENV_PYTHON=".venv-demucs/Scripts/python"
else
  VENV_PYTHON=".venv-demucs/bin/python"
fi

$VENV_PYTHON -m pip install --upgrade pip

# We install soundfile and ensure torchcodec is gone.
# torchaudio 2.5.0+ has a bug where it tries to use torchcodec for saving even if not installed.
# We downgrade torchaudio to a version before this behavior was introduced (e.g., <2.5.0)
# or ensure soundfile is the primary backend.
$VENV_PYTHON -m pip install soundfile

# Detect hardware and install appropriate torch/audio-separator extras
if [[ "$(uname)" == "Darwin" ]]; then
  echo "macOS detected. Installing with CoreML support..."
  $VENV_PYTHON -m pip install "torchaudio<2.5.0"
  $VENV_PYTHON -m pip install demucs "audio-separator[coreml]" || $VENV_PYTHON -m pip install demucs audio-separator
elif command -v nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA GPU detected. Installing with CUDA support..."
  # For CUDA, we might want to specify the index-url for torch to ensure we get the GPU version
  $VENV_PYTHON -m pip install "torchaudio<2.5.0" --extra-index-url https://download.pytorch.org/whl/cu121
  $VENV_PYTHON -m pip install demucs "audio-separator[gpu]" || $VENV_PYTHON -m pip install demucs audio-separator
else
  echo "No NVIDIA GPU detected or not on macOS. Installing standard versions..."
  $VENV_PYTHON -m pip install "torchaudio<2.5.0"
  $VENV_PYTHON -m pip install demucs audio-separator
fi

$VENV_PYTHON -m pip uninstall -y torchcodec || true

$VENV_PYTHON -m demucs --help >/dev/null

echo "Demucs is ready for Stem Desk."
