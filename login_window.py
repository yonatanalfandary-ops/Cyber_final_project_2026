import tkinter as tk
from tkinter import messagebox


class LoginWindow:
    """
    Fullscreen kiosk-style login window used as the admin fallback when
    face-ID authentication is unavailable or has failed. Standard users
    cannot reach this window; it is only invoked for accounts with the
    'root' role.
    """

    def __init__(self, network_client, station_id):
        self.network = network_client
        self.station_id = station_id
        self.user_data = None
        self.root = None

    def show(self):
        """Displays the login window and blocks until it is closed.
        Returns the authenticated user's data dictionary, or None on cancel."""
        self.root = tk.Tk()

        # Kiosk-mode window: fullscreen and always on top so the user
        # cannot drop out to the desktop.
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)

        self.root.configure(bg="#2c3e50")

        # Escape is bound as a safety hatch to close the window.
        self.root.bind("<Escape>", lambda e: self.close_app())

        # All content is placed inside a centered frame so it remains
        # visually centred regardless of the screen resolution.
        content_frame = tk.Frame(self.root, bg="#2c3e50")
        content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Header
        tk.Label(content_frame, text="ADMIN LOGIN", font=("Arial", 30, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=30)

        # Credential inputs
        tk.Label(content_frame, text="Username:", font=("Arial", 14), bg="#2c3e50", fg="white").pack()
        self.entry_user = tk.Entry(content_frame, font=("Arial", 16), width=20)
        self.entry_user.pack(pady=5)

        tk.Label(content_frame, text="Password:", font=("Arial", 14), bg="#2c3e50", fg="white").pack()
        self.entry_pass = tk.Entry(content_frame, show="*", font=("Arial", 16), width=20)
        self.entry_pass.pack(pady=5)

        # Submit
        btn_login = tk.Button(content_frame, text="LOGIN", command=self.perform_login,
                              font=("Arial", 16, "bold"), bg="#27ae60", fg="white", width=15)
        btn_login.pack(pady=30)

        # Cancel — returns control to the lock screen.
        btn_exit = tk.Button(content_frame, text="Cancel", command=self.close_app,
                             font=("Arial", 12), bg="#c0392b", fg="white")
        btn_exit.pack(pady=10)

        self.root.mainloop()
        return self.user_data

    def perform_login(self):
        """Validates the inputs and sends a LOGIN request to the server."""
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

        # If the admin is already logged in on another station, the server
        # returns a dedicated error code. Surface it as a clear message and
        # clear the password field so it can be re-entered safely.
        elif response and response.get("status") == "ERROR_USER_ALREADY_LOGGED_IN":
            print("❌ Login Blocked: Admin already active elsewhere.")
            messagebox.showerror("Login Failed", "Login Blocked: Admin is already active elsewhere.")
            self.entry_pass.delete(0, tk.END)

        else:
            msg = response.get("message", "Unknown Error") if response else "Server Timeout"
            messagebox.showerror("Login Failed", msg)

    def close_app(self):
        """Closes the window and returns control to the lock screen."""
        print("Back to Lock Screen.")
        self.root.destroy()
        return None