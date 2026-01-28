import cv2
import face_recognition
import json
import tkinter as tk
from tkinter import messagebox
from network_client import NetworkClient

# CONFIG
SERVER_IP = "127.0.0.1"


class FaceCaptureApp:
    def __init__(self):
        self.net = NetworkClient(SERVER_IP)
        if not self.net.connect():
            print("❌ Cannot connect to server.")
            exit()

    def capture_process(self):
        username = input("Enter Username to update: ")
        password = input("Enter Password: ")

        print(f"\n📸 Starting Multi-Angle Capture for {username}")
        print("We need 5 angles: Center, Left, Right, Up, Down")

        cap = cv2.VideoCapture(0)
        face_data = []
        instructions = ["Look CENTER", "Look slightly LEFT", "Look slightly RIGHT", "Look slightly UP",
                        "Look slightly DOWN"]

        for instruction in instructions:
            while True:
                ret, frame = cap.read()
                if not ret: break

                # Show instruction on screen
                cv2.putText(frame, f"{instruction} and press 's'", (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.imshow("Capture", frame)

                key = cv2.waitKey(1)
                if key & 0xFF == ord('s'):
                    # Capture and Process
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    boxes = face_recognition.face_locations(rgb)
                    encodings = face_recognition.face_encodings(rgb, boxes)

                    if len(encodings) > 0:
                        print(f"✅ Captured: {instruction}")
                        # Convert numpy array to list for JSON serialization
                        face_data.append(encodings[0].tolist())
                        break
                    else:
                        print("❌ No face found. Try again.")

                if key & 0xFF == 27:  # ESC
                    cap.release()
                    cv2.destroyAllWindows()
                    return

        cap.release()
        cv2.destroyAllWindows()

        # Send to Server
        print("📤 Sending data to server...")
        response = self.net.send_request("UPDATE_FACE", {
            "username": username,
            "password": password,
            "face_data": face_data  # Now a list of 5 lists
        })

        if response.get("status") == "SUCCESS":
            print("✅ Face Data Updated Successfully!")
        else:
            print(f"❌ Error: {response.get('message')}")


if __name__ == "__main__":
    app = FaceCaptureApp()
    app.capture_process()