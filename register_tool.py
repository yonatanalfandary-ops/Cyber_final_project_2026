import cv2
import face_recognition
import time
from database_manager import DatabaseManager


def register_multi_angle_user():
    print("========================================")
    print("   MULTI-ANGLE REGISTRATION TOOL        ")
    print("========================================")

    db = DatabaseManager()

    username = input("\nEnter new Username: ").strip()
    if not username: return
    password = input("Enter backup Password: ").strip()

    cap = cv2.VideoCapture(0)

    face_gallery = []  # We will store multiple angles here
    required_angles = ["Look CENTER", "Look slightly LEFT", "Look slightly RIGHT"]

    print("\nStarting Capture Process...")
    print("Please follow the instructions on the screen.")

    for angle_instruction in required_angles:
        while True:
            ret, frame = cap.read()
            if not ret: break

            # Draw Instructions
            cv2.putText(frame, f"STEP: {angle_instruction}", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(frame, "Press 's' to SNAP, 'q' to QUIT", (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow("Registration", frame)

            key = cv2.waitKey(1)
            if key & 0xFF == ord('s'):
                # SNAP
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                encodings = face_recognition.face_encodings(rgb_frame)

                if len(encodings) > 0:
                    face_gallery.append(encodings[0].tolist())
                    print(f"✅ Captured: {angle_instruction}")
                    time.sleep(0.5)  # Brief pause
                    break  # Move to next angle
                else:
                    print("⚠ No face seen. Try again.")

            elif key & 0xFF == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                return

    cap.release()
    cv2.destroyAllWindows()

    # Save the LIST of faces to the database
    if len(face_gallery) > 0:
        print(f"\nSaving {len(face_gallery)} face angles for {username}...")
        # Note: We are passing a List of Lists, which our DB Manager handles via JSON
        db.register_user(username, password, face_gallery)
    else:
        print("❌ No faces captured.")


if __name__ == "__main__":
    register_multi_angle_user()