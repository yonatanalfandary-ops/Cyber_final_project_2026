import cv2
import time
import numpy as np
import face_recognition
import tkinter as tk
from threading import Thread
from tkinter import messagebox
from settings_window import SettingsWindow
from rent_window import RentWindow


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

        # Warning State
        self.warning_shown = False
        self.is_paused = False

        # Face Data
        self.known_faces = []
        if self.user.get('face_encoding'):
            self.known_faces = [np.array(e) for e in self.user['face_encoding']]

        # UI Components
        self.root = None
        self.lbl_time = None

    def start(self):
        """Starts the background monitor and the Mini-HUD."""
        print(f"--- SESSION STARTED: {self.user['username']} ---")

        # 1. Start the Background Camera Thread
        camera_thread = Thread(target=self._background_monitor, daemon=True)
        camera_thread.start()

        # 2. Start the Mini-Toolbar UI (Main Thread)
        self._create_hud()

        # Cleanup when HUD closes
        self.is_running = False
        return None

    def _create_hud(self):
        self.root = tk.Tk()
        self.root.title("Session Guard")

        # UI Styling: Bottom Right Position
        width, height = 250, 90  # Increased height slightly for better drag handle
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{screen_w - width - 20}+{screen_h - height - 60}")

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")

        # --- DRAGGABILITY LOGIC ---
        self._offset_x = 0
        self._offset_y = 0

        def _start_drag(event):
            self._offset_x = event.x
            self._offset_y = event.y

        def _do_drag(event):
            # Calculate the intended position
            new_x = self.root.winfo_x() + event.x - self._offset_x
            new_y = self.root.winfo_y() + event.y - self._offset_y

            # Screen dimensions
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()

            # HUD dimensions
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()

            snap_margin = 25  # Distance in pixels to trigger the snap

            # --- Snap Logic ---
            # Left/Right edges
            if new_x < snap_margin:
                new_x = 0
            elif new_x > sw - ww - snap_margin:
                new_x = sw - ww

            # Top/Bottom edges
            if new_y < snap_margin:
                new_y = 0
            elif new_y > sh - wh - snap_margin:
                new_y = sh - wh

            self.root.geometry(f"+{new_x}+{new_y}")

        # Bind dragging to the main window
        self.root.bind("<Button-1>", _start_drag)
        self.root.bind("<B1-Motion>", _do_drag)
        # ---------------------------

        # Time Label
        self.lbl_time = tk.Label(self.root, text="TIME: 00:00", font=("Arial", 14, "bold"),
                                 bg="#1e1e1e", fg="#00ff00")
        self.lbl_time.pack(pady=5)

        # Also bind dragging to the label so clicking the text works too
        self.lbl_time.bind("<Button-1>", _start_drag)
        self.lbl_time.bind("<B1-Motion>", _do_drag)

        # Subtle Drag Handle Hint
        tk.Label(self.root, text="⋮⋮ DRAG TO REPOSITION ⋮⋮", font=("Arial", 7),
                 bg="#1e1e1e", fg="#444444").pack()

        # Buttons
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(pady=5)

        tk.Button(btn_frame, text="⚙ Settings", command=self._open_settings,
                  bg="#34495e", fg="white", font=("Arial", 9)).pack(side="left", padx=5)

        tk.Button(btn_frame, text="Logout [Q]", command=self._logout,
                  bg="#c0392b", fg="white", font=("Arial", 9)).pack(side="left", padx=5)

        self.root.bind('q', lambda e: self._logout())
        self.root.bind('s', lambda e: self._open_settings())

        self._update_hud_loop()
        self.root.mainloop()

    def _update_hud_loop(self):
        if not self.is_running:
            return

        if not self.is_paused and not self.is_admin:
            # 1. Deduct Local Time (1 second)
            self.balance_mins -= (1 / 60)

            # 2. Sync with server every 5 seconds (FIXED: key 'seconds')
            if time.time() - self.last_sync >= 5:
                self.net.send_request("DEDUCT_TIME", {
                    "username": self.user['username'],
                    "seconds": 5
                })
                self.last_sync = time.time()

        # 3. Update Label Display
        mins = max(0, int(self.balance_mins))
        secs = max(0, int((self.balance_mins * 60) % 60))
        self.lbl_time.config(text=f"TIME: {mins:02d}:{secs:02d}")

        # 4. Color Logic & Warning Trigger
        if self.balance_mins <= 1.0:
            self.lbl_time.config(fg="#ff4d4d")  # Red
            if not self.warning_shown and not self.is_paused and not self.is_admin:
                self._check_low_time()
        else:
            self.lbl_time.config(fg="#00ff00")  # Green
            self.warning_shown = False  # Reset flag if time was added

        # 5. Check Expired
        if self.balance_mins <= 0 and not self.is_admin:
            self._logout("Time Expired!")
            return

        # Schedule next update
        self.root.after(1000, self._update_hud_loop)

    def _background_monitor(self):
        """Headless face recognition loop."""
        cap = cv2.VideoCapture(0)
        while self.is_running:
            if self.is_paused or self.is_admin:
                time.sleep(0.5)
                continue

            ret, frame = cap.read()
            if not ret: continue

            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            found = False
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(self.known_faces, face_encoding, tolerance=0.5)
                if True in matches:
                    found = True
                    break

            if found:
                self.grace_start = None
            else:
                if self.grace_start is None:
                    self.grace_start = time.time()

                if time.time() - self.grace_start > 3:
                    print("⚠️ SECURITY VIOLATION: Face Lost")
                    self.is_running = False
                    self.root.after(0, self._logout, "Security: User Left")
            time.sleep(0.1)
        cap.release()

    def _check_low_time(self):
        """Triggered when time < 1 minute."""
        self.warning_shown = True
        self.is_paused = True  # Stops the timer deduction

        # 1. Ask using the HUD as parent
        ans = messagebox.askyesno("Low Time", "Less than 1 minute left! Add time?", parent=self.root)

        if ans:
            # 2. Pass self.root as the parent to RentWindow
            renter = RentWindow(self.net, self.user['username'])
            added = renter.show(parent=self.root)  # This blocks here until window closes

            if added > 0:
                self._sync_balance_from_server()
                self.warning_shown = False  # Allow warning to trigger again later

        # 3. Resume session logic
        self.is_paused = False
        print("▶ Session Resumed")

    def _sync_balance_from_server(self):
        """Fetches the actual balance from DB to ensure Client/Server sync."""
        response = self.net.send_request("FETCH_ACTIVE_USERS")
        if response and response.get("status") == "SUCCESS":
            for u in response.get("users", []):
                if u['username'] == self.user['username']:
                    self.balance_mins = float(u['time_balance'])
                    print(f"🔄 Sync Success: New Balance {self.balance_mins} mins")
                    break

    def _open_settings(self, event=None):
        self.is_paused = True
        self.root.attributes("-topmost", False)
        settings = SettingsWindow(self.net, self.user['username'], self.root)
        settings.show()
        self.is_paused = False
        self.root.attributes("-topmost", True)

    def _logout(self, reason=None):
        if reason:
            messagebox.showinfo("Session Ended", reason)
        self.is_running = False
        if self.root:
            self.root.destroy()