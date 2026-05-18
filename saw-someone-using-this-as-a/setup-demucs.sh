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
python3.11 -m venv .venv-demucs
.venv-demucs/bin/python -m pip install --upgrade pip

# We remove torchcodec because it often has strict FFmpeg version requirements (like FFmpeg 4)
# that conflict with modern Homebrew FFmpeg (often FFmpeg 7+). Demucs does not need it.
.venv-demucs/bin/python -m pip uninstall -y torchcodec || true
.venv-demucs/bin/python -m pip install demucs

.venv-demucs/bin/python -m demucs --help >/dev/null

echo "Demucs is ready for Stem Desk."
