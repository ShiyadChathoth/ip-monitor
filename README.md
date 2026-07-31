# Advanced SSH & PC Live Manager

A lightweight, Python-based GUI application designed for Linux users to seamlessly monitor, manage, and interact with remote servers and local network PCs via SSH and SFTP.

## Features

* **Live Status Monitoring:** Continuously pings saved IP addresses to track whether nodes are ONLINE or OFFLINE.
* **Built-in Network Scanner:** Scans your `192.168.0.X` local subnet to automatically discover active SSH hosts.
* **Graphical SFTP Explorer:** Browse remote directories, create new files, and download files/folders via a graphical interface.
* **Remote Code Execution:** Open remote scripts and HTML files directly on the target machine's physical monitor/display (using X11/Wayland environment detection).
* **Local Gedit Sync:** Instantly download a remote file, edit it locally in Gedit, and auto-sync changes back to the server upon closing.
* **Terminal Launcher:** Quickly spawn a new local `gnome-terminal` connected to the target node via SSH.

## Prerequisites

This application is built for Debian/Ubuntu-based Linux environments. It requires:
* Python 3.x
* `python3-tk` (Tkinter for the GUI)
* `sshpass` (For automated remote executions)
* SSH Service (`sshd`) enabled on local and target machines.

## Installation

Clone this repository and run the provided installation script to configure all system and Python dependencies:

```bash
git clone [https://github.com/yourusername/ip_monitor.git](https://github.com/yourusername/ip_monitor.git)
cd ip_monitor
chmod +x install.sh
./install.sh
