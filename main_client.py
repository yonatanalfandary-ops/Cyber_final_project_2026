import cv2
import numpy as np
import time
import os
import sys
import json
import face_recognition
from network_client import NetworkClient
from lock_screen import LockScreen
from login_window import LoginWindow
from rent_window import RentWindow
import tkinter as tk
from settings_window import SettingsWindow
from admin_panel import AdminPanel
from biometric_scanner import BiometricScanner
from session_guard import SessionGuard
from smart_lockscreen import SmartLockScreen

# CONFIG
SERVER_IP = "172.16.63.55" #"10.0.0.24"
SYNC_INTERVAL = 5
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'station_config.json')


class MainClient:
    def __init__(self):
        self.station_id = None
        self.net = NetworkClient(SERVER_IP)
        if not self.net.connect(): sys.exit()

        self._init_station()

        self.locker = None
        self.scanner = BiometricScanner()
        self.current_user = None

    def _init_station(self):
        """Reads local config or asks Server to generate a Gap ID."""
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                self.station_id = json.load(f).get("station_id")

        if self.station_id:
            resp = self.net.send_request("CONNECT_STATION", {"station_id": self.station_id})
        else:
            resp = self.net.send_request("REQUEST_NEW_STATION_ID", {})

        # --- TASK 12 FIX: Check for duplicate Station ID ---
        if resp and resp.get("status") == "ERROR_STATION_IN_USE":
            import tkinter as tk
            from tkinter import messagebox
            temp_root = tk.Tk()
            temp_root.withdraw()  # Hide the main window

            # Show the error directly (this pauses execution until OK is clicked)
            messagebox.showerror("Connection Error",
                                 "Error: This Station ID is currently active on another computer.")

            # Clean up and force exit immediately after OK is clicked
            temp_root.destroy()
            os._exit(0)

        # Catch if the Wipe payload happened during initialization
        if resp and resp.get("action") == "COMMAND_UNREGISTER":
            if os.path.exists(CONFIG_PATH): os.remove(CONFIG_PATH)
            sys.exit(0)

        # Save new Gap ID
        if resp and resp.get("status") == "SUCCESS" and resp.get("new_id"):
            self.station_id = resp.get("new_id")
            with open(CONFIG_PATH, 'w') as f:
                json.dump({"station_id": self.station_id}, f)

        if not self.station_id:
            print("❌ Failed to initialize Station ID.")
            sys.exit()

        print(f"🖥️ Station Initialized as: {self.station_id}")

    def run(self):
        while True:
            # STATE 1: Lock Screen
            self.locker = LockScreen(on_submit_callback=self.process_login)
            self.locker.lock()

            # STATE 2: Authenticated
            if self.current_user:
                if self.current_user['role'] == 'root':
                    admin = AdminPanel(self.net, self.current_user['username'])
                    admin.show()
                    self._execute_logout()
                else:
                    while self.current_user:
                        guard = SessionGuard(self.net, self.current_user)
                        status = guard.start()

                        if status == "PAUSED":
                            print(f"⏸️ Session paused for {self.current_user['username']}. Updating server...")

                            # --- NEW: Tell server the station is Paused ---
                            self.net.send_request("SYNC_STATE", {
                                "state_status": "Paused",
                                "active_user": self.current_user['username']
                            })

                            privacy = self._fetch_privacy_setting()
                            smart_lock = SmartLockScreen(self.current_user, self.scanner, privacy_screen=privacy)
                            lock_result = smart_lock.show()

                            if lock_result == "RESUME":
                                print(f"▶️ Session resumed for {self.current_user['username']}. Updating server...")

                                # --- NEW: Tell server the station is back In Use ---
                                self.net.send_request("SYNC_STATE", {
                                    "state_status": "In Use",
                                    "active_user": self.current_user['username']
                                })
                                continue
                            else:
                                # User chose to logout from the paused smart lock screen
                                self._execute_logout()
                                print("User logged out from pause.")
                                break


                        # --- THE FIX: Handle normal logouts and add cooldown ---
                        elif status == "LOGOUT":
                            self._execute_logout()  # This correctly sets self.current_user = None
                            print("User logged out.")
                            break

    def _execute_logout(self):
        """Notifies the Server to revert status back to Online."""
        self.net.send_request("LOGOUT", {})
        self.current_user = None

    def _fetch_privacy_setting(self):
        """Returns True if the privacy screen is enabled on the server."""
        try:
            response = self.net.send_request("GET_SETTING", {"key": "privacy_screen"})
            if response and response.get("status") == "SUCCESS":
                return response.get("value") == "1"
        except Exception:
            pass
        return False

    def process_login(self, username):
        """Handles the 4-step login and routing logic."""
        print(f"🔍 Checking database for user: {username}...")
        response = self.net.send_request("FETCH_ALL_USERS", {})
        target_user = None

        if response and response.get("users"):
            for u in response['users']:
                if u['username'].lower() == username.lower():
                    target_user = u
                    break

        if not target_user:
            print("❌ Username not found.")
            self.locker.reset_to_start("Username not found")
            return

        if not target_user.get('face_encoding'):
            if target_user.get('role') == 'root':
                print("🛡️ Root without face ID. Routing instantly to manual login.")
                self.locker.reset_to_start("")
                self._trigger_manual_login()
            else:
                print("⚠️ Standard user has no face ID. Blocking access.")
                self.locker.reset_to_start("No Face ID setup. Please see Admin.")
            return

        print("📸 Face ID found. Starting targeted scan...")
        privacy = self._fetch_privacy_setting()
        if privacy:
            self.locker.blank()   # Keep black window visible behind camera
        else:
            self.locker.root.withdraw()
        match = self.scanner.scan_specific_user(target_user)

        if match:
            print("✅ Face Matched!")
            balance = float(target_user.get('time_balance', 0))

            if target_user['role'] == 'root' or balance > 0:
                # --- NEW: Tell server Face ID unlock succeeded! ---
                resp = self.net.send_request("SYNC_STATE", {
                    "state_status": "In Use",
                    "active_user": target_user['username']
                })

                # --- TASK 15 FIX: Prevent Duplicate User Login ---
                if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                    print("❌ Login Blocked: User already active elsewhere.")
                    from tkinter import messagebox
                    self.locker.root.after(0, lambda: messagebox.showerror("Login Failed",
                                                                           "User is already logged in on another station.",
                                                                           parent=self.locker.root))
                    self.locker.root.deiconify()
                    self.locker.reset_to_start("Already logged in elsewhere.")
                    return

                self.current_user = target_user
                self.locker.unlock()
            else:
                print("💰 Balance is 0. Opening Rent Window...")
                renter = RentWindow(self.net, target_user['username'])

                raw_minutes = renter.show()
                try:
                    minutes_added = float(raw_minutes if raw_minutes else 0)
                except (ValueError, TypeError):
                    minutes_added = 0

                if minutes_added > 0:
                    print(f"✅ Rent successful! Adding {minutes_added} mins to session.")

                    # --- NEW: Tell server Face ID unlock succeeded after rent! ---
                    resp = self.net.send_request("SYNC_STATE", {
                        "state_status": "In Use",
                        "active_user": target_user['username']
                    })

                    # --- TASK 15 FIX: Prevent Duplicate User Login (Post-Rent) ---
                    if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                        print("❌ Login Blocked: User already active elsewhere.")
                        from tkinter import messagebox
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
                    print("❌ Payment cancelled. Returning to Lock Screen.")
                    if privacy:
                        self.locker.unblank()
                    else:
                        self.locker.root.deiconify()
                    self.locker.reset_to_start()
        else:
            print("🚫 Face match failed. Access Denied.")
            if privacy:
                self.locker.unblank()
            else:
                self.locker.root.deiconify()
            self.locker.reset_to_start("Face match failed. Access Denied.")

    def _trigger_manual_login(self):
        """Helper to unlock screen and open manual login."""
        self.locker.unlock()
        self.manual_login_sequence()

    def manual_login_sequence(self):
        """Admin fallback for password login."""
        login = LoginWindow(self.net, self.station_id)
        user_data = login.show()

        if user_data:
            role = user_data.get('role')

            if role == 'root':
                print(f"✅ Root {user_data['username']} authenticated manually.")

                # --- NEW: Tell server manual Admin login succeeded! ---
                resp = self.net.send_request("SYNC_STATE", {
                    "state_status": "In Use",
                    "active_user": user_data['username']
                })

                # --- TASK 15 FIX: Prevent Duplicate Admin Login ---
                if resp and resp.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
                    print("❌ Login Blocked: already active elsewhere.")
                    from tkinter import messagebox
                    if self.locker and self.locker.root:
                        self.locker.root.after(0, lambda: messagebox.showerror("Login Failed", "User is already logged in on another station.", parent=self.locker.root))
                        self.locker.root.deiconify()
                        self.locker.reset_to_start("Already logged in elsewhere.")
                    return

                self.current_user = user_data
            else:
                print("❌ Access Denied: Standard users cannot use manual login.")
                if self.locker and self.locker.root:
                    self.locker.root.deiconify()
                    self.locker.reset_to_start("Users must use Face ID.")


if __name__ == "__main__":
    app = MainClient()
    app.run()