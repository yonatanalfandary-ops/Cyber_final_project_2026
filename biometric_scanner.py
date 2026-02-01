import cv2
import face_recognition
import numpy as np
import time


class BiometricScanner:
    def __init__(self):
        pass

    def quick_face_scan(self, active_users):
        """
        Scans for 3 seconds to find a match among active_users.
        Returns the user dict if found, else None.
        """
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

            # 2. Check for matches
            for unknown_face in face_encs:
                for user in active_users:
                    if not user.get('face_encoding'): continue

                    # Convert list of lists to list of numpy arrays
                    known_faces = [np.array(e) for e in user['face_encoding']]

                    matches = face_recognition.compare_faces(known_faces, unknown_face, tolerance=0.6)
                    if True in matches:
                        found_user = user
                        break
                if found_user: break

            # 3. UI Feedback (Show the user they are being scanned)
            cv2.putText(frame, "Scanning...", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow('Biometric Scan', frame)

            # Required for the window to update
            if cv2.waitKey(1) & 0xFF == 27:  # Allow ESC to cancel early
                break

            if found_user:
                break

        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        return found_user