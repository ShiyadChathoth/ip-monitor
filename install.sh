#!/bin/bash

echo ">>> Updating package lists..."
sudo apt-get update

echo ">>> Installing required system dependencies (Tkinter, pip, sshpass)..."
sudo apt-get install -y python3-tk python3-pip sshpass

echo ">>> Installing Python dependencies..."
pip3 install -r requirements.txt

echo ">>> Setup Complete! Run the app using: python3 ssh_gui_monitor.py"
