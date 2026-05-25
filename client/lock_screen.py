import tkinter as tk
import os


class LockScreen:
    """
    Idle lock screen displayed when no user is logged in.

    The screen has two phases: an idle "Press SPACE" phase that hides all
    UI, and a wake phase that shows a username entry field. Submitting a
    username invokes the callback supplied by the caller, which is
    responsible for the actual authentication flow.
    """

    def __init__(self, on_submit_callback):
        self.root = None
        self.is_locked = False
        self.on_submit = on_submit_callback  # Callback receives the typed username.

    def _show_black_screen(self):
        """Builds and displays the fullscreen lock window."""
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black', cursor="none")

        # Primary status label, visible in both idle and wake phases.
        self.lbl_msg = tk.Label(
            self.root,
            text="Press SPACE to Start Session",
            font=("Arial", 20),
            fg="#ffffff",
            bg="black"
        )
        self.lbl_msg.pack(expand=True)

        # Username entry frame — kept unpacked (hidden) until the user wakes
        # the screen, then revealed in _trigger_wake.
        self.entry_frame = tk.Frame(self.root, bg="black")
        self.username_var = tk.StringVar()

        self.entry_user = tk.Entry(
            self.entry_frame,
            textvariable=self.username_var,
            font=("Arial", 18),
            justify="center"
        )
        self.entry_user.pack(pady=10)
        # Pressing Return in the entry submits the username.
        self.entry_user.bind("<Return>", lambda e: self._submit_username())

        self.btn_submit = tk.Button(
            self.entry_frame,
            text="Enter",
            font=("Arial", 14),
            command=self._submit_username
        )
        self.btn_submit.pack()

        # Idle-phase bindings: any space-press or click wakes the screen.
        # Escape is a developer-only emergency exit.
        self.root.bind("<space>", self._trigger_wake)
        self.root.bind("<Button-1>", self._trigger_wake)
        self.root.bind("<Escape>", self._emergency_exit)

        self.root.focus_force()
        self.root.mainloop()

    def _trigger_wake(self, event=None):
        """Transitions from the idle phase to the username-entry phase."""
        self.root.configure(cursor="arrow")  # Restore the mouse cursor.
        self.lbl_msg.config(text="Enter username", fg="#ffffff")

        # Reveal the entry frame and focus the input field.
        self.entry_frame.pack()
        self.entry_user.focus_set()

        # Remove the wake bindings so that typing a space character into the
        # username field doesn't re-trigger this handler.
        self.root.unbind("<space>")
        self.root.unbind("<Button-1>")

    def _submit_username(self):
        """Handles username submission via Enter button or Return key."""
        username = self.username_var.get().strip()
        if not username:
            return

        # Disable the input while the caller processes the username.
        self.entry_user.config(state="disabled")
        self.btn_submit.config(state="disabled")
        self.lbl_msg.config(text="Checking...", fg="yellow")
        self.root.update()

        # Hand control back to the main client.
        self.on_submit(username)

    def reset_to_start(self, error_msg=None):
        """
        Returns the lock screen to its idle phase. If an error message is
        supplied, it is displayed in red for two seconds before reverting
        to the default idle text.
        """
        if not self.root: return

        # Clear the username field and re-hide the entry frame.
        self.username_var.set("")
        self.entry_user.config(state="normal")
        self.btn_submit.config(state="normal")
        self.entry_frame.pack_forget()
        self.root.configure(cursor="none")

        if error_msg:
            # Show the error in red, then schedule the text reset.
            self.lbl_msg.config(text=error_msg, fg="#ff4d4d")
            self.root.update()
            self.root.after(2000, self._reset_text)
        else:
            self._reset_text()

        # Re-enable the wake bindings now that the entry is hidden again.
        self.root.bind("<space>", self._trigger_wake)
        self.root.bind("<Button-1>", self._trigger_wake)
        self.root.focus_force()

    def _reset_text(self):
        """Restores the idle status text after an error message has been displayed."""
        if self.root and self.root.winfo_exists():
            self.lbl_msg.config(text="Press SPACE to Start Session", fg="#ffffff")

    def _emergency_exit(self, event=None):
        """Force-kills the process. Bound to Escape for developer use only."""
        print("EMERGENCY EXIT")
        os._exit(0)

    def blank(self):
        """
        Hides all visible content but keeps the fullscreen black window in
        place. Used by the privacy-screen feature so that the desktop is
        not briefly exposed while the OpenCV face-scan window is open.
        """
        if not self.root: return
        self.lbl_msg.pack_forget()
        self.entry_frame.pack_forget()
        self.root.configure(cursor='none')
        self.root.update()

    def unblank(self):
        """Restores the idle 'Press SPACE' state after a call to blank()."""
        if not self.root: return
        self.username_var.set('')
        self.entry_user.config(state='normal')
        self.btn_submit.config(state='normal')
        self.lbl_msg.config(text='Press SPACE to Start Session', fg='#ffffff')
        self.lbl_msg.pack(expand=True)
        self.root.configure(cursor='none')
        # Re-enable the wake bindings.
        self.root.bind('<space>', self._trigger_wake)
        self.root.bind('<Button-1>', self._trigger_wake)
        self.root.focus_force()
        self.root.update()

    def lock(self):
        """Engages the lock screen. Blocks until unlock() is called."""
        if not self.is_locked:
            self.is_locked = True
            self._show_black_screen()

    def unlock(self):
        """Tears down the lock screen window and releases control to the caller."""
        if self.root:
            self.is_locked = False
            self.root.destroy()
            self.root = None