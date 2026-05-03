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
        self.exit_status = "LOGOUT"  # Defaults to full logout unless paused

        # Session State
        self.is_admin = (self.user.get('role') == 'root')
        self.balance_mins = float(self.user.get('time_balance', 0))
        self.grace_start = None
        self.last_sync = time.time()

        # Warning State
        self.warning_shown = False
        self.is_paused = False
        self._is_logging_out = False

        # Face Data
        self.known_faces = []
        if self.user.get('face_encoding'):
            self.known_faces = [np.array(e) for e in self.user['face_encoding']]

        # UI Components
        self.root = None
        self.lbl_time = None

        self._hud_timer = None
        self._countdown_timer = None

    def start(self):
        """Starts the background monitor and the Mini-HUD."""
        print(f"--- SESSION STARTED: {self.user['username']} ---")

        # 1. Start the Background Camera Thread (Store it as self.camera_thread)
        self.camera_thread = Thread(target=self._background_monitor, daemon=True)
        self.camera_thread.start()

        # 2. Start the Mini-Toolbar UI (Main Thread)
        self._create_hud()

        # Cleanup when HUD closes
        self.is_running = False

        # --- THE FIX: Wait for the background thread to actually die ---
        if hasattr(self, 'camera_thread') and self.camera_thread.is_alive():
            self.camera_thread.join(timeout=2.0) # Give it up to 2 seconds to run cap.release()

        # Save exact balance back to the user dictionary for when they resume!
        self.user['time_balance'] = self.balance_mins

        return self.exit_status

    def _create_hud(self):
        self.root = tk.Tk()
        self.root.title("Session Guard")

        # UI Styling: Bottom Right Position
        width, height = 250, 90
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
            new_x = self.root.winfo_x() + event.x - self._offset_x
            new_y = self.root.winfo_y() + event.y - self._offset_y
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()
            snap_margin = 25

            if new_x < snap_margin:
                new_x = 0
            elif new_x > sw - ww - snap_margin:
                new_x = sw - ww
            if new_y < snap_margin:
                new_y = 0
            elif new_y > sh - wh - snap_margin:
                new_y = sh - wh

            self.root.geometry(f"+{new_x}+{new_y}")

        self.root.bind("<Button-1>", _start_drag)
        self.root.bind("<B1-Motion>", _do_drag)
        # ---------------------------

        # Time Label
        self.lbl_time = tk.Label(self.root, text="TIME: 00:00", font=("Arial", 14, "bold"),
                                 bg="#1e1e1e", fg="#00ff00")
        self.lbl_time.pack(pady=5)

        self.lbl_time.bind("<Button-1>", _start_drag)
        self.lbl_time.bind("<B1-Motion>", _do_drag)

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
        if not self.is_running: return

        # 1. Deduct Time
        if not self.is_paused and not self.is_admin:
            self.balance_mins -= (1 / 60)
            if time.time() - self.last_sync >= 5:
                self.net.send_request("DEDUCT_TIME", {
                    "username": self.user['username'],
                    "seconds": 5
                })
                self.last_sync = time.time()

        # 2. THE FIX: Catch the timeout immediately, force 00:00, and halt the loop
        if self.balance_mins <= 0 and not self.is_admin:
            self.lbl_time.config(text="TIME: 00:00", fg="#ff4d4d")
            self.root.update()  # Force UI to draw the 00:00 before the popup blocks it

            # --- Cleanly zero out the balance on the server ---
            self.net.send_request("EXPIRE_SESSION", {
                "username": self.user['username']
            })

            self.is_running = False  # Stop background threads
            self._logout("Time Expired!")
            return  # Exit function so the 'after' loop doesn't trigger again

        # 3. Safe UI Update for active sessions
        if not self._is_logging_out:
            # Clamp the math value so it never calculates a negative time
            safe_balance = max(0.0, self.balance_mins)
            mins = int(safe_balance)
            secs = int((safe_balance * 60) % 60)
            self.lbl_time.config(text=f"TIME: {mins:02d}:{secs:02d}")

            # Low Time Warning Check
            if safe_balance <= 1.0:
                self.lbl_time.config(fg="#ff4d4d")
                if not self.warning_shown and not self.is_paused and not self.is_admin:
                    self._check_low_time()
            else:
                self.lbl_time.config(fg="#00ff00")
                self.warning_shown = False

        # 4. Schedule next tick
        self._hud_timer = self.root.after(1000, self._update_hud_loop)

    def _background_monitor(self):
        cap = None  # Start with no camera
        while self.is_running:
            # --- THE FIX: Release the camera if paused or admin ---
            if self.is_paused or self.is_admin:
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.5)
                continue

            # --- Re-acquire the camera if we are active ---
            if cap is None:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Use DSHOW here too!

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
                    print("⏸️ User Left. Pausing Session...")
                    self.is_running = False
                    self.exit_status = "PAUSED"

                    if self.root:
                        self.root.after(0, self._safe_pause_cleanup)
            time.sleep(0.1)

        if cap is not None:
            cap.release()

    def _fetch_privacy_setting(self):
        """Returns True if the privacy screen is enabled on the server."""
        try:
            response = self.net.send_request("GET_SETTING", {"key": "privacy_screen"})
            if response and response.get("status") == "SUCCESS":
                return response.get("value") == "1"
        except Exception:
            pass
        return False

    def _check_low_time(self):
        self.warning_shown = True
        self.is_paused = True

        # If privacy screen is on, place a fullscreen black overlay behind
        # the dialog and rent window so the desktop isn't exposed.
        overlay = None
        if self._fetch_privacy_setting():
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-fullscreen', True)
            overlay.attributes('-topmost', True)
            overlay.configure(bg='black')
            overlay.update()  # Force draw before the dialog opens on top

        dialog_parent = overlay if overlay else self.root
        ans = messagebox.askyesno("Low Time", "Less than 1 minute left! Add time?", parent=dialog_parent)
        if ans:
            renter = RentWindow(self.net, self.user['username'])
            added = renter.show(parent=dialog_parent)
            if added > 0:
                self._sync_balance_from_server()
                self.warning_shown = False

        if overlay:
            overlay.destroy()

        self.is_paused = False
        print("▶ Session Resumed")

    def _sync_balance_from_server(self):
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

        # THE FIX: Wait 600ms for the background thread to see it is paused
        # and release the camera, THEN open the settings window.
        self.root.after(600, self._show_settings_window)

    def _show_settings_window(self):
        # Also pass the user role here so the "Change Password" button shows up correctly for root!
        settings = SettingsWindow(self.net, self.user['username'], self.root, role=self.user.get('role', 'user'))
        settings.show()
        self.is_paused = False
        self.root.attributes("-topmost", True)

    def _logout(self, reason=None, event=None):
        if reason:
            self._execute_logout(reason)
            return

        if self._is_logging_out: return
        self._is_logging_out = True

        was_paused = self.is_paused
        self.is_paused = True
        self.root.attributes("-topmost", False)
        start_time = time.time()

        ans = messagebox.askyesnocancel("Logout Warning", "Have you closed all your applications?", parent=self.root)
        elapsed_seconds = time.time() - start_time

        if ans is True:
            self._execute_logout()
        elif ans is False:
            self._deduct_popup_time(elapsed_seconds)
            self.root.attributes("-topmost", True)
            self._start_force_logout_countdown(10)
        else:
            self._deduct_popup_time(elapsed_seconds)
            self._is_logging_out = False
            self.is_paused = was_paused
            self.root.attributes("-topmost", True)

    def _deduct_popup_time(self, elapsed_seconds):
        if self.is_admin: return
        self.balance_mins -= (elapsed_seconds / 60)
        self.net.send_request("DEDUCT_TIME", {
            "username": self.user['username'],
            "seconds": elapsed_seconds
        })

    def _start_force_logout_countdown(self, seconds_left):
        if seconds_left <= 0:
            self._execute_logout()
            return
        self.lbl_time.config(text=f"CLOSING IN {seconds_left}s...", fg="red")
        self._countdown_timer = self.root.after(1000, lambda: self._start_force_logout_countdown(seconds_left - 1))

    def _safe_pause_cleanup(self):
        """Executes strictly in the MAIN thread to safely stop Tkinter timers and UI."""
        if hasattr(self, '_hud_timer') and self._hud_timer:
            self.root.after_cancel(self._hud_timer)
        if hasattr(self, '_countdown_timer') and self._countdown_timer:
            self.root.after_cancel(self._countdown_timer)

        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass

    def _final_destroy(self):
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass

    def _execute_logout(self, reason=None):
        """The Unified Cleanup & Exit Function"""
        if reason:
            try:
                messagebox.showinfo("Session Ended", reason, parent=self.root)
            except:
                pass

        # 1. Stop the loops
        self.is_running = False

        # 2. Cancel the TKinter timers immediately
        if hasattr(self, '_hud_timer') and self._hud_timer:
            self.root.after_cancel(self._hud_timer)
        if hasattr(self, '_countdown_timer') and self._countdown_timer:
            self.root.after_cancel(self._countdown_timer)

        # 3. Finalize State
        self.exit_status = "LOGOUT"

        # 4. Thread-Safe UI Destruction with a tiny delay for the camera

        # Wait 200ms before destroying the UI. This gives the background thread
        # enough time to exit its loop and execute cap.release().
        # Without this delay, the UI closes too fast, causing a race condition
        # that triggers a "Tcl_AsyncDelete async handler deleted by the wrong thread " crash or locks up the webcam.
        if self.root:
            self.root.after(200, self._final_destroy)