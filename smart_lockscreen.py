import tkinter as tk


class SmartLockScreen:
    """The black screen that appears when a user walks away."""

    def __init__(self, user, scanner):
        self.user = user
        self.scanner = scanner
        self.result = "TIMEOUT"
        self.time_left = 120  # 2 minutes in seconds

        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg="black")
        self.root.attributes('-topmost', True)

        self.lbl_display = tk.Label(self.root, text="",
                                    font=("Arial", 30), bg="black", fg="white")
        self.lbl_display.place(relx=0.5, rely=0.5, anchor="center")

        # Force the OS to give this window keyboard focus
        self.root.focus_force()
        self.root.grab_set()

        # Key binds
        self.root.bind("<space>", self._on_space)
        self.root.bind("<Escape>", self._on_esc)

        # Fallback: If they click the black screen with their mouse, steal focus back
        self.root.bind("<Button-1>", lambda e: self.root.focus_force())

        # Start the countdown loop
        self._update_timer()

    def _update_timer(self):
        """Updates the countdown every second."""
        if self.time_left <= 0:
            self._on_timeout()
            return

        # Format the remaining seconds into MM:SS
        mins, secs = divmod(self.time_left, 60)
        time_str = f"{mins:02d}:{secs:02d}"

        # Update the UI
        self.lbl_display.config(
            text=f"Session Paused For\n{time_str}\n\nPress SPACE to continue session"
        )

        # Decrement and schedule the next tick
        self.time_left -= 1
        self.timer_id = self.root.after(1000, self._update_timer)

    def _on_space(self, event):
        print("📸 Resuming: Scanning face...")
        # Temporarily pause the countdown while the camera is open
        self.root.after_cancel(self.timer_id)
        self.root.withdraw()  # Hide black screen to show camera window

        match = self.scanner.scan_specific_user(self.user)

        if match:
            print("✅ Face Matched! Resuming session.")
            self.result = "RESUME"
            self.root.destroy()
        else:
            print("🚫 Face match failed. Returning to Smart Lock.")
            self.root.deiconify()  # Bring the black screen back
            self.root.focus_force()
            # Resume the countdown
            self.timer_id = self.root.after(1000, self._update_timer)

    def _on_timeout(self):
        print("⏳ Smart Lock Timeout (2 mins). Logging out completely.")
        self.result = "TIMEOUT"
        self.root.destroy()

    def _on_esc(self, event):
        print("🛑 Emergency Exit Triggered.")
        self.result = "EXIT"
        self.root.after_cancel(self.timer_id)
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result