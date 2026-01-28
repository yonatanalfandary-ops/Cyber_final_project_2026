import tkinter as tk
from tkinter import simpledialog, messagebox
import cv2
import face_recognition


class SettingsWindow:
    # 1. Add 'from_payment' parameter (Default False)
    def __init__(self, network_client, username, parent_root, from_payment=False):
        self.net = network_client
        self.username = username
        self.parent_root = parent_root
        self.from_payment = from_payment  # Store the flag
        self.root = None
        self.new_username = None

    def show(self):
        self.root = tk.Toplevel(self.parent_root)

        # --- KIOSK MODE ---
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg="#34495e")

        # Center Frame
        frame = tk.Frame(self.root, bg="#34495e")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="Account Settings", font=("Arial", 28, "bold"),
                 bg="#34495e", fg="white").pack(pady=30)

        # Buttons
        btn_style = {"font": ("Arial", 16), "width": 25, "bg": "#2980b9", "fg": "white"}

        tk.Button(frame, text="Change Full Name", command=self.change_name, **btn_style).pack(pady=10)
        tk.Button(frame, text="Change Password", command=self.change_password, **btn_style).pack(pady=10)
        tk.Button(frame, text="Change Username", command=self.change_username, **btn_style).pack(pady=10)

        tk.Label(frame, text="--- Biometrics ---", font=("Arial", 12),
                 bg="#34495e", fg="#bdc3c7").pack(pady=10)

        tk.Button(frame, text="Recapture Face ID", command=self.recapture_face,
                  font=("Arial", 16, "bold"), width=25, bg="#e67e22", fg="white").pack(pady=10)

        # --- DYNAMIC EXIT BUTTON ---
        # If coming from payment, show "Back to Payment"
        # If coming from session, just show "Close Settings"
        exit_text = "Back to Payment" if self.from_payment else "Close Settings"
        exit_color = "#c0392b"  # Red

        tk.Button(frame, text=exit_text, command=self.close,
                  font=("Arial", 14), width=15, bg=exit_color, fg="white").pack(pady=30)

        self.root.wait_window()
        return self.new_username if self.new_username else self.username

    def send_update(self, field, value):
        print(f"📝 Updating {field}...")
        response = self.net.send_request("UPDATE_PROFILE", {
            "username": self.username,
            "field": field,
            "value": value
        })
        return response.get("status") == "SUCCESS"

    # ... [Keep change_name, change_password, change_username, recapture_face exactly as they were] ...
    # (I omitted them here to save space, but ensure you keep the existing logic!)

    def change_name(self):
        new_name = simpledialog.askstring("Update Name", "Enter new Full Name:", parent=self.root)
        if new_name:
            if self.send_update("full_name", new_name):
                messagebox.showinfo("Success", "Full Name updated.", parent=self.root)
            else:
                messagebox.showerror("Error", "Failed to update.", parent=self.root)

    def change_password(self):
        new_pass = simpledialog.askstring("Update Password", "Enter new Password:", parent=self.root, show="*")
        if new_pass:
            # CHANGED: "password_hash" -> "password"
            if self.send_update("password", new_pass):
                messagebox.showinfo("Success", "Password updated.", parent=self.root)
            else:
                messagebox.showerror("Error", "Failed to update.", parent=self.root)

    def change_username(self):
        new_user = simpledialog.askstring("Update Username", "Enter new Username:", parent=self.root)
        if new_user:
            confirm = messagebox.askyesno("Confirm", "Are you sure?",
                                          parent=self.root)
            if not confirm: return

            if self.send_update("username", new_user):
                self.username = new_user
                self.new_username = new_user
                messagebox.showinfo("Success", f"Username changed to '{new_user}'", parent=self.root)
            else:
                messagebox.showerror("Error", "Username taken or invalid.", parent=self.root)

    def recapture_face(self):
        confirm = messagebox.askyesno("Recapture Face",
                                      "This will open the camera.\nLook: Center, Left, Right, Up, Down.\nReady?",
                                      parent=self.root)
        if not confirm: return

        self.root.withdraw()
        cap = cv2.VideoCapture(0)
        angles = ["Center", "Left", "Right", "Up", "Down"]
        captured_encodings = []

        try:
            for angle in angles:
                captured = False
                while not captured:
                    ret, frame = cap.read()
                    if not ret: break
                    cv2.putText(frame, f"Look {angle} - Press SPACE", (50, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imshow("Face Capture", frame)
                    key = cv2.waitKey(1)
                    if key == 32:  # Space
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        boxes = face_recognition.face_locations(rgb)
                        if boxes:
                            encs = face_recognition.face_encodings(rgb, boxes)
                            if encs:
                                captured_encodings.append(encs[0].tolist())
                                captured = True
                                cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), (0, 255, 0), 20)
                                cv2.imshow("Face Capture", frame)
                                cv2.waitKey(500)
                    if key == 27:  # ESC
                        cap.release()
                        cv2.destroyAllWindows()
                        self.root.deiconify()
                        return

            if len(captured_encodings) == 5:
                password = simpledialog.askstring("Auth Required", "Enter password to save:", show="*",
                                                  parent=self.root)
                response = self.net.send_request("UPDATE_FACE", {
                    "username": self.username, "password": password, "face_data": captured_encodings
                })
                if response.get("status") == "SUCCESS":
                    messagebox.showinfo("Success", "Face ID Updated!", parent=self.root)
                else:
                    messagebox.showerror("Error", "Failed to save.", parent=self.root)
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.root.attributes('-topmost', True)

    def close(self):
        self.root.destroy()