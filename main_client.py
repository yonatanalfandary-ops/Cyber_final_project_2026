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
        # Note: Assuming your server has a FETCH_ALL_USERS or similar route to get user data.
        response = self.net.send_request("FETCH_ACTIVE_USERS", {})
        target_user = None

        if response and response.get("users"):
            for u in response['users']:
                if u['username'].lower() == username.lower():
                    target_user = u
                    break

        if not target_user:
            # NO: Show inline error and wait for them to try again
            print("❌ Username not found.")
            self.locker.reset_to_start("Username not found")
            return

        # 👇 ADD THESE TWO LINES 👇
        print(f"DEBUG: Found {target_user['username']}. Keys received from server:")
        print(target_user.keys())

        # --- 3. THE ROUTING (Face Check) ---
        if not target_user.get('face_encoding'):
            # SCENARIO A: No Face Encoding (e.g., Master Admin)
            print("⚠️ No face ID found. Routing to manual login.")
            self.locker.reset_to_start("Face ID missing - enter as admin to create")

            # Briefly show the message, then destroy the lock screen and show password window
            self.locker.root.after(2000, self._trigger_manual_login)
            return

        # SCENARIO B: Has Face Encoding
        print("📸 Face ID found. Starting targeted scan...")
        # Hide the lock screen temporarily so we can see the camera
        self.locker.root.withdraw()
        match = self.scanner.scan_specific_user(target_user)

        # --- 4. THE BIOMETRIC SCAN RESULTS ---
        if match:
            print("✅ Face Matched!")
            balance = float(target_user.get('time_balance', 0))

            if target_user['role'] == 'root' or balance > 0:
                # MATCH + HAS TIME: Login instantly
                self.current_user = target_user
                self.locker.unlock()
            else:
                # MATCH + NO TIME: Route to Rent Window
                print("💰 Balance is 0. Opening Rent Window...")
                renter = RentWindow(self.net, target_user['username'])
                minutes_added = renter.show()

                if minutes_added > 0:
                    target_user['time_balance'] = minutes_added
                    self.current_user = target_user
                    self.locker.unlock()
                else:
                    print("❌ Payment cancelled. Returning to Lock Screen.")
                    self.locker.root.deiconify()
                    self.locker.reset_to_start()
        else:
            # NO MATCH: Face is wrong. Deny and reset instantly (No password fallback)
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
                minutes_added = renter.show()

                if minutes_added > 0:
                    user_data['time_balance'] = minutes_added
                    self.current_user = user_data
                else:
                    print("❌ Payment cancelled. Returning to Lock Screen.")


if __name__ == "__main__":
    app = MainClient()
    app.run()