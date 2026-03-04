import cv2
import numpy as np
import time
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

# CONFIG
STATION_ID = "STATION_01"
SERVER_IP = "127.0.0.1"
SYNC_INTERVAL = 5


class MainClient:
    def __init__(self):
        self.net = NetworkClient(SERVER_IP)
        self.locker = None
        self.scanner = BiometricScanner()
        self.current_user = None

        if not self.net.connect(): exit()

    def run(self):
        """The main lifecycle state machine."""
        while True:
            # STATE 1: Lock Screen
            # Pass our new process_login function so the lock screen can hand us the typed username
            self.locker = LockScreen(on_submit_callback=self.process_login)
            self.locker.lock()

            # STATE 2: Authenticated
            if self.current_user:
                print(f"✅ Logged in as: {self.current_user['username']}")

                if self.current_user['role'] == 'root':
                    # Admin Mode
                    admin = AdminPanel(self.net, self.current_user['username'])
                    admin.show()
                else:
                    # User Session Mode
                    guard = SessionGuard(self.net, self.current_user)
                    self.current_user = guard.start()  # Blocks until session ends

                # Session over, clear user, loop back to Lock Screen
                self.current_user = None

    def process_login(self, username):
        """Handles the 4-step login and routing logic."""

        # --- 2. THE USERNAME CHECK ---
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

        # --- 3. THE ROUTING (Face Check) ---
        if not target_user.get('face_encoding'):
            # Check if the user is an admin/root
            if target_user.get('role') in ['root', 'admin']:
                print("🛡️ Admin without face ID. Routing instantly to manual login.")
                self.locker.reset_to_start("")  # Clear any old text just in case
                self._trigger_manual_login()    # Go straight to password window
            else:
                # Regular user without face encoding
                print("⚠️ No face ID found. Routing to manual login.")
                self.locker.reset_to_start("Face ID missing - enter as admin to create")
                self.locker.root.after(2000, self._trigger_manual_login)
            return

        # SCENARIO B: Has Face Encoding
        print("📸 Face ID found. Starting targeted scan...")
        self.locker.root.withdraw()
        match = self.scanner.scan_specific_user(target_user)

        # --- 4. THE BIOMETRIC SCAN RESULTS ---
        if match:
            print("✅ Face Matched!")
            balance = float(target_user.get('time_balance', 0))

            if target_user['role'] in ['root', 'admin'] or balance > 0:
                # MATCH + HAS TIME (or is Admin): Login instantly
                self.current_user = target_user
                self.locker.unlock()
            else:
                # MATCH + NO TIME: Route to Rent Window
                print("💰 Balance is 0. Opening Rent Window...")
                renter = RentWindow(self.net, target_user['username'])

                # Safely capture the return value and convert it to a float
                raw_minutes = renter.show()
                try:
                    minutes_added = float(raw_minutes if raw_minutes else 0)
                except (ValueError, TypeError):
                    minutes_added = 0

                if minutes_added > 0:
                    print(f"✅ Rent successful! Adding {minutes_added} mins to session.")
                    # Update local balance so SessionGuard knows how long to run
                    target_user['time_balance'] = minutes_added
                    self.current_user = target_user
                    self.locker.unlock()  # Unlocks and transitions to Session Guard!
                else:
                    print("❌ Payment cancelled. Returning to Lock Screen.")
                    self.locker.root.deiconify()
                    self.locker.reset_to_start()
        else:
            # NO MATCH
            print("🚫 Face match failed. Access Denied.")
            self.locker.root.deiconify()
            self.locker.reset_to_start("Face match failed. Access Denied.")
    def _trigger_manual_login(self):
        """Helper to unlock screen and open manual login."""
        self.locker.unlock()
        self.manual_login_sequence()

    def manual_login_sequence(self):
        """Fallback for password login."""
        login = LoginWindow(self.net, STATION_ID)
        user_data = login.show()

        if user_data:
            role = user_data.get('role')
            balance = float(user_data.get('time_balance', 0))

            if role == 'root' or balance > 0:
                self.current_user = user_data
            else:
                print("💰 Balance is 0. Opening Rent Window...")
                renter = RentWindow(self.net, user_data['username'])
                renter.show() # Ignore the return value

                # --- Verify with the server if they actually bought time ---
                print("🔄 Verifying new balance with server...")
                check_resp = self.net.send_request("FETCH_ALL_USERS", {})
                updated_balance = 0

                if check_resp and check_resp.get("users"):
                    for u in check_resp['users']:
                        if u['username'] == user_data['username']:
                            updated_balance = float(u.get('time_balance', 0))
                            user_data = u  # Update local user data
                            break

                if updated_balance > 0:
                    print(f"✅ Payment confirmed! New balance: {updated_balance}. Starting session...")
                    self.current_user = user_data
                    # If called via lock screen trigger, unlock it here:
                    if self.locker and self.locker.root:
                        try:
                            self.locker.unlock()
                        except:
                            pass
                else:
                    print("❌ No time added (Payment cancelled). Returning to Lock Screen.")
                    if self.locker and self.locker.root:
                        self.locker.root.deiconify()
                        self.locker.reset_to_start()


if __name__ == "__main__":
    app = MainClient()
    app.run()