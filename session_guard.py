import cv2
import time
import numpy as np
import face_recognition
import tkinter as tk
from settings_window import SettingsWindow


class SessionGuard:
    def __init__(self, network_client, user_data):
        self.net = network_client
        self.user = user_data
        self.is_running = True

        # Session State
        self.is_admin = (self.user.get('role') == 'root')
        self.balance_mins = float(self.user.get('time_balance', 0))
        self.grace_start = None
        self.last_sync = time.time()
        self.last_loop = time.time()

        # Face Data (Pre-load for performance)
        self.known_faces = []
        if self.user.get('face_encoding'):
            self.known_faces = [np.array(e) for e in self.user['face_encoding']]

    def start(self):
        """Starts the session loop. Returns updated user data on exit."""
        cap = cv2.VideoCapture(0)
        print(f"--- SESSION STARTED: {self.user['username']} ---")

        while self.is_running:
            ret, frame = cap.read()
            if not ret: break

            # 1. Update State (Timer & Sync)
            if not self._update_time_logic():
                break  # Time expired

            # 2. Check Security (Face Scan)
            if not self.is_admin:
                self._check_biometrics(frame)

            # 3. Draw UI
            self._draw_hud(frame)
            cv2.imshow("Security Monitor", frame)

            # 4. Handle Inputs
            self._handle_input(cap)

        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        self._final_sync()
        return self.user

    def _update_time_logic(self):
        """Calculates time deduction and server sync."""
        if self.is_admin: return True

        current_time = time.time()
        dt = current_time - self.last_loop
        self.last_loop = current_time

        # Local countdown
        self.balance_mins -= (dt / 60.0)

        # Server Sync (Every 5s)
        if current_time - self.last_sync >= 5:
            deduct = current_time - self.last_sync
            self.net.send_request("DEDUCT_TIME", {
                "username": self.user['username'], "seconds": deduct
            })
            self.last_sync = current_time

        if self.balance_mins <= 0:
            print("❌ TIME EXPIRED!")
            return False
        return True

    def _check_biometrics(self, frame):
        """Verifies if the user is present."""
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        # Check faces
        match_found = False
        if self.known_faces:
            face_encs = face_recognition.face_encodings(rgb)
            for enc in face_encs:
                matches = face_recognition.compare_faces(self.known_faces, enc, tolerance=0.6)
                if True in matches:
                    match_found = True
                    break

        # Grace Period Logic
        if match_found:
            self.grace_start = None
        else:
            if self.grace_start is None: self.grace_start = time.time()

            elapsed = time.time() - self.grace_start
            if elapsed > 2.0:
                print("❌ USER GONE TOO LONG.")
                self.is_running = False  # Trigger logout
            else:
                # Warning Text
                cv2.putText(frame, f"LOCKING IN {2.0 - elapsed:.1f}s", (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 5)

    def _draw_hud(self, frame):
        """Draws the interface overlay."""
        mins = int(max(0, self.balance_mins))
        secs = int((max(0, self.balance_mins) - mins) * 60)

        # Black Box
        cv2.rectangle(frame, (10, 10), (400, 110), (0, 0, 0), -1)

        # Text
        cv2.putText(frame, f"TIME: {mins}:{secs:02d}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, "[S] Settings  [Q] Logout", (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def _handle_input(self, cap):
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            self.is_running = False
        elif key == ord('s'):
            self._open_settings(cap)

    def _open_settings(self, cap):
        """Pauses OpenCV to open Tkinter settings."""
        cap.release()
        cv2.destroyAllWindows()

        temp = tk.Tk()
        temp.withdraw()

        settings = SettingsWindow(self.net, self.user['username'], temp)
        new_name = settings.show()

        temp.destroy()

        if new_name:
            self.user['username'] = new_name

        # Restart loop timing to avoid massive deduction
        cap.open(0)
        self.last_loop = time.time()

    def _final_sync(self):
        if not self.is_admin:
            elapsed = time.time() - self.last_sync
            self.net.send_request("DEDUCT_TIME", {
                "username": self.user['username'], "seconds": elapsed
            })