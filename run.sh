#!/usr/bin/env bash
set -e

# Stem Desk Launcher
# This script ensures dependencies are installed and starts the server.

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check for Python
if command -v python3 &> /dev/null; then
    PYTHON_EXE="python3"
elif command -v python &> /dev/null; then
    PYTHON_EXE="python"
else
    echo "Error: python is not installed."
    exit 1
fi

# Check if setup is needed
if [ ! -d ".venv-demucs" ]; then
    echo "First-time setup detected. Running setup-demucs.sh..."
    bash setup-demucs.sh
fi

# Determine the venv python path
if [[ -f ".venv-demucs/Scripts/python" ]]; then
  VENV_PYTHON=".venv-demucs/Scripts/python"
elif [[ -f ".venv-demucs/bin/python" ]]; then
  VENV_PYTHON=".venv-demucs/bin/python"
else
  VENV_PYTHON="$PYTHON_EXE"
fi

# Start the server and open the browser
echo "Starting Stem Desk..."
# We run the server in the background so we can open the browser
"$VENV_PYTHON" server.py --port 8765 &
SERVER_PID=$!

# Function to kill the server on exit
cleanup() {
    echo "Shutting down..."
    kill $SERVER_PID
}
trap cleanup EXIT

# Wait a moment for the server to initialize
sleep 2

# Open browser based on OS
URL="http://127.0.0.1:8765/index.html"
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$URL"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v xdg-open &> /dev/null; then
        xdg-open "$URL"
    else
        echo "Please open $URL in your browser."
    fi
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    start "$URL"
else
    echo "Please open $URL in your browser."
fi

# Keep the script running to maintain the server process
wait $SERVER_PID
