import tkinter as tk
import threading
import os


class LockScreen:
    def __init__(self, on_wake_callback):
        self.root = None
        self.is_locked = False
        self.on_wake = on_wake_callback  # Function to call when user presses Space/Click

    def _show_black_screen(self):
        self.root = tk.Tk()

        # 1. Full Black Screen (Sleep Mode)
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black', cursor="none")  # Hide mouse cursor

        # 2. Event Bindings (The Wake Up Triggers)
        self.root.bind("<space>", self._trigger_wake)
        self.root.bind("<Button-1>", self._trigger_wake)  # Left Click
        self.root.bind("<Escape>", self._emergency_exit)

        # 3. Sleeping Message
        self.lbl_msg = tk.Label(
            self.root,
            text="Press SPACE to Start Session",
            font=("Arial", 16),
            fg="#555555",  # Dim text
            bg="black"
        )
        self.lbl_msg.pack(expand=True)

        self.root.focus_force()
        self.root.mainloop()

    def _trigger_wake(self, event):
        """Called when user presses Space or Clicks."""
        self.lbl_msg.config(text="Scanning...", fg="#00ff00")
        self.root.update()
        # Call the logic in main_client to start camera
        self.on_wake()

    def _emergency_exit(self, event=None):
        print("⚠ EMERGENCY EXIT")
        os._exit(0)

    def lock(self):
        """Starts the black screen."""
        if not self.is_locked:
            self.is_locked = True
            # Run the GUI in the main thread (Tkinter prefers this)
            # But since we have other logic, we usually run GUI in main.
            # For this simplified setup, we will start it here.
            self._show_black_screen()

    def update_status(self, text):
        """Updates the text on the black screen."""
        if self.root:
            self.lbl_msg.config(text=text)
            self.root.update()

    def unlock(self):
        """Destroys the lock screen."""
        if self.root:
            self.is_locked = False
            self.root.destroy()
            self.root = None