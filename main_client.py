import face_recognition
import cv2
import os
import numpy as np
import ctypes
import json
from network_client import NetworkClient

class FaceAuthenticator:
    """
    Handles facial recognition logic with support for multiple users from DB.
    """

    def __init__(self):
        self.known_face_encodings = []
        self.known_face_names = []

    def load_users_from_db(self, user_list):
        """
        Receives a list of users from DatabaseManager and loads them.
        Format: [{'name': 'Yonatan', 'encoding': [0.1, 0.2...]}, ...]
        """
        print(f"Loading {len(user_list)} users from Database...")

        for user in user_list:
            name = user['name']
            encoding = np.array(user['encoding'])  # Convert list back to numpy

            self.known_face_encodings.append(encoding)
            self.known_face_names.append(name)
            print(f" - Loaded: {name}")

    def identify(self, frame, resize_factor=0.25):
        """
        Returns a list of (name, location) tuples.
        """
        small_frame = cv2.resize(frame, (0, 0), fx=resize_factor, fy=resize_factor)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        results = []

        for face_encoding, location in zip(face_encodings, face_locations):
            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding)
            name = "Unknown"

            if True in matches:
                first_match_index = matches.index(True)
                name = self.known_face_names[first_match_index]

            # Scale location back up
            top, right, bottom, left = location
            scale = int(1 / resize_factor)
            scaled_location = (top * scale, right * scale, bottom * scale, left * scale)
            results.append((name, scaled_location))

        return results


class WebcamStream:
    """Handles the video capture device."""

    def __init__(self, source=0):
        self.video_capture = cv2.VideoCapture(source)
        if not self.video_capture.isOpened():
            raise ValueError("Unable to open camera.")

    def get_frame(self):
        ret, frame = self.video_capture.read()
        return ret, frame

    def release(self):
        self.video_capture.release()


class SecuritySystem:
    """
    Main controller. Now handles Dynamic User Login.
    """

    def __init__(self, face_auth_system, camera_system):
        self.auth = face_auth_system
        self.cam = camera_system
        self.is_running = False

        # --- NEW: Dynamic User State ---
        self.current_user = None  # Who is currently using the PC?
        self.is_locked = True  # Does the system think it's locked?

        # Security Config
        self.missing_frames_count = 0
        self.lock_threshold = 30  # Lock after ~1-2 seconds of absence

    def lock_computer(self):
        """Locks Windows and resets the current user."""
        print("⚠ TIMEOUT: Locking Workstation...")
        try:
            ctypes.windll.user32.LockWorkStation()
            self.current_user = None
            self.is_locked = True
            self.missing_frames_count = 0
        except Exception as e:
            print(f"Error locking computer: {e}")

    def unlock_computer(self, username):
        """Log a user in."""
        print(f"✅ ACCESS GRANTED: Welcome, {username}")
        self.current_user = username
        self.is_locked = False
        self.missing_frames_count = 0
        # In a real app, you might minimize the window here

    def draw_results(self, frame, results):
        for name, (top, right, bottom, left) in results:
            # Green if it's the current user, Blue if authorized but not logged in, Red if unknown
            if name == self.current_user:
                color = (0, 255, 0)  # Green
            elif name != "Unknown":
                color = (255, 255, 0)  # Cyan (Known user seeing lock screen)
            else:
                color = (0, 0, 255)  # Red

            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)
        return frame

    def run(self):
        print("System Active. Waiting for user...")
        self.is_running = True

        while self.is_running:
            ret, frame = self.cam.get_frame()
            if not ret: break

            results = self.auth.identify(frame)
            names_found = [r[0] for r in results]

            # --- LOGIC FLOW ---

            # Scenario A: Computer is Locked (No current user)
            if self.current_user is None:
                # Check if ANY known user is looking
                for name in names_found:
                    if name != "Unknown":
                        self.unlock_computer(name)
                        break

            # Scenario B: Computer is Unlocked (User is working)
            else:
                if self.current_user in names_found:
                    # User is present, reset timer
                    self.missing_frames_count = 0
                else:
                    # User missing, start countdown
                    self.missing_frames_count += 1

                    if self.missing_frames_count % 10 == 0:
                        print(f"User {self.current_user} missing... {self.missing_frames_count}/{self.lock_threshold}")

                # Check if we need to lock
                if self.missing_frames_count > self.lock_threshold:
                    self.lock_computer()

            # --- DISPLAY ---
            frame_with_ui = self.draw_results(frame, results)

            # Overlay status text
            status_text = f"USER: {self.current_user}" if self.current_user else "LOCKED"
            cv2.putText(frame_with_ui, status_text, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)

            # Warning text
            if self.current_user and self.missing_frames_count > 5:
                cv2.putText(frame_with_ui, f"LOCKING IN {self.lock_threshold - self.missing_frames_count}",
                            (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

            cv2.imshow('Face ID Client', frame_with_ui)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.is_running = False

        self.cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    # --- STEP 1: Connect to Server ---
    # NOTE: Change "127.0.0.1" to your server's real IP when you use 2 computers!
    net = NetworkClient(server_ip="127.0.0.1", server_port=5000)

    if not net.connect():
        print("CRITICAL: Could not reach the server. Exiting.")
        exit()

    # Ask the server for the user list
    response = net.send_request("FETCH_USERS")

    if response and response.get("status") == "SUCCESS":
        users = response["users"]
        print(f"✅ Received {len(users)} users from Server.")
    else:
        print("❌ Failed to download user list.")
        users = []

    if not users:
        print("⚠ WARNING: Server returned no users. Is the database empty?")

    # --- STEP 2: Initialize Auth ---
    auth_system = FaceAuthenticator()
    auth_system.load_users_from_db(users)

    # --- STEP 3: Start Security System ---
    camera = WebcamStream()
    system = SecuritySystem(auth_system, camera)
    system.run()

    # Close connection when app quits
    net.close()