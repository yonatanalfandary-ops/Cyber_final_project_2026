import tkinter as tk
import threading
import os


class LockScreen:
    def __init__(self):
        self.root = None
        self.is_locked = False
        self.lock_thread = None

    def _show_lock_window(self):
        self.root = tk.Tk()

        # 1. Secure Full Screen
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black')
        self.root.overrideredirect(True)

        # 2. PANIC BUTTON (The Safety Key)
        # Pressing 'Escape' will now force-close the entire program
        self.root.bind("<Escape>", self._emergency_exit)

        # 3. Add Lock Message
        label = tk.Label(
            self.root,
            text="🔒 SYSTEM LOCKED\n\nAuth Required\n(Press ESC to Emergency Quit)",
            font=("Arial", 30, "bold"),
            fg="red",
            bg="black"
        )
        label.pack(expand=True)
        self.root.focus_force()
        self.root.mainloop()

    def _emergency_exit(self, event=None):
        """Kills everything if you get stuck."""
        print("⚠ EMERGENCY EXIT TRIGGERED")
        self.is_locked = False
        if self.root:
            self.root.destroy()
        os._exit(0)  # Force kills the entire Python script

    def lock(self):
        """Activates the lock screen."""
        if not self.is_locked:
            self.is_locked = True
            self.lock_thread = threading.Thread(target=self._show_lock_window)
            self.lock_thread.daemon = True
            self.lock_thread.start()
            print("🔒 SCREEN SHIELD ACTIVATED")

    def unlock(self):
        """Destroys the lock screen."""
        if self.is_locked and self.root:
            self.is_locked = False
            try:
                self.root.quit()
                self.root.destroy()
            except Exception as e:
                print(f"Unlock Error: {e}")
            self.root = None
            print("🔓 SCREEN SHIELD REMOVED")