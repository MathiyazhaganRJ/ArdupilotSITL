#!/usr/bin/env bash
# Setup script for ArduPilot SITL Visualizer & Desktop App on Ubuntu / Debian / WSL
set -e

echo "=== Setting up ArduPilot SITL Visualizer on Ubuntu / Linux ==="

echo "1. Updating package lists..."
sudo apt update

echo "2. Installing GTK3 and WebKit2 system libraries for native desktop window (pywebview)..."
# Detect Ubuntu 20.04 vs 22.04+ for WebKit2 package version
if grep -q "20.04" /etc/os-release 2>/dev/null; then
    WEBKIT_PKG="gir1.2-webkit2-4.0"
else
    WEBKIT_PKG="gir1.2-webkit2-4.1"
fi

sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 "$WEBKIT_PKG"

echo "3. Installing Python dependencies..."
pip install -r requirements.txt

echo "=== Setup complete! ==="
echo ""
echo "To run the standalone native desktop app:"
echo "    python server/server.py"
echo ""
echo "To run in headless server mode (for browser tab):"
echo "    python server/server.py --headless"
echo ""
echo "To run the log viewer:"
echo "    python log_viewer.py"
