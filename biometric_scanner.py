import cv2
import face_recognition
import numpy as np
import time
import tkinter as tk


class BiometricScanner:
    def __init__(self):
        pass

    def quick_face_scan(self, active_users, timeout=5):
        """
        Scans for a face from the list of 'active_users' for 'timeout' seconds.
        Displays a borderless camera feed centered on screen (cannot be closed/minimized).
        """
        if not active_users:
            return None

        # --- OPTIMIZATION: Pre-load face data ---
        known_encodings = []
        known_users = []

        for user in active_users:
            if user.get('face_encoding'):
                encodings = [np.array(e) for e in user['face_encoding']]
                known_encodings.extend(encodings)
                known_users.extend([user] * len(encodings))

        if not known_encodings:
            return None

        # --- SETUP WINDOW ---
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()

        win_w, win_h = 640, 480
        x_pos = (screen_width - win_w) // 2
        y_pos = (screen_height - win_h) // 2

        window_name = "Face Scanner"

        # 1. Create Window
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # 2. Remove Title Bar & Borders
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        # 3. Force it back to our desired size (640x480) and position
        cv2.resizeWindow(window_name, win_w, win_h)
        cv2.moveWindow(window_name, x_pos, y_pos)

        # 4. Force Topmost
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

        # --- START CAMERA ---
        print(f"👀 Scanning for {len(active_users)} active users...")
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        start_time = time.time()
        found_user = None

        while (time.time() - start_time) < timeout:
            ret, frame = cap.read()
            if not ret: break

            # --- FACE RECOGNITION ---
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)

                if True in matches:
                    first_match_index = matches.index(True)
                    found_user = known_users[first_match_index]

                    # --- SUCCESS FEEDBACK ---
                    height, width, _ = frame.shape
                    text = f"WELCOME {found_user['username']}!"
                    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
                    text_x = (width - text_size[0]) // 2
                    text_y = (height + text_size[1]) // 2

                    cv2.putText(frame, text, (text_x, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)

                    cv2.imshow(window_name, frame)
                    cv2.waitKey(1000)
                    break

            if found_user:
                break

            cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        return found_user

    def scan_specific_user(self, target_user, timeout=5):
        """
        Scans and compares the face ONLY against the provided target_user's encoding.
        Returns True if matched, False otherwise.
        """
        if not target_user or not target_user.get('face_encoding'):
            return False

        known_encodings = [np.array(e) for e in target_user['face_encoding']]

        # --- SETUP WINDOW ---
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()

        win_w, win_h = 640, 480
        x_pos = (screen_width - win_w) // 2
        y_pos = (screen_height - win_h) // 2
        window_name = "Face Verification"

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.resizeWindow(window_name, win_w, win_h)
        cv2.moveWindow(window_name, x_pos, y_pos)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

        # --- START CAMERA ---
        print(f"🎯 Verifying face for: {target_user['username']}...")
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        start_time = time.time()
        matched = False

        while (time.time() - start_time) < timeout:
            ret, frame = cap.read()
            if not ret: break

            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for face_encoding in face_encodings:
                # ONLY compare against the specific user's encodings
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)

                if True in matches:
                    matched = True
                    # Success UI
                    height, width, _ = frame.shape
                    text = "MATCHED!"
                    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
                    cv2.putText(frame, text, ((width - text_size[0]) // 2, (height + text_size[1]) // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                    cv2.imshow(window_name, frame)
                    cv2.waitKey(1000)
                    break

            if matched:
                break

            # Show target username on screen
            cv2.putText(frame, f"Verifying: {target_user['username']}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == 27:  # ESC
                break

        cap.release()
        cv2.destroyAllWindows()
        return matched