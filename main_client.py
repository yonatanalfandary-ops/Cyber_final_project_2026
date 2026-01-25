import cv2
import numpy as np
import time
import face_recognition
from network_client import NetworkClient
from lock_screen import LockScreen
from login_window import LoginWindow

# CONFIG
STATION_ID = "STATION_01"
SERVER_IP = "127.0.0.1"
SYNC_INTERVAL = 5  # Update DB every 5 seconds


class MainClient:
    def __init__(self):
        self.net = NetworkClient(SERVER_IP)
        self.locker = None
        self.current_user = None

        if not self.net.connect():
            print("❌ Cannot reach server. Exiting.")
            exit()

    def run(self):
        """The main lifecycle loop."""
        while True:
            # 1. Start in SLEEP MODE
            self.locker = LockScreen(on_wake_callback=self.wake_sequence)
            self.locker.lock()  # Blocks until unlocked

            # 2. Session Started
            if self.current_user:
                print(f"✅ Starting Session for: {self.current_user['username']}")
                self.monitor_session()
                # When monitor_session ends, we loop back to Lock Screen
                self.current_user = None

    def wake_sequence(self):
        """Triggered on Spacebar/Click."""
        print("⏰ Waking up... Fetching active renters...")

        # A. Fetch Active Users
        response = self.net.send_request("FETCH_ACTIVE_USERS", {})
        active_users = response.get("users", []) if response else []

        # B. Quick Face Scan
        user_found = self.quick_face_scan(active_users)

        if user_found:
            self.current_user = user_found
            print(f"🔓 FACE RECOGNIZED: {user_found['username']}")
            self.locker.unlock()
        else:
            self.locker.unlock()
            self.manual_login_sequence()

    def quick_face_scan(self, active_users):
        """Scans for 3 seconds to find a paid user."""
        if not active_users: return None

        cap = cv2.VideoCapture(0)
        start_time = time.time()
        found_user = None

        while time.time() - start_time < 3.0:
            ret, frame = cap.read()
            if not ret: break

            # Fast processing
            small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            face_encs = face_recognition.face_encodings(rgb)

            for unknown_face in face_encs:
                for user in active_users:
                    # Check first available encoding
                    known_face = [np.array(user['face_encoding'][0])]
                    match = face_recognition.compare_faces(known_face, unknown_face, tolerance=0.5)
                    if True in match:
                        found_user = user
                        break
                if found_user: break
            if found_user: break

        cap.release()
        return found_user

    def manual_login_sequence(self):
        login = LoginWindow(self.net, STATION_ID)
        user_data = login.show()

        if user_data:
            # Check Time Balance (Admins bypass)
            if user_data['role'] == 'root' or user_data['time_balance'] > 0:
                self.current_user = user_data
            else:
                print("💰 Balance is 0. Please rent time.")
                # Here you would trigger payment window
                self.run()

    def monitor_session(self):
        """
        The Active User Loop.
        Handles: Face Check, Grace Period, Time Deduction, Admin Logout.
        """
        cap = cv2.VideoCapture(0)

        # Setup specific user biometrics
        known_face = None
        if self.current_user['face_encoding']:
            known_face = [np.array(self.current_user['face_encoding'][0])]

        is_admin = self.current_user['role'] == 'root'
        balance_minutes = float(self.current_user.get('time_balance', 0))

        grace_start_time = None
        last_sync_time = time.time()

        print(f"--- SESSION STARTED ({'ADMIN' if is_admin else 'USER'}) ---")
        print("Press ESC in the Camera Window to Logout (Admin Only)")

        while True:
            ret, frame = cap.read()
            if not ret: break

            current_time = time.time()

            # --- 1. TIME MANAGEMENT ---
            if not is_admin:
                # Deduct time locally
                elapsed = current_time - last_sync_time
                if elapsed >= SYNC_INTERVAL:
                    # Update Database
                    self.net.send_request("DEDUCT_TIME", {
                        "username": self.current_user['username'],
                        "seconds": elapsed
                    })
                    # Update local balance
                    balance_minutes -= (elapsed / 60.0)
                    last_sync_time = current_time

                    if balance_minutes <= 0:
                        print("❌ TIME EXPIRED! Logging out...")
                        break

            # --- 2. FACE VERIFICATION ---
            if not is_admin:
                # Fast Check
                small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                face_locs = face_recognition.face_locations(rgb)
                face_encs = face_recognition.face_encodings(rgb, face_locs)

                match_found = False
                if known_face:
                    for enc in face_encs:
                        if True in face_recognition.compare_faces(known_face, enc, tolerance=0.5):
                            match_found = True
                            break

                # GRACE PERIOD LOGIC
                if match_found:
                    # User is present, reset timer
                    if grace_start_time is not None:
                        print("✅ User returned. Timer reset.")
                    grace_start_time = None
                    # Visual: Green Border
                    cv2.rectangle(frame, (0, 0), (640, 480), (0, 255, 0), 10)
                else:
                    # User missing!
                    if grace_start_time is None:
                        grace_start_time = time.time()

                    time_gone = time.time() - grace_start_time
                    remaining = 2.0 - time_gone

                    # Visual Alert
                    print(f"⚠ WARNING: LOGOUT IN {remaining:.1f}s")
                    cv2.putText(frame, f"LOCKING IN {remaining:.1f}s", (50, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 5)

                    if time_gone > 2.0:
                        print("❌ USER GONE TOO LONG. LOCKING.")
                        break

            # --- 3. ADMIN / MANUAL LOGOUT ---
            # Show the small security feed (required to capture key presses)
            cv2.imshow("Security Monitor", frame)

            # If Admin, they must press ESC to logout
            # If User, they can also press ESC to end session early
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC Key
                print("👋 Manual Logout Triggered.")
                break

        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        # Final sync on exit (save the last few seconds)
        if not is_admin:
            elapsed = time.time() - last_sync_time
            self.net.send_request("DEDUCT_TIME", {
                "username": self.current_user['username'],
                "seconds": elapsed
            })


if __name__ == "__main__":
    app = MainClient()
    app.run()