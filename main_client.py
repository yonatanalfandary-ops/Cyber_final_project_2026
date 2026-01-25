import cv2
import numpy as np
import time
from network_client import NetworkClient
from lock_screen import LockScreen
from login_window import LoginWindow
import face_recognition

# --- CONFIGURATION ---
STATION_ID = "STATION_01"
SERVER_IP = "127.0.0.1"  # Change to Server IP if different PC


class FaceAuthenticator:
    """Manages the ONE face we are looking for."""

    def __init__(self):
        self.target_encoding = None
        self.target_name = None

    def load_user(self, user_data):
        self.target_name = user_data['username']
        # The server sends a list of lists (multi-angle), we take the first one for now
        # or we could compare against all of them for better accuracy.
        if user_data.get('face_encoding'):
            # Convert list back to numpy array
            encodings = user_data['face_encoding']
            # Flatten to a list of numpy arrays
            self.target_encoding = [np.array(e) for e in encodings]
            print(f"🔒 Loaded biometrics for: {self.target_name}")
        else:
            print("⚠ User has no face data! (Admin/Root?)")
            self.target_encoding = []

    def verify_user(self, frame):
        """
        Returns True if the target user is found in the frame.
        """
        if not self.target_encoding:
            return True  # If no face data (e.g. root/admin), skip check

        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # Find faces in current frame
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for encoding in face_encodings:
            # Check against ALL known angles of the user
            matches = face_recognition.compare_faces(self.target_encoding, encoding, tolerance=0.5)
            if True in matches:
                return True

        return False


class SecuritySystem:
    def __init__(self, authenticator, locker):
        self.auth = authenticator
        self.locker = locker
        self.camera = None
        self.is_running = True
        self.missing_frames = 0
        self.MAX_MISSING = 50  # How many frames you can be gone (approx 2-3 sec)

    def start_session(self):
        print("📸 Starting Camera Security...")
        self.camera = cv2.VideoCapture(0)
        self.locker.unlock()  # Lower the shield

        while self.is_running:
            ret, frame = self.camera.read()
            if not ret: break

            # 1. Verify User
            is_present = self.auth.verify_user(frame)

            if is_present:
                self.missing_frames = 0
                # Optional: Draw Green Box
                cv2.rectangle(frame, (10, 10), (50, 50), (0, 255, 0), -1)
            else:
                self.missing_frames += 1
                print(f"⚠ Warning: Face missing ({self.missing_frames}/{self.MAX_MISSING})")

            # 2. Logic: Lock if gone too long
            if self.missing_frames > self.MAX_MISSING:
                print("❌ USER GONE - LOCKING SESSION")
                self.locker.lock()
                # Here we could break the loop to force a re-login
                # or just keep it locked until they look back.
                # For this new system, let's END the session to force password again.
                break

                # Display (Optional - hide in real production)
            cv2.imshow("Security Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.camera.release()
        cv2.destroyAllWindows()
        self.locker.lock()  # Ensure locked on exit


# --- MAIN APPLICATION LOOP ---
if __name__ == "__main__":
    net = NetworkClient(SERVER_IP)
    if not net.connect():
        print("❌ Cannot reach server. Exiting.")
        exit()

    locker = LockScreen()
    # locker.lock()  <-- DELETE OR COMMENT THIS OUT!
    # (Do not lock immediately, or it hides the login window)

    while True:
        # 2. Show Login Screen
        print("\n🔐 WAITING FOR LOGIN...")
        login = LoginWindow(net, STATION_ID)
        user_data = login.show()  # This blocks until login

        if user_data:
            # 3. Login Success
            auth = FaceAuthenticator()
            auth.load_user(user_data)

            # 4. Start Monitoring (Desktop Unlocked)
            system = SecuritySystem(auth, locker)
            system.start_session()

            print("👋 Session Ended. Returning to Login.")

            # Ensure the shield is reset for the next person
            locker.unlock()
        else:
            # If they closed the login window, exit the loop
            break