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
SYNC_INTERVAL = 5  # Server sync every 5 seconds


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
            self.locker = LockScreen(on_wake_callback=self.wake_sequence)
            self.locker.lock()

            if self.current_user:
                print(f"✅ Starting Session for: {self.current_user['username']}")
                self.monitor_session()
                self.current_user = None

    def wake_sequence(self):
        print("⏰ Waking up... Fetching active renters...")
        response = self.net.send_request("FETCH_ACTIVE_USERS", {})
        active_users = response.get("users", []) if response else []

        user_found = self.quick_face_scan(active_users)

        if user_found:
            self.current_user = user_found
            print(f"🔓 FACE RECOGNIZED: {user_found['username']}")
            self.locker.unlock()
        else:
            self.locker.unlock()
            self.manual_login_sequence()

    def quick_face_scan(self, active_users):
        if not active_users: return None

        print(f"👀 Scanning for {len(active_users)} active users...")
        cap = cv2.VideoCapture(0)
        start_time = time.time()
        found_user = None

        while time.time() - start_time < 3.0:
            ret, frame = cap.read()
            if not ret: break

            # 1. Resize for performance
            small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            face_encs = face_recognition.face_encodings(rgb)

            for unknown_face in face_encs:
                for user in active_users:
                    # --- UPDATED: Load ALL angles ---
                    # user['face_encoding'] is a list of lists. Convert all to numpy arrays.
                    known_faces = [np.array(e) for e in user['face_encoding']]

                    # Check if ANY of the stored angles match the camera face
                    matches = face_recognition.compare_faces(known_faces, unknown_face, tolerance=0.6)

                    if True in matches:
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
            if user_data.get('role') == 'root' or user_data.get('time_balance', 0) > 0:
                self.current_user = user_data
            else:
                print("💰 Balance is 0. Please rent time.")
                self.run()

    def monitor_session(self):
        cap = cv2.VideoCapture(0)

        # --- UPDATED: Load ALL angles for the current user ---
        known_faces = []
        if self.current_user.get('face_encoding'):
            known_faces = [np.array(e) for e in self.current_user['face_encoding']]

        is_admin = self.current_user.get('role') == 'root'

        # Local balance allows for smooth countdown
        local_balance_minutes = float(self.current_user.get('time_balance', 0))

        grace_start_time = None
        last_sync_time = time.time()
        last_loop_time = time.time()  # Used to calculate exact delta for display

        print(f"--- SESSION STARTED ({'ADMIN' if is_admin else 'USER'}) ---")
        print("Press ESC in the Camera Window to Logout")

        while True:
            ret, frame = cap.read()
            if not ret: break

            current_time = time.time()
            dt = current_time - last_loop_time  # Time passed since last frame
            last_loop_time = current_time

            # --- 1. TIME MANAGEMENT ---
            if not is_admin:
                # Decrease local display timer instantly (Smooth countdown)
                local_balance_minutes -= (dt / 60.0)

                # Sync with Server every 5 seconds
                if current_time - last_sync_time >= SYNC_INTERVAL:
                    seconds_to_deduct = current_time - last_sync_time
                    self.net.send_request("DEDUCT_TIME", {
                        "username": self.current_user['username'],
                        "seconds": seconds_to_deduct
                    })
                    last_sync_time = current_time

                if local_balance_minutes <= 0:
                    print("❌ TIME EXPIRED! Logging out...")
                    break

            # --- 2. FACE VERIFICATION ---
            if not is_admin:
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

                face_locs = face_recognition.face_locations(rgb)
                face_encs = face_recognition.face_encodings(rgb, face_locs)

                match_found = False
                if known_faces:
                    for enc in face_encs:
                        # Compare against ALL angles
                        matches = face_recognition.compare_faces(known_faces, enc, tolerance=0.6)
                        if True in matches:
                            match_found = True
                            break

                # Grace Period Logic
                if match_found:
                    if grace_start_time is not None:
                        print("✅ User returned. Timer reset.")
                    grace_start_time = None
                    cv2.rectangle(frame, (0, 0), (640, 480), (0, 255, 0), 10)
                else:
                    if grace_start_time is None:
                        grace_start_time = time.time()

                    time_gone = time.time() - grace_start_time
                    remaining = 2.0 - time_gone

                    print(f"⚠ WARNING: LOGOUT IN {remaining:.1f}s")
                    cv2.putText(frame, f"LOCKING IN {remaining:.1f}s", (50, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 5)

                    if time_gone > 2.0:
                        print("❌ USER GONE TOO LONG. LOCKING.")
                        break

            # --- 3. DISPLAY & CONTROLS ---
            # Format nicely
            if local_balance_minutes < 0: local_balance_minutes = 0
            mins = int(local_balance_minutes)
            secs = int((local_balance_minutes - mins) * 60)
            time_str = f"TIME LEFT: {mins}:{secs:02d}"

            cv2.rectangle(frame, (10, 10), (350, 60), (0, 0, 0), -1)
            cv2.putText(frame, time_str, (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.imshow("Security Monitor", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC Key
                print("👋 Manual Logout Triggered.")
                break

        cap.release()
        cv2.destroyAllWindows()

        # Final sync
        if not is_admin:
            elapsed = time.time() - last_sync_time
            self.net.send_request("DEDUCT_TIME", {
                "username": self.current_user['username'],
                "seconds": elapsed
            })


if __name__ == "__main__":
    app = MainClient()
    app.run()