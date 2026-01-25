import tkinter as tk
from tkinter import messagebox
import sys


class LoginWindow:
    def __init__(self, network_client, station_id):
        self.network = network_client
        self.station_id = station_id
        self.user_data = None
        self.root = None

    def show(self):
        self.root = tk.Tk()
        self.root.title("Cyber Cafe Login")
        self.root.geometry("400x350")  # Slightly taller
        self.root.configure(bg="#2c3e50")

        # Allow closing with the X button or ESC
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.bind("<Escape>", lambda e: self.close_app())

        # Header
        tk.Label(self.root, text="SYSTEM LOCKED", font=("Arial", 20, "bold"), bg="#2c3e50", fg="white").pack(pady=20)

        # Inputs
        tk.Label(self.root, text="Username:", bg="#2c3e50", fg="white").pack()
        self.entry_user = tk.Entry(self.root, font=("Arial", 12))
        self.entry_user.pack(pady=5)

        tk.Label(self.root, text="Password:", bg="#2c3e50", fg="white").pack()
        self.entry_pass = tk.Entry(self.root, show="*", font=("Arial", 12))
        self.entry_pass.pack(pady=5)

        # Login Button
        btn_login = tk.Button(self.root, text="LOGIN", command=self.perform_login, font=("Arial", 12, "bold"),
                              bg="#27ae60", fg="white")
        btn_login.pack(pady=20, ipadx=20)

        # Exit Button (Safe Key)
        btn_exit = tk.Button(self.root, text="Exit System", command=self.close_app, font=("Arial", 10), bg="#c0392b",
                             fg="white")
        btn_exit.pack(pady=5)

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
        print("User closed the application.")
        self.root.destroy()
        sys.exit()  # Clean exit