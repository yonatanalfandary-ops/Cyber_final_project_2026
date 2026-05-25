import cv2
import face_recognition
import numpy as np
import time
import tkinter as tk


class BiometricScanner:
    """
    Wrapper around OpenCV and face_recognition that provides two scanning
    modes: an open scan that matches against any active user, and a
    targeted scan that verifies a single specific user.
    """

    def __init__(self):
        pass

    def quick_face_scan(self, active_users, timeout=5):
        """
        Scans the webcam feed for any face that matches one of the supplied
        active users. Runs for up to `timeout` seconds and displays a
        borderless, always-on-top camera preview centered on the screen.

        Returns the matched user dictionary, or None if no match is found
        before the timeout expires.
        """
        if not active_users:
            return None

        # Flatten every user's stored encodings into a single list, along
        # with a parallel list mapping each encoding back to its user.
        # Doing this once up front avoids repeating the work each frame.
        known_encodings = []
        known_users = []

        for user in active_users:
            if user.get('face_encoding'):
                encodings = [np.array(e) for e in user['face_encoding']]
                known_encodings.extend(encodings)
                known_users.extend([user] * len(encodings))

        if not known_encodings:
            return None

        # Calculate the screen-centered position for the preview window.
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()

        win_w, win_h = 640, 480
        x_pos = (screen_width - win_w) // 2
        y_pos = (screen_height - win_h) // 2

        window_name = "Face Scanner"

        # Build a borderless, fullscreen-property, always-on-top window
        # sized to 640x480 and positioned at the centre of the screen.
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.resizeWindow(window_name, win_w, win_h)
        cv2.moveWindow(window_name, x_pos, y_pos)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

        # Open the webcam and begin the scan loop.
        print(f"Scanning for {len(active_users)} active users...")
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        start_time = time.time()
        found_user = None

        while (time.time() - start_time) < timeout:
            ret, frame = cap.read()
            if not ret: break

            # Downscale the frame to 25% for faster face detection, then
            # convert to RGB for the face_recognition library.
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)

                if True in matches:
                    first_match_index = matches.index(True)
                    found_user = known_users[first_match_index]

                    # Overlay a green welcome banner on the captured frame
                    # for one second to confirm the match to the user.
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

            # Allow ESC to abort the scan early.
            if cv2.waitKey(1) & 0xFF == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        return found_user

    def scan_specific_user(self, target_user, timeout=5):
        """
        Scans the webcam feed and compares each detected face only against
        the supplied target user's stored encodings.

        Returns True if a match is found within the timeout, False otherwise.
        """
        if not target_user or not target_user.get('face_encoding'):
            return False

        known_encodings = [np.array(e) for e in target_user['face_encoding']]

        # Calculate the screen-centered position for the preview window.
        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()

        win_w, win_h = 640, 480
        x_pos = (screen_width - win_w) // 2
        y_pos = (screen_height - win_h) // 2
        window_name = "Face Verification"

        # Build the same borderless always-on-top window used by quick_face_scan.
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.resizeWindow(window_name, win_w, win_h)
        cv2.moveWindow(window_name, x_pos, y_pos)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

        # Open the webcam and begin the verification loop.
        print(f"Verifying face for: {target_user['username']}...")
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
                # Compare each detected face only against the target user.
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)

                if True in matches:
                    matched = True
                    # Briefly display a green "MATCHED!" confirmation overlay.
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

            # Show who is being verified at the top of the preview frame.
            cv2.putText(frame, f"Verifying: {target_user['username']}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.imshow(window_name, frame)

            # Allow ESC to abort the scan early.
            if cv2.waitKey(1) & 0xFF == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        return matched