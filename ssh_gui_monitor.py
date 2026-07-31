import json
import os
import platform
import socket
import stat
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

CONFIG_FILE = "ips.json"
HISTORY_FILE = "ip_history.json"

class IPMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced SSH & PC Live Manager")
        self.root.geometry("860x600")
        self.root.minsize(750, 480)

        if not self.check_local_ssh_status():
            root.destroy()
            return

        self.monitored_ips = {}
        self.past_ips = []
        self.running = True

        self.load_history()

        # --- Top Frame: Input Controls & Actions ---
        input_frame = ttk.LabelFrame(root, text=" Device Management ", padding=10)
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="Tag:").pack(side="left", padx=2)
        self.name_entry = ttk.Entry(input_frame, width=10)
        self.name_entry.pack(side="left", padx=4)

        ttk.Label(input_frame, text="IP (192.168.0.X):").pack(side="left", padx=2)
        self.ip_combobox = ttk.Combobox(input_frame, values=self.past_ips, width=12)
        self.ip_combobox.pack(side="left", padx=4)
        self.ip_combobox.bind("<Return>", lambda event: self.add_ip())

        add_btn = ttk.Button(input_frame, text="Add", command=self.add_ip)
        add_btn.pack(side="left", padx=2)

        scan_btn = ttk.Button(input_frame, text="Scan Network", command=self.open_scanner_window)
        scan_btn.pack(side="left", padx=2)

        # --- Center Frame: Status List Grid ---
        list_frame = ttk.LabelFrame(root, text=" Monitored Servers & PCs ", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(list_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # --- Bottom Status Bar ---
        self.status_bar = ttk.Label(root, text="System Status: Initializing...", relief=tk.SUNKEN, anchor="w", padding=5)
        self.status_bar.pack(side="bottom", fill="x")

        self.load_saved_ips()

        self.monitor_thread = threading.Thread(target=self.background_monitor, daemon=True)
        self.monitor_thread.start()

    def check_local_ssh_status(self):
        ssh_active = False
        try:
            res = subprocess.run(["systemctl", "is-active", "ssh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if "active" in res.stdout:
                ssh_active = True
        except Exception:
            pass

        if not ssh_active:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    if s.connect_ex(('127.0.0.1', 22)) == 0:
                        ssh_active = True
            except Exception:
                pass

        if not ssh_active:
            answer = messagebox.askyesno(
                "SSH Service Required",
                "⚠️ Warning: Local SSH Server is currently DISABLED or not detected!\n\n"
                "To safely manage and browse remote nodes, SSH must be enabled.\n\n"
                "Click 'Yes' to attempt starting SSH automatically, or 'No' to close.",
                icon=messagebox.WARNING
            )
            if answer:
                try:
                    subprocess.run(["sudo", "systemctl", "start", "ssh"], check=False)
                    time.sleep(1)
                    return True
                except Exception:
                    return True
            else:
                return False
        return True

    def add_ip(self, ip_to_add=None, name_to_add=None, save=True):
        ip_input = ip_to_add if ip_to_add else self.ip_combobox.get().strip()
        name_input = name_to_add if name_to_add else self.name_entry.get().strip()

        if not ip_input:
            if not ip_to_add:
                messagebox.showwarning("Warning", "Please enter a valid IP address or suffix.")
            return

        if not any(char.isalpha() for char in ip_input) and "." not in ip_input:
            ip = f"192.168.0.{ip_input}"
        else:
            ip = ip_input

        if ip in self.monitored_ips:
            if not ip_to_add:
                messagebox.showinfo("Info", "This IP is already being monitored.")
            return

        if not name_input:
            name_input = "PC"

        if ip not in self.past_ips:
            self.past_ips.append(ip)
            self.save_history()
            self.ip_combobox['values'] = self.past_ips

        row_frame = ttk.Frame(self.scrollable_frame, padding=4)
        row_frame.pack(fill="x", expand=True)

        lbl_name = ttk.Label(row_frame, text=f"[{name_input}]", width=12, font=("Arial", 9, "italic"))
        lbl_name.pack(side="left", padx=2)

        lbl_ip = ttk.Label(row_frame, text=ip, width=16, font=("Courier", 10, "bold"))
        lbl_ip.pack(side="left", padx=4)

        lbl_status = tk.Label(row_frame, text="CHECKING...", bg="orange", fg="white", width=10, font=("Arial", 9, "bold"))
        lbl_status.pack(side="left", padx=4)

        # Action Buttons
        btn_remove = ttk.Button(row_frame, text="Remove", width=7, command=lambda: self.remove_ip(ip, row_frame))
        btn_remove.pack(side="right", padx=2)

        btn_rename = ttk.Button(row_frame, text="Rename", width=7, command=lambda: self.rename_ip(ip))
        btn_rename.pack(side="right", padx=2)

        btn_files = ttk.Button(row_frame, text="Files (GUI)", width=9, command=lambda: self.open_sftp_explorer(ip, name_input))
        btn_files.pack(side="right", padx=2)

        btn_ssh = ttk.Button(row_frame, text="Terminal", width=8, command=lambda: self.open_ssh_terminal(ip))
        btn_ssh.pack(side="right", padx=2)

        self.monitored_ips[ip] = {
            "status_label": lbl_status, 
            "name": name_input, 
            "name_label": lbl_name,
            "row_frame": row_frame,
            "is_online": False
        }

        if not ip_to_add:
            self.ip_combobox.set("")
            self.name_entry.delete(0, tk.END)

        if save:
            self.save_ips_to_file()

    def open_ssh_terminal(self, ip):
        username = simpledialog.askstring("SSH Login", f"Enter SSH username for {ip}:", initialvalue="s7cse")
        if username:
            try:
                subprocess.Popen(["gnome-terminal", "--", "ssh", f"{username}@{ip}"])
            except Exception as e:
                messagebox.showerror("Error", f"Could not open terminal: {e}")

    def open_sftp_explorer(self, ip, name):
        if not PARAMIKO_AVAILABLE:
            messagebox.showerror("Missing Library", "Please install Paramiko:\nsudo apt install python3-paramiko")
            return

        explorer_win = tk.Toplevel(self.root)
        explorer_win.title(f"SFTP Explorer & Remote Runner [{name} - {ip}]")
        explorer_win.geometry("980x620")
        explorer_win.transient(self.root)

        top_bar = ttk.Frame(explorer_win, padding=8)
        top_bar.pack(fill="x", padx=5, pady=5)

        ttk.Label(top_bar, text="User:").pack(side="left", padx=2)
        user_entry = ttk.Entry(top_bar, width=8)
        user_entry.insert(0, "s7cse")
        user_entry.pack(side="left", padx=2)

        ttk.Label(top_bar, text="Pass:").pack(side="left", padx=2)
        pass_entry = ttk.Entry(top_bar, width=8, show="*")
        pass_entry.pack(side="left", padx=2)

        ttk.Label(top_bar, text="Path:").pack(side="left", padx=2)
        path_entry = ttk.Entry(top_bar, width=18)
        path_entry.insert(0, "/home/")
        path_entry.pack(side="left", padx=2)

        # File tree view
        tree_frame = ttk.Frame(explorer_win)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        tree = ttk.Treeview(tree_frame, columns=("Type", "Size", "Name"), show="headings", height=12)
        tree.heading("Type", text="Type")
        tree.heading("Size", text="Size")
        tree.heading("Name", text="File / Folder Name")
        tree.column("Type", width=80, anchor="center")
        tree.column("Size", width=90, anchor="e")
        tree.column("Name", width=740)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        action_bar = ttk.Frame(explorer_win, padding=5)
        action_bar.pack(fill="x", padx=5, pady=2)

        log_frame = ttk.LabelFrame(explorer_win, text=" Live Debug Console ", padding=5)
        log_frame.pack(fill="both", expand=False, padx=5, pady=5)

        debug_box = tk.Text(log_frame, height=5, bg="#1e1e1e", fg="#00ff00", font=("Courier", 9))
        debug_box.pack(fill="both", expand=True)
        debug_box.insert(tk.END, ">>> Debug console initialized. Ready...\n")

        def log_msg(msg):
            debug_box.insert(tk.END, f"{msg}\n")
            debug_box.see(tk.END)

        def load_files_sftp():
            username = user_entry.get().strip()
            password = pass_entry.get()
            path = path_entry.get().strip()

            if not username or not password:
                messagebox.showwarning("Warning", "Please enter username and password.")
                return

            tree.delete(*tree.get_children())
            log_msg(f"\n[INFO] Connecting to {ip}:22 as '{username}'...")

            def background_sftp():
                try:
                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    log_msg("[SUCCESS] Connected to server successfully!")

                    log_msg("[INFO] Detecting remote desktop display environment variables...")
                    env_detect_cmd = (
                        'GUI_PID=$(pgrep -u $USER -n -f "gnome-shell|plasma|xfce4-session|Xwayland|Xorg" | head -n 1); '
                        'if [ -n "$GUI_PID" ]; then '
                        '  export $(cat /proc/$GUI_PID/environ 2>/dev/null | tr "\\0" "\\n" | grep -E "^(DISPLAY|XAUTHORITY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR)="); '
                        'fi; '
                        '[ -z "$DISPLAY" ] && export DISPLAY=:0; '
                        'echo "DISPLAY is set to: $DISPLAY"'
                    )
                    
                    chan = transport.open_session()
                    chan.exec_command(env_detect_cmd)
                    out = chan.makefile('r', -1).read().strip()
                    log_msg(f"[SUCCESS] Environment check result: {out}")

                    sftp = paramiko.SFTPClient.from_transport(transport)
                    file_list = sftp.listdir_attr(path)
                    log_msg(f"[SUCCESS] Retrieved {len(file_list)} items from '{path}'.")
                    
                    def update_ui():
                        for attr in file_list:
                            filename = attr.filename
                            if filename in [".", ".."]:
                                continue
                            is_dir = stat.S_ISDIR(attr.st_mode)
                            f_type = "[Folder]" if is_dir else "[File]"
                            size_str = f"{attr.st_size} B" if not is_dir else "-"
                            tree.insert("", "end", values=(f_type, size_str, filename))
                        tree.update_idletasks()

                    explorer_win.after(0, update_ui)
                    sftp.close()
                    transport.close()
                except Exception as e:
                    log_msg(f"[ERROR] {str(e)}")

            threading.Thread(target=background_sftp, daemon=True).start()

        def go_back_dir():
            current_path = path_entry.get().strip().rstrip("/")
            parent_path = os.path.dirname(current_path)
            if not parent_path:
                parent_path = "/"
            path_entry.delete(0, tk.END)
            path_entry.insert(0, parent_path)
            load_files_sftp()

        def copy_selected_path():
            selected_item = tree.selection()
            if not selected_item:
                messagebox.showwarning("Warning", "Please select a file or folder first.")
                return
            item_values = tree.item(selected_item, "values")
            filename = item_values[2]
            current_path = path_entry.get().strip().rstrip("/")
            full_target_path = f"{current_path}/{filename}"
            
            explorer_win.clipboard_clear()
            explorer_win.clipboard_append(full_target_path)
            log_msg(f"[INFO] Copied path to clipboard: {full_target_path}")
            messagebox.showinfo("Copied", f"Path copied to clipboard:\n{full_target_path}")

        def create_new_file():
            new_filename = simpledialog.askstring("New File", "Enter file name (e.g., code.sh, index.html):", parent=explorer_win)
            if not new_filename:
                return

            current_path = path_entry.get().strip().rstrip("/")
            remote_file_path = f"{current_path}/{new_filename}"
            username = user_entry.get().strip()
            password = pass_entry.get()

            def bg_create_file():
                try:
                    log_msg(f"[INFO] Creating new empty file: {remote_file_path}")
                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)
                    
                    local_temp_path = os.path.join("/tmp", new_filename)
                    open(local_temp_path, 'w').close()
                    
                    sftp.put(local_temp_path, remote_file_path)
                    sftp.close()
                    transport.close()

                    log_msg(f"[SUCCESS] File created remotely. Opening in local Gedit...")
                    subprocess.run(["gedit", local_temp_path])

                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)
                    sftp.put(local_temp_path, remote_file_path)
                    sftp.close()
                    transport.close()
                    
                    log_msg(f"[SUCCESS] Code synced and uploaded back to remote {remote_file_path}")
                    explorer_win.after(0, load_files_sftp)
                except Exception as e:
                    log_msg(f"[ERROR] Failed to create/edit file: {e}")

            threading.Thread(target=bg_create_file, daemon=True).start()

        def download_selected_file():
            selected_item = tree.selection()
            if not selected_item:
                messagebox.showwarning("Warning", "Please select a file to download.")
                return
            item_values = tree.item(selected_item, "values")
            if "Folder" in item_values[0]:
                messagebox.showwarning("Warning", "Please use 'Download Folder' for directories.")
                return
            
            filename = item_values[2]
            current_path = path_entry.get().strip()
            remote_file_path = os.path.join(current_path, filename).replace("\\", "/")
            
            local_save_dir = filedialog.askdirectory(title="Select Local Save Folder")
            if not local_save_dir:
                return

            username = user_entry.get().strip()
            password = pass_entry.get()

            def bg_download():
                try:
                    log_msg(f"[INFO] Downloading file '{filename}'...")
                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)
                    
                    local_file_path = os.path.join(local_save_dir, filename)
                    sftp.get(remote_file_path, local_file_path)
                    
                    sftp.close()
                    transport.close()
                    log_msg(f"[SUCCESS] Downloaded file to {local_file_path}")
                    explorer_win.after(0, lambda: messagebox.showinfo("Success", f"File downloaded successfully to:\n{local_file_path}"))
                except Exception as e:
                    log_msg(f"[ERROR] Download failed: {str(e)}")

            threading.Thread(target=bg_download, daemon=True).start()

        def download_selected_folder():
            selected_item = tree.selection()
            if not selected_item:
                messagebox.showwarning("Warning", "Please select a folder to download.")
                return
            item_values = tree.item(selected_item, "values")
            if "Folder" not in item_values[0]:
                messagebox.showwarning("Warning", "Selected item is not a folder.")
                return

            foldername = item_values[2]
            current_path = path_entry.get().strip()
            remote_folder_path = os.path.join(current_path, foldername).replace("\\", "/")

            local_save_dir = filedialog.askdirectory(title="Select Local Destination Folder")
            if not local_save_dir:
                return

            username = user_entry.get().strip()
            password = pass_entry.get()

            def bg_download_folder():
                try:
                    log_msg(f"[INFO] Starting recursive download of folder '{foldername}'...")
                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)

                    local_target_dir = os.path.join(local_save_dir, foldername)
                    os.makedirs(local_target_dir, exist_ok=True)

                    def recursive_sftp_get(remote_dir, local_dir):
                        for entry in sftp.listdir_attr(remote_dir):
                            r_path = f"{remote_dir}/{entry.filename}"
                            l_path = os.path.join(local_dir, entry.filename)
                            if stat.S_ISDIR(entry.st_mode):
                                os.makedirs(l_path, exist_ok=True)
                                recursive_sftp_get(r_path, l_path)
                            else:
                                sftp.get(r_path, l_path)

                    recursive_sftp_get(remote_folder_path, local_target_dir)

                    sftp.close()
                    transport.close()
                    log_msg(f"[SUCCESS] Folder downloaded completely to {local_target_dir}")
                    explorer_win.after(0, lambda: messagebox.showinfo("Success", f"Folder downloaded successfully to:\n{local_target_dir}"))
                except Exception as e:
                    log_msg(f"[ERROR] Folder download failed: {str(e)}")

            threading.Thread(target=bg_download_folder, daemon=True).start()

        def open_in_local_gedit():
            selected_item = tree.selection()
            if not selected_item:
                messagebox.showwarning("Warning", "Please select a file to open in Gedit.")
                return
            item_values = tree.item(selected_item, "values")
            if "Folder" in item_values[0]:
                messagebox.showwarning("Warning", "Cannot open folders in Gedit.")
                return
            
            filename = item_values[2]
            current_path = path_entry.get().strip()
            remote_file_path = os.path.join(current_path, filename).replace("\\", "/")
            username = user_entry.get().strip()
            password = pass_entry.get()

            def bg_gedit_sync():
                try:
                    log_msg(f"[INFO] Downloading '{filename}' to local temp folder for Gedit...")
                    transport = paramiko.Transport((ip, 22))
                    transport.connect(username=username, password=password)
                    sftp = paramiko.SFTPClient.from_transport(transport)
                    
                    local_temp_path = os.path.join("/tmp", filename)
                    sftp.get(remote_file_path, local_temp_path)
                    
                    mtime_before = os.path.getmtime(local_temp_path)

                    log_msg(f"[INFO] Opening local file in Gedit: {local_temp_path}")
                    subprocess.run(["gedit", local_temp_path])

                    mtime_after = os.path.getmtime(local_temp_path)
                    if mtime_after > mtime_before:
                        log_msg(f"[INFO] File modified locally. Uploading changes back to remote {remote_file_path}...")
                        sftp.put(local_temp_path, remote_file_path)
                        log_msg(f"[SUCCESS] Changes uploaded back to remote PC successfully!")
                        explorer_win.after(0, lambda: messagebox.showinfo("Synced", "Changes saved and uploaded back to remote PC!"))
                    else:
                        log_msg("[INFO] No changes detected in file.")

                    sftp.close()
                    transport.close()
                except Exception as e:
                    log_msg(f"[ERROR] Gedit sync error: {e}")

            threading.Thread(target=bg_gedit_sync, daemon=True).start()

        def run_script_remotely():
            selected_item = tree.selection()
            if not selected_item:
                messagebox.showwarning("Warning", "Please select a file to run remotely.")
                return
            item_values = tree.item(selected_item, "values")
            if "Folder" in item_values[0]:
                messagebox.showwarning("Warning", "Cannot execute a folder.")
                return

            filename = item_values[2]
            current_path = path_entry.get().strip()
            username = user_entry.get().strip()
            password = pass_entry.get()

            def bg_run_remote():
                try:
                    log_msg(f"[INFO] Opening '{filename}' on remote monitor session...")
                    
                    # Command includes a fallback if GUI_PID fails due to cross-user permissions
                    remote_cmd = (
                        f'GUI_PID=$(pgrep -u $USER -n -f "gnome-shell|plasma|xfce4-session|Xwayland|Xorg" | head -n 1); '
                        f'if [ -n "$GUI_PID" ]; then '
                        f'  export $(cat /proc/$GUI_PID/environ 2>/dev/null | tr "\\0" "\\n" | grep -E "^(DISPLAY|XAUTHORITY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR)="); '
                        f'fi; '
                        f'[ -z "$DISPLAY" ] && export DISPLAY=:0; '
                        f'cd "{current_path}" && firefox "{filename}"'
                    )

                    ssh_cmd = ["sshpass", "-p", password, "ssh", "-o", "StrictHostKeyChecking=no", f"{username}@{ip}", remote_cmd]
                    
                    res = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                    if res.returncode == 0:
                        log_msg(f"[SUCCESS] Opened successfully on remote monitor!")
                        explorer_win.after(0, lambda: messagebox.showinfo("Success", f"Opened '{filename}' on remote monitor successfully!"))
                    else:
                        log_msg(f"[ERROR] Execution error: {res.stderr.strip()}")
                except Exception as e:
                    log_msg(f"[ERROR] Failed to run remotely: {e}")

            threading.Thread(target=bg_run_remote, daemon=True).start()

        btn_connect = ttk.Button(top_bar, text="Connect", command=load_files_sftp)
        btn_connect.pack(side="left", padx=2)

        btn_back = ttk.Button(action_bar, text="Back", command=go_back_dir)
        btn_back.pack(side="left", padx=2)

        btn_new = ttk.Button(action_bar, text="+ New File", command=create_new_file)
        btn_new.pack(side="left", padx=2)

        btn_copy = ttk.Button(action_bar, text="Copy Path", command=copy_selected_path)
        btn_copy.pack(side="left", padx=2)

        btn_download = ttk.Button(action_bar, text="Download File", command=download_selected_file)
        btn_download.pack(side="left", padx=2)

        btn_dl_folder = ttk.Button(action_bar, text="Download Folder", command=download_selected_folder)
        btn_dl_folder.pack(side="left", padx=2)

        btn_gedit = ttk.Button(action_bar, text="Edit in Gedit", command=open_in_local_gedit)
        btn_gedit.pack(side="left", padx=2)

        btn_run = ttk.Button(action_bar, text="▶ Open in Remote Browser", command=run_script_remotely)
        btn_run.pack(side="left", padx=2)

        def on_item_double_click(event):
            selected_item = tree.selection()
            if selected_item:
                item_values = tree.item(selected_item, "values")
                if item_values and "Folder" in item_values[0]:
                    folder_name = item_values[2]
                    current_path = path_entry.get().strip().rstrip("/")
                    new_path = f"{current_path}/{folder_name}"
                    path_entry.delete(0, tk.END)
                    path_entry.insert(0, new_path)
                    load_files_sftp()

        tree.bind("<Double-1>", on_item_double_click)

    def rename_ip(self, ip):
        if ip not in self.monitored_ips:
            return
        current_name = self.monitored_ips[ip]["name"]
        new_name = simpledialog.askstring("Rename Tag", f"Enter new label for {ip}:", initialvalue=current_name)
        if new_name and new_name.strip():
            new_name = new_name.strip()
            self.monitored_ips[ip]["name"] = new_name
            self.monitored_ips[ip]["name_label"].config(text=f"[{new_name}]")
            self.save_ips_to_file()

    def remove_ip(self, ip, frame):
        if ip in self.monitored_ips:
            del self.monitored_ips[ip]
        frame.destroy()
        self.save_ips_to_file()

    def open_scanner_window(self):
        scan_win = tk.Toplevel(self.root)
        scan_win.title("Subnet Network Scanner")
        scan_win.geometry("400x450")
        scan_win.transient(self.root)

        lbl_info = ttk.Label(scan_win, text="Scanning port 22 on 192.168.0.1-254...", font=("Arial", 10, "bold"))
        lbl_info.pack(pady=10)

        listbox_frame = ttk.Frame(scan_win)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)

        ip_listbox = tk.Listbox(listbox_frame, font=("Courier", 11), selectmode=tk.SINGLE)
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=ip_listbox.yview)
        ip_listbox.configure(yscrollcommand=scrollbar.set)

        ip_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        found_ips = []

        def scan_network():
            def check_port(ip):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(1)
                        if s.connect_ex((ip, 22)) == 0:
                            found_ips.append(ip)
                            scan_win.after(0, lambda: ip_listbox.insert(tk.END, ip))
                except Exception:
                    pass

            threads = []
            for i in range(1, 255):
                target_ip = f"192.168.0.{i}"
                t = threading.Thread(target=check_port, args=(target_ip,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            scan_win.after(0, lambda: lbl_info.config(text=f"Scan Complete! Discovered {len(found_ips)} SSH nodes."))

        threading.Thread(target=scan_network, daemon=True).start()

        def add_selected_ip():
            selection = ip_listbox.curselection()
            if selection:
                selected_ip = ip_listbox.get(selection[0])
                self.ip_combobox.set(selected_ip.split(".")[-1])
                self.name_entry.focus_set()
                scan_win.destroy()
            else:
                messagebox.showwarning("Warning", "Please select an IP first.")

        btn_select = ttk.Button(scan_win, text="Use Selected IP", command=add_selected_ip)
        btn_select.pack(pady=10)

    def save_ips_to_file(self):
        try:
            data_to_save = {ip: details["name"] for ip, details in self.monitored_ips.items()}
            with open(CONFIG_FILE, "w") as f:
                json.dump(data_to_save, f)
        except Exception as e:
            print(f"Error saving IPs: {e}")

    def load_saved_ips(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        for ip in content:
                            self.add_ip(ip_to_add=ip, name_to_add="PC", save=False)
                    elif isinstance(content, dict):
                        for ip, name in content.items():
                            self.add_ip(ip_to_add=ip, name_to_add=name, save=False)
            except Exception as e:
                print(f"Error loading saved IPs: {e}")
        
        if not self.monitored_ips and os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    hist_ips = json.load(f)
                    for ip in hist_ips:
                        self.add_ip(ip_to_add=ip, name_to_add="PC", save=False)
            except Exception:
                pass

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.past_ips, f)
        except Exception as e:
            print(f"Error saving history: {e}")

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    self.past_ips = json.load(f)
            except Exception as e:
                print(f"Error loading history: {e}")

    def ping_host(self, ip):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                return s.connect_ex((ip, 22)) == 0
        except Exception:
            return False

    def background_monitor(self):
        while self.running:
            ips_to_check = list(self.monitored_ips.keys())
            online_count = 0
            offline_count = 0

            for ip in ips_to_check:
                if ip not in self.monitored_ips:
                    continue
                
                is_active = self.ping_host(ip)
                if is_active:
                    online_count += 1
                else:
                    offline_count += 1

                if ip in self.monitored_ips:
                    label = self.monitored_ips[ip]["status_label"]
                    self.monitored_ips[ip]["is_online"] = is_active
                    if is_active:
                        self.root.after(0, lambda l=label: l.config(text="ONLINE", bg="#2ecc71", fg="white"))
                    else:
                        self.root.after(0, lambda l=label: l.config(text="OFFLINE", bg="#e74c3c", fg="white"))
            
            total = len(ips_to_check)
            status_text = f"Monitored Nodes: {total} | Online: {online_count} | Offline: {offline_count}"
            self.root.after(0, lambda: self.status_bar.config(text=status_text))

            time.sleep(3)

    def on_closing(self, event=None):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = IPMonitorApp(root)
    if app.running:
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()