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
from smart_lockscreen import SmartLockScreen

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
            self.locker = LockScreen(on_submit_callback=self.process_login)
            self.locker.lock()

            # STATE 2: Authenticated
            if self.current_user:
                print(f"✅ Logged in as: {self.current_user['username']}")

                if self.current_user['role'] == 'root':
                    # Admin Mode
                    admin = AdminPanel(self.net, self.current_user['username'])
                    admin.show()
                    self.current_user = None
                else:
                    # User Session Mode loop (Allows pausing/resuming)
                    while self.current_user:
                        guard = SessionGuard(self.net, self.current_user)
                        status = guard.start()  # Blocks until session ends or pauses

                        if status == "PAUSED":
                            print("🔒 Session Paused. Entering Smart Lock.")
                            smart_lock = SmartLockScreen(self.current_user, self.scanner)
                            lock_result = smart_lock.show()

                            if lock_result == "RESUME":
                                # Loops back up and starts a fresh SessionGuard with saved time
                                continue
                            else:
                                # They timed out or hit Escape, so clear user and go to main Login
                                self.current_user = None
                                break
                        else:
                            # They properly logged out via the Q button or time ran out
                            self.current_user = None
                            break

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
            if target_user.get('role') in ['root', 'admin']:
                print("🛡️ Admin without face ID. Routing instantly to manual login.")
                self.locker.reset_to_start("")
                self._trigger_manual_login()
            else:
                print("⚠️ No face ID found. Routing to manual login.")
                self.locker.reset_to_start("Face ID missing - enter as admin to create")
                self.locker.root.after(2000, self._trigger_manual_login)
            return

        print("📸 Face ID found. Starting targeted scan...")
        self.locker.root.withdraw()
        match = self.scanner.scan_specific_user(target_user)

        if match:
            print("✅ Face Matched!")
            balance = float(target_user.get('time_balance', 0))

            if target_user['role'] in ['root', 'admin'] or balance > 0:
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
                    target_user['time_balance'] = minutes_added
                    self.current_user = target_user
                    self.locker.unlock()
                else:
                    print("❌ Payment cancelled. Returning to Lock Screen.")
                    self.locker.root.deiconify()
                    self.locker.reset_to_start()
        else:
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
                renter.show()

                print("🔄 Verifying new balance with server...")
                check_resp = self.net.send_request("FETCH_ALL_USERS", {})
                updated_balance = 0

                if check_resp and check_resp.get("users"):
                    for u in check_resp['users']:
                        if u['username'] == user_data['username']:
                            updated_balance = float(u.get('time_balance', 0))
                            user_data = u
                            break

                if updated_balance > 0:
                    print(f"✅ Payment confirmed! New balance: {updated_balance}. Starting session...")
                    self.current_user = user_data
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