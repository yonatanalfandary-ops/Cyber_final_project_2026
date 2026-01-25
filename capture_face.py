import cv2
import face_recognition
import json
import time
from network_client import NetworkClient

# CONFIG
SERVER_IP = "127.0.0.1"


def capture_and_update():
    print("--- 📸 FACE UPDATE TOOL ---")
    username = input("Enter Username to update: ")
    password = input("Enter Password: ")

    cap = cv2.VideoCapture(0)
    print("\nLook at the camera. Press 's' to SNAP.")

    face_data = None

    while True:
        ret, frame = cap.read()
        if not ret: break

        cv2.imshow("Capture - Press 's'", frame)

        if cv2.waitKey(1) & 0xFF == ord('s'):
            print("Processing...")
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(rgb_frame)

            if len(encodings) > 0:
                # We found a face!
                print("✅ Face Captured!")
                # Convert to list for JSON sending
                face_data = [encodings[0].tolist()]
                break
            else:
                print("❌ No face detected. Try again.")

    cap.release()
    cv2.destroyAllWindows()

    if face_data:
        print(f"📡 Sending data to Server for user '{username}'...")
        net = NetworkClient(SERVER_IP)
        if net.connect():
            resp = net.send_request("UPDATE_FACE", {
                "username": username,
                "password": password,
                "face_data": face_data
            })
            print(f"Server Response: {resp}")
        else:
            print("❌ Could not connect to server.")


if __name__ == "__main__":
    capture_and_update()