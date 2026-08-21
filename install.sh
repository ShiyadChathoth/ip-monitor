#!/bin/bash
set -e

echo ">>> Updating package lists..."
sudo apt-get update

echo ">>> Installing required system and Python dependencies..."
sudo apt-get install -y python3-tk sshpass python3-paramiko

echo ">>> Creating Desktop Shortcut..."
APP_DIR=$(pwd)
DESKTOP_FILE=$HOME/.local/share/applications/ip_monitor.desktop

cat << INNEREF > "$DESKTOP_FILE"
[Desktop Entry]
Name=SSH Live Manager
Comment=Advanced SSH & PC Live Manager
Exec=/usr/bin/python3 "$APP_DIR/ssh_gui_monitor.py"
Path=$APP_DIR
Icon=$APP_DIR/logo.svg
Terminal=false
Type=Application
Categories=Utility;Network;Development;
INNEREF

chmod +x "$DESKTOP_FILE"

echo ">>> Setup Complete! You can now launch 'SSH Live Manager' from your application menu."
