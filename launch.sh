#!/usr/bin/env bash
# ==============================================================================
# X-Plane Cabin Announcer - Unix Launcher (macOS & Linux)
# ==============================================================================

# Move to the script's directory
cd "$(dirname "$0")" || exit 1

echo "======================================================"
echo "          X-Plane Cabin Announcer (macOS/Linux)       "
echo "======================================================"
echo ""

# Find available Python command (python3 or python)
if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo "ERROR: Python 3 was not found on your system."
    echo "Please install Python 3.9+ from your package manager or https://www.python.org"
    exit 1
fi

echo "Using Python: $($PY_CMD --version)"

# Check and install requirements if needed
if ! $PY_CMD -c "import customtkinter, sounddevice, soundfile, scipy, numpy, pygame, yaml, PIL" >/dev/null 2>&1; then
    echo "Dependencies missing. Installing from requirements.txt..."
    $PY_CMD -m pip install -r requirements.txt --prefer-binary
fi

echo "Launching X-Plane Cabin Announcer..."
$PY_CMD main.py "$@"
