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
    """
    Runs an active user session. Owns the on-screen HUD, the background
    face-presence monitor, time-balance deduction, and the logout flow.

    The HUD runs on the main thread inside its own Tk root; the camera
    presence check runs on a daemon thread and signals the main thread by
    setting state flags and using root.after(0, ...) for any UI changes.
    """

    def __init__(self, network_client, user_data):
        self.net = network_client
        self.user = user_data
        self.is_running = True
        self.exit_status = "LOGOUT"  # Default exit reason if nothing else is set.

        # Session state
        self.is_admin = (self.user.get('role') == 'root')
        self.balance_mins = float(self.user.get('time_balance', 0))
        self.grace_start = None
        self.last_sync = time.time()

        # Warning / pause state flags
        self.warning_shown = False
        self.is_paused = False
        self._is_logging_out = False

        # Pre-load this user's stored face encodings.
        self.known_faces = []
        if self.user.get('face_encoding'):
            self.known_faces = [np.array(e) for e in self.user['face_encoding']]

        # UI handles
        self.root = None
        self.lbl_time = None

        # Cancellable timer IDs
        self._hud_timer = None
        self._countdown_timer = None

    def start(self):
        """Starts the background monitor and the HUD. Blocks until the session ends."""
        print(f"--- SESSION STARTED: {self.user['username']} ---")

        # Launch the camera-monitor thread.
        self.camera_thread = Thread(target=self._background_monitor, daemon=True)
        self.camera_thread.start()

        # Build and run the HUD on the main thread.
        self._create_hud()

        # The HUD has now closed; signal the monitor to stop.
        self.is_running = False

        # Wait for the camera thread to actually finish so that cap.release()
        # has time to run before the next session opens the camera again.
        if hasattr(self, 'camera_thread') and self.camera_thread.is_alive():
            self.camera_thread.join(timeout=2.0)

        # Persist the exact remaining balance back to the user dict so a
        # resume from pause picks up where the session left off.
        self.user['time_balance'] = self.balance_mins

        return self.exit_status

    def _create_hud(self):
        """Builds the small always-on-top HUD window and starts its update loop."""
        self.root = tk.Tk()
        self.root.title("Session Guard")

        # Anchor the HUD to the bottom-right of the screen by default.
        width, height = 250, 90
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{screen_w - width - 20}+{screen_h - height - 60}")

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e1e")

        # --- Drag-to-reposition handlers ---
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

            # Snap the HUD to the screen edge when dragged close enough.
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

        # Time-remaining display
        self.lbl_time = tk.Label(self.root, text="TIME: 00:00", font=("Arial", 14, "bold"),
                                 bg="#1e1e1e", fg="#00ff00")
        self.lbl_time.pack(pady=5)

        # The label is also a drag handle so the user has a generous grab area.
        self.lbl_time.bind("<Button-1>", _start_drag)
        self.lbl_time.bind("<B1-Motion>", _do_drag)

        tk.Label(self.root, text="⋮⋮ DRAG TO REPOSITION ⋮⋮", font=("Arial", 7),
                 bg="#1e1e1e", fg="#444444").pack()

        # Action buttons
        btn_frame = tk.Frame(self.root, bg="#1e1e1e")
        btn_frame.pack(pady=5)

        tk.Button(btn_frame, text="Settings", command=self._open_settings,
                  bg="#34495e", fg="white", font=("Arial", 9)).pack(side="left", padx=5)

        tk.Button(btn_frame, text="Logout [Q]", command=self._logout,
                  bg="#c0392b", fg="white", font=("Arial", 9)).pack(side="left", padx=5)

        # Keyboard shortcuts: Q to log out, S to open settings.
        self.root.bind('q', lambda e: self._logout())
        self.root.bind('s', lambda e: self._open_settings())

        self._update_hud_loop()
        self.root.mainloop()

    def _update_hud_loop(self):
        """Once-per-second tick: deducts time, syncs with the server, updates the display."""
        if not self.is_running: return

        # Deduct one second's worth of balance for non-admin users while the
        # session is active. Sync the cumulative deduction to the server
        # every five seconds rather than every tick to limit network chatter.
        if not self.is_paused and not self.is_admin:
            self.balance_mins -= (1 / 60)
            if time.time() - self.last_sync >= 5:
                self.net.send_request("DEDUCT_TIME", {
                    "username": self.user['username'],
                    "seconds": 5
                })
                self.last_sync = time.time()

        # Handle balance exhaustion: force the display to 00:00, zero out the
        # balance on the server, and trigger a logout. The update() call
        # ensures the 00:00 is rendered before the messagebox blocks the loop.
        if self.balance_mins <= 0 and not self.is_admin:
            self.lbl_time.config(text="TIME: 00:00", fg="#ff4d4d")
            self.root.update()

            self.net.send_request("EXPIRE_SESSION", {
                "username": self.user['username']
            })

            self.is_running = False
            self._logout("Time Expired!")
            return  # Don't schedule another tick after a forced logout.

        # Normal UI update path.
        if not self._is_logging_out:
            # Clamp the balance so brief overshoots can't display negative time.
            safe_balance = max(0.0, self.balance_mins)
            mins = int(safe_balance)
            secs = int((safe_balance * 60) % 60)
            self.lbl_time.config(text=f"TIME: {mins:02d}:{secs:02d}")

            # Low-time warning: switch the display to red and surface the
            # rent prompt once when less than a minute remains.
            if safe_balance <= 1.0:
                self.lbl_time.config(fg="#ff4d4d")
                if not self.warning_shown and not self.is_paused and not self.is_admin:
                    self._check_low_time()
            else:
                self.lbl_time.config(fg="#00ff00")
                self.warning_shown = False

        # Schedule the next tick.
        self._hud_timer = self.root.after(1000, self._update_hud_loop)

    def _background_monitor(self):
        """
        Daemon thread that watches the webcam for the active user's face.
        If the face is missing for more than three seconds, the session is
        switched to the Paused state.
        """
        cap = None  # Lazily acquired so we don't hold the camera while paused.
        while self.is_running:
            # While paused or for admin sessions, release the camera so other
            # parts of the app (Settings, RentWindow recapture) can use it.
            if self.is_paused or self.is_admin:
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.5)
                continue

            # Re-acquire the camera if we don't already hold it.
            if cap is None:
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

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
                # User present — reset the grace timer.
                self.grace_start = None
            else:
                # Start (or continue) the grace period. After three seconds
                # of continuous absence, transition to the Paused state and
                # tear down the HUD on the main thread.
                if self.grace_start is None:
                    self.grace_start = time.time()

                if time.time() - self.grace_start > 3:
                    print("User Left. Pausing Session...")
                    self.is_running = False
                    self.exit_status = "PAUSED"

                    if self.root:
                        self.root.after(0, self._safe_pause_cleanup)
            time.sleep(0.1)

        if cap is not None:
            cap.release()

    def _fetch_privacy_setting(self):
        """Returns True if the privacy-screen option is enabled on the server."""
        try:
            response = self.net.send_request("GET_SETTING", {"key": "privacy_screen"})
            if response and response.get("status") == "SUCCESS":
                return response.get("value") == "1"
        except Exception:
            pass
        return False

    def _check_low_time(self):
        """Surfaces the low-time prompt and offers an inline rent flow."""
        self.warning_shown = True
        self.is_paused = True

        # If privacy mode is on, place a fullscreen black overlay behind the
        # dialog and rent window so the desktop is never exposed during the
        # interaction.
        overlay = None
        if self._fetch_privacy_setting():
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-fullscreen', True)
            overlay.attributes('-topmost', True)
            overlay.configure(bg='black')
            overlay.update()  # Force a paint before the dialog opens on top.

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
        print("Session Resumed")

    def _sync_balance_from_server(self):
        """Pulls the user's current balance from the server after a rent transaction."""
        response = self.net.send_request("FETCH_ACTIVE_USERS")
        if response and response.get("status") == "SUCCESS":
            for u in response.get("users", []):
                if u['username'] == self.user['username']:
                    self.balance_mins = float(u['time_balance'])
                    print(f"Sync Success: New Balance {self.balance_mins} mins")
                    break

    def _open_settings(self, event=None):
        """Pauses the session, then opens the settings window after a short delay."""
        self.is_paused = True
        self.root.attributes("-topmost", False)

        # Wait for the camera-monitor thread to observe the paused state
        # and release the webcam before opening Settings (which needs the
        # camera for the face recapture flow).
        self.root.after(600, self._show_settings_window)

    def _show_settings_window(self):
        """Opens the settings window with the user's current role."""
        # Forward the role so the "Change Password" button is shown only
        # to admin accounts.
        settings = SettingsWindow(self.net, self.user['username'], self.root, role=self.user.get('role', 'user'))
        settings.show()
        self.is_paused = False
        self.root.attributes("-topmost", True)

    def _logout(self, reason=None, event=None):
        """
        Logout dispatcher. A non-None `reason` indicates an automatic logout
        (e.g. time expired) and skips the confirmation dialog. Otherwise
        the user is asked to confirm they have closed their applications.
        """
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
            # Confirmed — log the user out immediately.
            self._execute_logout()
        elif ans is False:
            # User needs time to close apps — deduct the time they spent on
            # the dialog and start a 10-second force-logout countdown.
            self._deduct_popup_time(elapsed_seconds)
            self.root.attributes("-topmost", True)
            self._start_force_logout_countdown(10)
        else:
            # Cancelled — restore the previous paused state and resume.
            self._deduct_popup_time(elapsed_seconds)
            self._is_logging_out = False
            self.is_paused = was_paused
            self.root.attributes("-topmost", True)

    def _deduct_popup_time(self, elapsed_seconds):
        """Deducts time spent looking at the logout dialog from the user's balance."""
        if self.is_admin: return
        self.balance_mins -= (elapsed_seconds / 60)
        self.net.send_request("DEDUCT_TIME", {
            "username": self.user['username'],
            "seconds": elapsed_seconds
        })

    def _start_force_logout_countdown(self, seconds_left):
        """Recursive countdown that forces a logout when it reaches zero."""
        if seconds_left <= 0:
            self._execute_logout()
            return
        self.lbl_time.config(text=f"CLOSING IN {seconds_left}s...", fg="red")
        self._countdown_timer = self.root.after(1000, lambda: self._start_force_logout_countdown(seconds_left - 1))

    def _safe_pause_cleanup(self):
        """
        Runs on the main thread to safely tear down the HUD when the
        background monitor signals a pause. Cancels pending timers before
        destroying the window so Tk doesn't try to fire them on a dead root.
        """
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
        """Final teardown step scheduled by _execute_logout."""
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass

    def _execute_logout(self, reason=None):
        """Unified cleanup and exit. Stops loops, cancels timers, and destroys the HUD."""
        if reason:
            # If privacy mode is on, place a fullscreen black overlay
            # behind the dialog so the desktop isn't exposed while the
            # session-ended notification is visible. Mirrors the same
            # pattern used by _check_low_time.
            overlay = None
            if self._fetch_privacy_setting():
                try:
                    overlay = tk.Toplevel(self.root)
                    overlay.attributes('-fullscreen', True)
                    overlay.attributes('-topmost', True)
                    overlay.configure(bg='black')
                    overlay.update()
                except:
                    overlay = None

            dialog_parent = overlay if overlay else self.root
            try:
                messagebox.showinfo("Session Ended", reason, parent=dialog_parent)
            except:
                pass

            if overlay:
                try:
                    overlay.destroy()
                except:
                    pass

        # 1. Stop the HUD update loop and the camera monitor.
        self.is_running = False

        # 2. Cancel any pending Tk timers so they don't fire mid-teardown.
        if hasattr(self, '_hud_timer') and self._hud_timer:
            self.root.after_cancel(self._hud_timer)
        if hasattr(self, '_countdown_timer') and self._countdown_timer:
            self.root.after_cancel(self._countdown_timer)

        # 3. Mark the exit status so the caller knows this was a logout.
        self.exit_status = "LOGOUT"

        # 4. Destroy the UI after a brief delay. This gives the background
        # thread time to exit its loop and call cap.release() before the
        # main thread tears Tk down. Without this delay the UI can close
        # too fast and trigger a "Tcl_AsyncDelete async handler deleted by
        # the wrong thread" crash or a stuck webcam handle.
        if self.root:
            self.root.after(200, self._final_destroy)