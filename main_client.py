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
from biometric_scanner import BiometricScanner  # <--- Ensure this import exists!
from session_guard import SessionGuard  # <--- NEW IMPORT

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
            self.locker = LockScreen(on_wake_callback=self.wake_sequence)
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
                    # Hand off control to the Guard
                    guard = SessionGuard(self.net, self.current_user)
                    self.current_user = guard.start() # Blocks until session ends

                # Session over, clear user, loop back to Lock Screen
                self.current_user = None

    def wake_sequence(self):
        print("⏰ Waking up... Fetching active renters...")
        response = self.net.send_request("FETCH_ACTIVE_USERS", {})
        active_users = response.get("users", []) if response else []

        # --- FIX 2: Call the method on the scanner object ---
        user_found = self.scanner.quick_face_scan(active_users)

        if user_found:
            self.current_user = user_found
            print(f"🔓 FACE RECOGNIZED: {user_found['username']}")
            self.locker.unlock()
        else:
            self.locker.unlock()
            self.manual_login_sequence()

    def manual_login_sequence(self):
        # ... (Your existing code here is fine) ...
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

