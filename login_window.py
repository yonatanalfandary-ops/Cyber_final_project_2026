import tkinter as tk
from tkinter import messagebox


class LoginWindow:
    def __init__(self, network_client, station_id):
        self.network = network_client
        self.station_id = station_id
        self.user_data = None
        self.root = None

    def show(self):
        self.root = tk.Tk()

        # --- FULLSCREEN KIOSK MODE ---
        self.root.attributes('-fullscreen', True)  # Fullscreen
        self.root.attributes('-topmost', True)  # Always on top
        # -----------------------------

        self.root.configure(bg="#2c3e50")

        # Bind Escape key to close (Safety feature)
        self.root.bind("<Escape>", lambda e: self.close_app())

        # --- CENTERED CONTENT FRAME ---
        # We create a frame to hold elements so they appear in the middle
        content_frame = tk.Frame(self.root, bg="#2c3e50")
        content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Header
        tk.Label(content_frame, text="SYSTEM LOCKED", font=("Arial", 30, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=30)

        # Inputs
        tk.Label(content_frame, text="Username:", font=("Arial", 14), bg="#2c3e50", fg="white").pack()
        self.entry_user = tk.Entry(content_frame, font=("Arial", 16), width=20)
        self.entry_user.pack(pady=5)

        tk.Label(content_frame, text="Password:", font=("Arial", 14), bg="#2c3e50", fg="white").pack()
        self.entry_pass = tk.Entry(content_frame, show="*", font=("Arial", 16), width=20)
        self.entry_pass.pack(pady=5)

        # Login Button
        btn_login = tk.Button(content_frame, text="LOGIN", command=self.perform_login,
                              font=("Arial", 16, "bold"), bg="#27ae60", fg="white", width=15)
        btn_login.pack(pady=30)

        # Exit Button
        btn_exit = tk.Button(content_frame, text="Cancel", command=self.close_app,
                             font=("Arial", 12), bg="#c0392b", fg="white")
        btn_exit.pack(pady=10)

        self.root.mainloop()
        return self.user_data

    def perform_login(self):
        username = self.entry_user.get()
        password = self.entry_pass.get()

        if not username or not password:
            messagebox.showwarning("Input Error", "Please fill in all fields.")
            return

        print(f"📡 Attempting login for {username}...")
        response = self.network.send_request("LOGIN", {
            "username": username,
            "password": password,
            "station_id": self.station_id
        })

        if response and response.get("status") == "SUCCESS":
            print("✅ Login Successful!")
            self.user_data = response
            self.root.destroy()
        else:
            msg = response.get("message", "Unknown Error") if response else "Server Timeout"
            messagebox.showerror("Login Failed", msg)

    def close_app(self):
        print("Back to Lock Screen.")
        self.root.destroy()
        return None