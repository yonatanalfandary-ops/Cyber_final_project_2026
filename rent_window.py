import tkinter as tk
from tkinter import messagebox
from settings_window import SettingsWindow

class RentWindow:
    def __init__(self, network_client, username):
        self.net = network_client
        self.username = username
        self.added_time = 0
        self.root = None
        self.price_per_min = 0.50  # CONFIG: $0.50 per minute

    def show(self):
        """Displays the window and returns the minutes added (or 0 if cancelled)."""
        self.root = tk.Tk()

        # --- FULLSCREEN KIOSK MODE ---
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        # -----------------------------

        self.root.configure(bg="#2c3e50")

        # --- CENTERED CONTENT FRAME ---
        content_frame = tk.Frame(self.root, bg="#2c3e50")
        content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Header
        tk.Label(content_frame, text=f"Hello, {self.username}",
                 font=("Arial", 24), bg="#2c3e50", fg="white").pack(pady=20)

        tk.Label(content_frame, text=f"Rate: ${self.price_per_min:.2f} / min",
                 font=("Arial", 14, "italic"), bg="#2c3e50", fg="#bdc3c7").pack()

        # Input Section
        tk.Label(content_frame, text="How many minutes do you want?",
                 font=("Arial", 16), bg="#2c3e50", fg="#ecf0f1").pack(pady=(30, 10))

        # Validation Setup
        vcmd = (self.root.register(self.validate_number), '%P')

        # Entry Box
        self.entry_mins = tk.Entry(content_frame, font=("Arial", 30), justify='center', width=8,
                                   validate='key', validatecommand=vcmd)
        self.entry_mins.pack(pady=10)
        self.entry_mins.bind("<KeyRelease>", self.update_price_display)

        # Price Display
        self.lbl_price = tk.Label(content_frame, text="Total: $0.00",
                                  font=("Arial", 28, "bold"), bg="#2c3e50", fg="#f1c40f")
        self.lbl_price.pack(pady=20)

        # Payment Button
        tk.Button(content_frame, text="PAY & UNLOCK", font=("Arial", 18, "bold"),
                  bg="#27ae60", fg="white", width=20, command=self.process_payment).pack(pady=5)

        # --- NEW SETTINGS BUTTON ---
        tk.Button(content_frame, text="Account Settings", command=self.open_settings,
                  font=("Arial", 12), bg="#3498db", fg="white").pack(pady=10)
        # ---------------------------

        # Cancel Button
        tk.Button(content_frame, text="Cancel", command=self.close,
                  font=("Arial", 14), bg="#c0392b", fg="white").pack(pady=10)

        self.entry_mins.focus_set()

        self.root.mainloop()
        return self.added_time

    def open_settings(self):
        self.root.withdraw()

        # Pass True because we want the "Back to Payment" button
        settings = SettingsWindow(self.net, self.username, self.root, from_payment=True)

        updated_username = settings.show()
        self.username = updated_username

        self.root.deiconify()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)

    def validate_number(self, new_text):
        if new_text == "": return True
        return new_text.isdigit()

    def update_price_display(self, event=None):
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
        try:
            text = self.entry_mins.get()
            if not text: return
            minutes = int(text)
            if minutes <= 0: return

            cost = minutes * self.price_per_min

            confirm = messagebox.askyesno("Confirm Payment", f"Charge card ${cost:.2f} for {minutes} mins?")
            if not confirm: return

            print(f"💳 Processing payment: ${cost:.2f} for {minutes} mins...")
            response = self.net.send_request("ADD_TIME", {
                "username": self.username,
                "minutes": minutes
            })

            if response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", "Payment Accepted! Unlocking station...")
                self.added_time = minutes
                self.root.destroy()
            else:
                messagebox.showerror("Error", "Transaction Failed. Try again.")

        except ValueError:
            pass

    def close(self):
        self.root.destroy()