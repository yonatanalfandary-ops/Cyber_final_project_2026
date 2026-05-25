import os
import sys
import json
import tkinter as tk
from tkinter import messagebox
from client.network_client import NetworkClient
from client.lock_screen import LockScreen
from client.login_window import LoginWindow
from client.rent_window import RentWindow
from client.admin_panel import AdminPanel
from client.biometric_scanner import BiometricScanner
from client.session_guard import SessionGuard
from client.smart_lockscreen import SmartLockScreen

# --- Configuration ---
# Fallback used only on the very first run, before the IP prompt has anything saved to pre-fill with.
DEFAULT_SERVER_IP = "10.0.0.24"
SYNC_INTERVAL = 5
# station_config.json lives at the project root (next to client/, server/, shared/),
# not inside client/. Walking up one directory from this file's location reaches the root.
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'station_config.json'
)


class MainClient:
    """
    Top-level client controller. Owns the network connection, the biometric
    scanner, and the state-machine that moves the station between its lock
    screen, authenticated session, and admin panel states.
    """

    def __init__(self):
        self.station_id = None

        # Prompt for the server IP, pre-filled with the last working one.
        # Loop on connection failure so the user can correct a typo without
        # having to restart the program.
        last_ip = self._load_last_ip()

        while True:
            server_ip = self._prompt_for_server_ip(last_ip)
            if not server_ip:
                # User cancelled the prompt — exit cleanly.
                sys.exit()

            self.net = NetworkClient(server_ip)
            if self.net.connect():
                # Connection succeeded — persist this IP so it pre-fills next time.
                self._save_last_ip(server_ip)
                break

            # Connection failed — surface the error in a Tk popup and re-prompt
            # with whatever IP they just tried already in the field.
            err_root = tk.Tk()
            err_root.withdraw()
            messagebox.showerror(
                "Connection Failed",
                f"Could not connect to server at {server_ip}.\n"
                "Please check the IP address and try again."
            )
            err_root.destroy()
            last_ip = server_ip

        self._init_station()

        self.locker = None
        self.scanner = BiometricScanner()
        self.current_user = None

    def _init_station(self):
        """
        Initialises the station's identity. Reads a station ID from the
        local config file if one exists, otherwise asks the server to
        allocate a new one and persists it for future runs.
        """
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                self.station_id = json.load(f).get("station_id")

        if self.station_id:
            resp = self.net.send_request("CONNECT_STATION", {"station_id": self.station_id})
        else:
            resp = self.net.send_request("REQUEST_NEW_STATION_ID", {})

        # If another running client is already using this station ID, the
        # server rejects the connection. Surface a clear error and exit so
        # both clients aren't talking to the same server slot at once.
        if resp and resp.get("status") == "ERROR_STATION_IN_USE":
            temp_root = tk.Tk()
            temp_root.withdraw()

            # Blocks until the user clicks OK.
            messagebox.showerror("Connection Error",
                                 "Error: This Station ID is currently active on another computer.")

            # Force a hard exit so no further work is done.
            temp_root.destroy()
            os._exit(0)

        # The server may also have issued a kill-switch wipe while we were
        # offline; honour it by deleting the local config and exiting.
        if resp and resp.get("action") == "COMMAND_UNREGISTER":
            if os.path.exists(CONFIG_PATH): os.remove(CONFIG_PATH)
            sys.exit(0)

        # If the server allocated a new ID for us, persist it for next run.
        # Load existing config first so we don't overwrite other fields (like last_ip).
        if resp and resp.get("status") == "SUCCESS" and resp.get("new_id"):
            self.station_id = resp.get("new_id")
            existing_config = {}
            try:
                if os.path.exists(CONFIG_PATH):
                    with open(CONFIG_PATH, 'r') as f:
                        existing_config = json.load(f)
            except Exception:
                existing_config = {}
            existing_config["station_id"] = self.station_id
            with open(CONFIG_PATH, 'w') as f:
                json.dump(existing_config, f)

        if not self.station_id:
            print("Failed to initialize Station ID.")
            sys.exit()

        print(f"Station Initialized as: {self.station_id}")

    def run(self):
        """Main state-machine loop. Cycles between lock screen and active session."""
        while True:
            # State 1: Lock screen — waits for a user to begin authentication.
            self.locker = LockScreen(on_submit_callback=self.process_login)
            self.locker.lock()

            # State 2: Authenticated — branch by role.
            if self.current_user:
                if self.current_user['role'] == 'root':
                    # Admins go straight to the admin panel.
                    admin = AdminPanel(self.net, self.current_user['username'])
                    admin.show()
                    self._execute_logout()
                else:
                    # Standard users run an active session loop that can be
                    # paused (smart lock) or terminated (logout).
                    while self.current_user:
                        guard = SessionGuard(self.net, self.current_user)
                        status = guard.start()

                        if status == "PAUSED":
                            print(f"Session paused for {self.current_user['username']}. Updating server...")

                            # Notify the server that the station is in the Paused state.
                            self.net.send_request("SYNC_STATE", {
                                "state_status": "Paused",
                                "active_user": self.current_user['username']
                            })

                            privacy = self._fetch_privacy_setting()
                            smart_lock = SmartLockScreen(self.current_user, self.scanner, privacy_screen=privacy)
                            lock_result = smart_lock.show()

                            if lock_result == "RESUME":
                                print(f"Session resumed for {self.current_user['username']}. Updating server...")

                                # Notify the server that the station is back In Use.
                                self.net.send_request("SYNC_STATE", {
                                    "state_status": "In Use",
                                    "active_user": self.current_user['username']
                                })
                                continue
                            else:
                                # Timed out or user explicitly logged out from the smart lock.
                                self._execute_logout()
                                print("User logged out from pause.")
                                break

                        elif status == "LOGOUT":
                            # Standard logout from the session HUD.
                            self._execute_logout()
                            print("User logged out.")
                            break

    def _execute_logout(self):
        """Notifies the server to revert the station status back to Online."""
        self.net.send_request("LOGOUT", {})
        self.current_user = None

    def _fetch_privacy_setting(self):
        """Returns True if the privacy-screen option is enabled on the server."""
        try:
            response = self.net.send_request("GET_SETTING", {"key": "privacy_screen"})
            if response and response.get("status") == "SUCCESS":
                return response.get("value") == "1"
        except Exception:
            pass
        return False

    def _load_last_ip(self):
        """Returns the last-used server IP from the config file, or the default if none is stored."""
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    return config.get("last_ip", DEFAULT_SERVER_IP)
        except Exception:
            pass
        return DEFAULT_SERVER_IP

    def _save_last_ip(self, ip):
        """Persists the given IP to the config file without disturbing other fields (e.g. station_id)."""
        config = {}
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
        except Exception:
            config = {}

        config["last_ip"] = ip

        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Warning: could not save IP to config: {e}")

    def _prompt_for_server_ip(self, default_ip):
        """
        Displays a small Tk dialog asking the user for the server IP. The field is
        pre-filled with default_ip so the user can usually just press Enter to accept.
        Returns the entered IP string, or None if the user cancelled.
        """

        result = {"ip": None}

        root = tk.Tk()
        root.title("Server Connection")
        root.configure(bg="#2c3e50")

        # Center the dialog on the screen.
        width, height = 420, 220
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.attributes('-topmost', True)
        root.resizable(False, False)

        tk.Label(root, text="Enter Server IP Address:", font=("Arial", 14, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=(25, 10))

        ip_var = tk.StringVar(value=default_ip)
        entry = tk.Entry(root, textvariable=ip_var, font=("Arial", 14),
                         width=20, justify='center')
        entry.pack(pady=5)
        entry.focus_set()
        entry.select_range(0, tk.END)

        def on_ok(event=None):
            ip = ip_var.get().strip()
            if ip:
                result["ip"] = ip
                root.destroy()

        def on_cancel(event=None):
            root.destroy()

        btn_frame = tk.Frame(root, bg="#2c3e50")
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="Connect", command=on_ok,
                  font=("Arial", 12, "bold"), bg="#27ae60", fg="white",
                  width=12).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_cancel,
                  font=("Arial", 12), bg="#c0392b", fg="white",
                  width=12).pack(side="left", padx=5)

        # Convenience bindings: Enter to confirm, Escape or window-close to cancel.
        root.bind('<Return>', on_ok)
        root.bind('<Escape>', on_cancel)
        root.protocol("WM_DELETE_WINDOW", on_cancel)

        root.mainloop()
        return result["ip"]

    def process_login(self, username):
        """
        Handles a username submitted from the lock screen.

        The flow is:
          1. Look up the user on the server.
          2. If they have no face encoding, route admins to manual login
             and reject standard users with a clear message.
          3. Otherwise run a targeted face scan against that user.
          4. On a successful scan, either start the session (if they have
             balance or are an admin) or open the rent window first.
        """
        print(f"Checking database for user: {username}...")
        response = self.net.send_request("FETCH_USER", {"username": username})
        target_user = None

        if response and response.get("status") == "SUCCESS":
            target_user = response.get("user")

        if not target_user:
            print("Username not found.")
            self.locker.reset_to_start("Username not found")
            return

        if not target_user.get('face_encoding'):
            if target_user.get('role') == 'root':
                print("Root without face ID. Routing instantly to manual login.")
                self.locker.reset_to_start("")
                self._trigger_manual_login()
            else:
                print("Standard user has no face ID. Blocking access.")
                self.locker.reset_to_start("No Face ID setup. Please see Admin.")
            return

        print("Face ID found. Starting targeted scan...")
        privacy = self._fetch_privacy_setting()
        if privacy:
            # Privacy mode: hide the lock-screen contents but keep the black
            # backdrop, so the desktop is never briefly exposed.
            self.locker.blank()
        else:
            self.locker.root.withdraw()
        match = self.scanner.scan_specific_user(target_user)

        if match:
            print("Face Matched!")
            balance = float(target_user.get('time_balance', 0))

            if target_user['role'] == 'root' or balance > 0:
                # Notify the server that the face-ID unlock succeeded.
                resp = self.net.send_request("SYNC_STATE", {
                    "state_status": "In Use",
                    "active_user": target_user['username']
                })

                # If the same user is already logged in on another station,
                # block this login and return to the lock screen.
                if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                    print("Login Blocked: User already active elsewhere.")
                    self.locker.root.after(0, lambda: messagebox.showerror("Login Failed",
                                                                           "User is already logged in on another station.",
                                                                           parent=self.locker.root))
                    self.locker.root.deiconify()
                    self.locker.reset_to_start("Already logged in elsewhere.")
                    return

                self.current_user = target_user
                self.locker.unlock()
            else:
                # The user has no remaining balance; open the rent window.
                print("Balance is 0. Opening Rent Window...")
                renter = RentWindow(self.net, target_user['username'])

                raw_minutes = renter.show()
                try:
                    minutes_added = float(raw_minutes if raw_minutes else 0)
                except (ValueError, TypeError):
                    minutes_added = 0

                if minutes_added > 0:
                    print(f"Rent successful! Adding {minutes_added} mins to session.")

                    # Notify the server now that the user has paid and the
                    # session is about to begin.
                    resp = self.net.send_request("SYNC_STATE", {
                        "state_status": "In Use",
                        "active_user": target_user['username']
                    })

                    # Duplicate-login check after the rent transaction.
                    if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                        print("Login Blocked: User already active elsewhere.")
                        self.locker.root.after(0, lambda: messagebox.showerror("Login Failed",
                                                                               "User is already logged in on another station.",
                                                                               parent=self.locker.root))
                        self.locker.root.deiconify()
                        self.locker.reset_to_start("Already logged in elsewhere.")
                        return

                    target_user['time_balance'] = minutes_added
                    self.current_user = target_user
                    self.locker.unlock()
                else:
                    print("Payment cancelled. Returning to Lock Screen.")
                    if privacy:
                        self.locker.unblank()
                    else:
                        self.locker.root.deiconify()
                    self.locker.reset_to_start()
        else:
            print("Face match failed. Access Denied.")
            if privacy:
                self.locker.unblank()
            else:
                self.locker.root.deiconify()

            if target_user.get('role') == 'root':
                # Admin face scan failed — fall back to manual password
                # login rather than sending them back to the lock screen.
                print("Admin detected — routing to manual login.")
                self.locker.reset_to_start("")
                self._trigger_manual_login()
            else:
                self.locker.reset_to_start("Face match failed. Access Denied.")

    def _trigger_manual_login(self):
        """Tears down the lock screen and opens the admin password login window."""
        self.locker.unlock()
        self.manual_login_sequence()

    def manual_login_sequence(self):
        """Admin fallback flow for password-based authentication."""
        login = LoginWindow(self.net, self.station_id)
        user_data = login.show()

        if user_data:
            role = user_data.get('role')

            if role == 'root':
                print(f"Root {user_data['username']} authenticated manually.")

                # Notify the server that a manual admin login succeeded.
                resp = self.net.send_request("SYNC_STATE", {
                    "state_status": "In Use",
                    "active_user": user_data['username']
                })

                # Duplicate-login check for manual admin login.
                if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                    print("Login Blocked: already active elsewhere.")
                    if self.locker and self.locker.root:
                        self.locker.root.after(0, lambda: messagebox.showerror("Login Failed", "User is already logged in on another station.", parent=self.locker.root))
                        self.locker.root.deiconify()
                        self.locker.reset_to_start("Already logged in elsewhere.")
                    return

                self.current_user = user_data
            else:
                # Defensive guard: standard users should never reach the
                # manual login window in the first place, but in case they
                # do, reject the attempt with a clear message.
                print("Access Denied: Standard users cannot use manual login.")
                if self.locker and self.locker.root:
                    self.locker.root.deiconify()
                    self.locker.reset_to_start("Users must use Face ID.")


if __name__ == "__main__":
    app = MainClient()
    app.run()