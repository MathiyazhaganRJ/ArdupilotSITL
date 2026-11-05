#!/usr/bin/env bash
# Setup script for ArduPilot SITL Visualizer & Desktop App on Ubuntu / Debian / WSL
set -e

echo "=== Setting up ArduPilot SITL Visualizer on Ubuntu / Linux ==="

echo "1. Updating package lists..."
sudo apt update

echo "2. Installing GTK3, WebKit2, and Python build tools for native desktop window (pywebview)..."
# Detect Ubuntu 20.04 vs 22.04+ for WebKit2 package version
if grep -q "20.04" /etc/os-release 2>/dev/null; then
    WEBKIT_PKG="gir1.2-webkit2-4.0"
else
    WEBKIT_PKG="gir1.2-webkit2-4.1"
fi

sudo apt install -y python3-pip python3-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0 "$WEBKIT_PKG"

echo "3. Installing Python dependencies..."
PIP_CMD="pip3"
if ! command -v pip3 &>/dev/null; then
    PIP_CMD="pip"
fi

# Modern Ubuntu 23.04+ and 24.04 LTS (PEP 668) require --break-system-packages for non-venv installs
if $PIP_CMD install --help 2>&1 | grep -q -- '--break-system-packages'; then
    $PIP_CMD install -r requirements.txt --break-system-packages
else
    $PIP_CMD install -r requirements.txt
fi

echo "=== Setup complete! ==="
echo ""
echo "To run the standalone native desktop app:"
echo "    python3 server/server.py"
echo ""
echo "To run in headless server mode (for browser tab):"
echo "    python3 server/server.py --headless"
echo ""
echo "To run the log viewer:"
echo "    python3 log_viewer.py"
