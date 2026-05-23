import tkinter as tk
from tkinter import messagebox
from settings_window import SettingsWindow


class RentWindow:
    """
    Fullscreen payment window shown when a user with a zero time balance
    successfully passes face authentication. Allows the user to purchase
    additional minutes (or open their account settings) before starting
    the session.
    """

    def __init__(self, network_client, username):
        self.net = network_client
        self.username = username
        self.added_time = 0
        self.root = None
        self.price_per_min = 0.50  # Rate in dollars per minute.

    def show(self, parent=None):
        """
        Displays the window and blocks until it is closed.
        Returns the number of minutes the user successfully purchased
        (0 if they cancelled or the transaction failed).
        """
        # Use Toplevel rather than Tk() so this window attaches to an
        # existing Tk root — creating a second Tk() instance would crash
        # the Tkinter event loop.
        if parent:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Toplevel()

        self.root.grab_set()  # Modal: focus stays on this window.

        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg="#2c3e50")

        # All content is placed inside a centered frame.
        content_frame = tk.Frame(self.root, bg="#2c3e50")
        content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Header
        self.lbl_welcome = tk.Label(content_frame, text=f"Hello, {self.username}",
                                    font=("Arial", 24), bg="#2c3e50", fg="white")
        self.lbl_welcome.pack(pady=20)

        tk.Label(content_frame, text=f"Rate: ${self.price_per_min:.2f} / min",
                 font=("Arial", 14, "italic"), bg="#2c3e50", fg="#bdc3c7").pack()

        # Input section
        tk.Label(content_frame, text="How many minutes do you want?",
                 font=("Arial", 16), bg="#2c3e50", fg="#ecf0f1").pack(pady=(30, 10))

        # Restrict entry to digits only via a Tk validation command.
        vcmd = (self.root.register(self.validate_number), '%P')

        self.entry_mins = tk.Entry(content_frame, font=("Arial", 30), justify='center', width=8,
                                   validate='key', validatecommand=vcmd)
        self.entry_mins.pack(pady=10)
        self.entry_mins.bind("<KeyRelease>", self.update_price_display)

        # Live-updating total price display.
        self.lbl_price = tk.Label(content_frame, text="Total: $0.00",
                                  font=("Arial", 28, "bold"), bg="#2c3e50", fg="#f1c40f")
        self.lbl_price.pack(pady=20)

        # Payment button
        tk.Button(content_frame, text="PAY & UNLOCK", font=("Arial", 18, "bold"),
                  bg="#27ae60", fg="white", width=20, command=self.process_payment).pack(pady=5)

        # Account settings shortcut so the user can update details (e.g.
        # their face encoding) without first having to add time.
        tk.Button(content_frame, text="Account Settings", command=self.open_settings,
                  font=("Arial", 12), bg="#3498db", fg="white").pack(pady=10)

        # Cancel — returns the user to the lock screen.
        tk.Button(content_frame, text="Cancel", command=self.close,
                  font=("Arial", 14), bg="#c0392b", fg="white").pack(pady=10)

        self.entry_mins.focus_set()

        # Block until the window is destroyed (either by Pay or Cancel).
        self.root.wait_window()

        # Execution resumes here once the window closes; return the
        # purchased minutes to the caller.
        return self.added_time

    def open_settings(self):
        """Hides this window and opens the settings window on top of it."""
        self.root.withdraw()
        # Pass self.root as the parent so the settings window attaches
        # to the same Tk root.
        settings = SettingsWindow(self.net, self.username, self.root, from_payment=True)
        updated_username = settings.show()

        # If the user changed their username inside Settings, reflect it here.
        if updated_username:
            self.username = updated_username
            self.lbl_welcome.config(text=f"Hello, {self.username}")

        self.root.deiconify()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)

    def validate_number(self, new_text):
        """Tk validation callback: allows only digits or an empty string."""
        if new_text == "": return True
        return new_text.isdigit()

    def update_price_display(self, event=None):
        """Recalculates and displays the total cost whenever the input changes."""
        text = self.entry_mins.get()
        if not text:
            self.lbl_price.config(text="Total: $0.00")
            return
        try:
            mins = int(text)
            cost = mins * self.price_per_min
            self.lbl_price.config(text=f"Total: ${cost:.2f}")
        except ValueError:
            self.lbl_price.config(text="Total: $0.00")

    def process_payment(self):
        """Confirms the charge with the user and submits the ADD_TIME request."""
        try:
            text = self.entry_mins.get()
            if not text: return
            minutes = int(text)
            if minutes <= 0: return

            cost = minutes * self.price_per_min

            # Use parent=self.root so the dialog appears on top of the
            # fullscreen rent window rather than behind it.
            confirm = messagebox.askyesno("Confirm Payment",
                                          f"Charge card ${cost:.2f} for {minutes} mins?",
                                          parent=self.root)
            if not confirm: return

            response = self.net.send_request("ADD_TIME", {
                "username": self.username,
                "minutes": minutes
            })

            if response and response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", "Payment Accepted!", parent=self.root)
                self.added_time = minutes
                self.root.destroy()
            else:
                messagebox.showerror("Error", "Transaction Failed.", parent=self.root)

        except ValueError:
            pass

    def close(self):
        """Closes the window without purchasing any time."""
        self.root.destroy()