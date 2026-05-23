import tkinter as tk


class SmartLockScreen:
    """
    Mid-session lock screen displayed when a user walks away from their
    station. Shows a countdown for up to two minutes during which the user
    can return, press SPACE, and resume their session via face
    verification. If the countdown expires the session is terminated.
    """

    def __init__(self, user, scanner, privacy_screen=False):
        self.user = user
        self.scanner = scanner
        self.privacy_screen = privacy_screen
        self.result = "TIMEOUT"
        self.time_left = 120  # Two minutes in seconds.

        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg="black")
        self.root.attributes('-topmost', True)

        self.lbl_display = tk.Label(self.root, text="",
                                    font=("Arial", 30), bg="black", fg="white")
        self.lbl_display.place(relx=0.5, rely=0.5, anchor="center")

        # Force keyboard focus so SPACE is captured immediately.
        self.root.focus_force()
        self.root.grab_set()

        # Key bindings: SPACE to resume, ESC as an emergency exit.
        self.root.bind("<space>", self._on_space)
        self.root.bind("<Escape>", self._on_esc)

        # Clicking the screen also reclaims focus, in case the window
        # manager has stolen it.
        self.root.bind("<Button-1>", lambda e: self.root.focus_force())

        # Begin the countdown.
        self._update_timer()

    def _update_timer(self):
        """Tick handler that refreshes the displayed countdown every second."""
        if self.time_left <= 0:
            self._on_timeout()
            return

        # Format the remaining seconds as MM:SS.
        mins, secs = divmod(self.time_left, 60)
        time_str = f"{mins:02d}:{secs:02d}"

        self.lbl_display.config(
            text=f"Session Paused For\n{time_str}\n\nPress SPACE to continue session"
        )

        # Decrement and schedule the next tick.
        self.time_left -= 1
        self.timer_id = self.root.after(1000, self._update_timer)

    def _on_space(self, event):
        """Attempts to resume the session by verifying the user's face."""
        print("📸 Resuming: Scanning face...")
        # Pause the countdown while the camera is active.
        self.root.after_cancel(self.timer_id)

        if self.privacy_screen:
            # Privacy mode: keep the black window in place as a backdrop so
            # the desktop is never exposed. Clear the label so the camera
            # window appears against a clean black background.
            self.lbl_display.config(text="")
            self.root.update()
        else:
            self.root.withdraw()  # Default behaviour exposes the desktop.

        match = self.scanner.scan_specific_user(self.user)

        if match:
            print("✅ Face Matched! Resuming session.")
            self.result = "RESUME"
            self.root.destroy()
        else:
            print("🚫 Face match failed. Returning to Smart Lock.")
            if not self.privacy_screen:
                self.root.deiconify()
            self.root.focus_force()
            # Restart the countdown (which also restores the label text).
            self.timer_id = self.root.after(1000, self._update_timer)

    def _on_timeout(self):
        """Called when the two-minute timer expires — forces a full logout."""
        print("⏳ Smart Lock Timeout (2 mins). Logging out completely.")
        self.result = "TIMEOUT"
        self.root.destroy()

    def _on_esc(self, event):
        """Developer-only emergency exit, bound to the Escape key."""
        print("🛑 Emergency Exit Triggered.")
        self.result = "EXIT"
        self.root.after_cancel(self.timer_id)
        self.root.destroy()

    def show(self):
        """Runs the event loop and returns the exit reason ('RESUME', 'TIMEOUT', or 'EXIT')."""
        self.root.mainloop()
        return self.result