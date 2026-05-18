#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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

# Create or update the virtual environment
# Using 'python3' as a fallback if 'python3.11' is not explicitly available
PYTHON_EXE=$(command -v python3.11 || command -v python3)
$PYTHON_EXE -m venv .venv-demucs
.venv-demucs/bin/python -m pip install --upgrade pip

# We install soundfile and ensure torchcodec is gone.
# torchaudio 2.5.0+ sometimes tries to use torchcodec by default.
.venv-demucs/bin/python -m pip install soundfile
.venv-demucs/bin/python -m pip install demucs
.venv-demucs/bin/python -m pip uninstall -y torchcodec || true

.venv-demucs/bin/python -m demucs --help >/dev/null

echo "Demucs is ready for Stem Desk."
