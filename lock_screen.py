import tkinter as tk
import os


class LockScreen:
    def __init__(self, on_submit_callback):
        self.root = None
        self.is_locked = False
        self.on_submit = on_submit_callback  # Now accepts the username

    def _show_black_screen(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(background='black', cursor="none")

        # 1. Main Message Label
        self.lbl_msg = tk.Label(
            self.root,
            text="Press SPACE to Start Session",
            font=("Arial", 20),
            fg="#555555",
            bg="black"
        )
        self.lbl_msg.pack(expand=True)

        # 2. Hidden Entry Frame (Username Box & Button)
        self.entry_frame = tk.Frame(self.root, bg="black")
        self.username_var = tk.StringVar()

        self.entry_user = tk.Entry(
            self.entry_frame,
            textvariable=self.username_var,
            font=("Arial", 18),
            justify="center"
        )
        self.entry_user.pack(pady=10)
        # Bind the Enter key to submit automatically
        self.entry_user.bind("<Return>", lambda e: self._submit_username())

        self.btn_submit = tk.Button(
            self.entry_frame,
            text="Enter",
            font=("Arial", 14),
            command=self._submit_username
        )
        self.btn_submit.pack()

        # 3. Initial Bindings
        self.root.bind("<space>", self._trigger_wake)
        self.root.bind("<Button-1>", self._trigger_wake)
        self.root.bind("<Escape>", self._emergency_exit)

        self.root.focus_force()
        self.root.mainloop()

    def _trigger_wake(self, event=None):
        """Phase 1: Shows the inline UI when user wakes the screen."""
        self.root.configure(cursor="arrow")  # Bring mouse cursor back
        self.lbl_msg.config(text="Enter username", fg="#ffffff")

        # Show the entry box and focus it
        self.entry_frame.pack()
        self.entry_user.focus_set()

        # Unbind space/click so typing a space in the username doesn't re-trigger this
        self.root.unbind("<space>")
        self.root.unbind("<Button-1>")

    def _submit_username(self):
        """Triggered when they click Enter or hit Return key."""
        username = self.username_var.get().strip()
        if not username:
            return

        # Freeze UI while processing
        self.entry_user.config(state="disabled")
        self.btn_submit.config(state="disabled")
        self.lbl_msg.config(text="Checking...", fg="yellow")
        self.root.update()

        # Pass the typed username back to main_client
        self.on_submit(username)

    def reset_to_start(self, error_msg=None):
        """Resets UI back to the start. Shows an optional error message for 2 seconds."""
        if not self.root: return

        # Clear and hide entry box
        self.username_var.set("")
        self.entry_user.config(state="normal")
        self.btn_submit.config(state="normal")
        self.entry_frame.pack_forget()
        self.root.configure(cursor="none")

        if error_msg:
            # Show the error in red, then queue a reset in 2000ms
            self.lbl_msg.config(text=error_msg, fg="#ff4d4d")
            self.root.update()
            self.root.after(2000, self._reset_text)
        else:
            self._reset_text()

        # Restore bindings
        self.root.bind("<space>", self._trigger_wake)
        self.root.bind("<Button-1>", self._trigger_wake)
        self.root.focus_force()

    def _reset_text(self):
        if self.root and self.root.winfo_exists():
            self.lbl_msg.config(text="Press SPACE to Start Session", fg="#555555")

    def _emergency_exit(self, event=None):
        print("⚠ EMERGENCY EXIT")
        os._exit(0)

    def blank(self):
        """Hides all visible content but keeps the fullscreen black window.
        Used by the privacy screen feature so the desktop isn't exposed
        while the face-scan camera window is open on top.
        """
        if not self.root: return
        self.lbl_msg.pack_forget()
        self.entry_frame.pack_forget()
        self.root.configure(cursor='none')
        self.root.update()

    def unblank(self):
        """Restores the lock screen to its idle 'Press SPACE' state after blanking."""
        if not self.root: return
        self.username_var.set('')
        self.entry_user.config(state='normal')
        self.btn_submit.config(state='normal')
        self.lbl_msg.config(text='Press SPACE to Start Session', fg='#555555')
        self.lbl_msg.pack(expand=True)
        self.root.configure(cursor='none')
        # Restore key bindings
        self.root.bind('<space>', self._trigger_wake)
        self.root.bind('<Button-1>', self._trigger_wake)
        self.root.focus_force()
        self.root.update()

    def lock(self):
        if not self.is_locked:
            self.is_locked = True
            self._show_black_screen()

    def unlock(self):
        if self.root:
            self.is_locked = False
            self.root.destroy()
            self.root = None