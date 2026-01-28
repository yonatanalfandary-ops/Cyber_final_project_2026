import tkinter as tk
from tkinter import simpledialog, messagebox
import cv2
import face_recognition


class AdminPanel:
    def __init__(self, network_client, admin_username):
        self.net = network_client
        self.admin_username = admin_username
        self.root = None
        self.listbox = None
        self.users_cache = []

    def show(self):
        self.root = tk.Tk()

        # --- KIOSK MODE SETUP ---
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg="#2c3e50")

        # --- TOP CONTROL BAR (Header) ---
        top_bar = tk.Frame(self.root, bg="#34495e", height=60)
        top_bar.pack(side="top", fill="x")
        top_bar.pack_propagate(False)  # Prevent shrinking

        # Title (Left)
        tk.Label(top_bar, text=f"🔧 ADMIN PANEL | {self.admin_username}",
                 font=("Arial", 18, "bold"), bg="#34495e", fg="#ecf0f1").pack(side="left", padx=20)

        # Logout Button (Right)
        tk.Button(top_bar, text="LOGOUT", command=self.close,
                  font=("Arial", 12, "bold"), bg="#c0392b", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # Minimize Button (Right)
        tk.Button(top_bar, text="_ Minimize", command=self.minimize_window,
                  font=("Arial", 12, "bold"), bg="#7f8c8d", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # --- MAIN CONTENT ---
        main_frame = tk.Frame(self.root, bg="#2c3e50")
        main_frame.pack(fill="both", expand=True, padx=50, pady=20)

        # LEFT: User List
        left_frame = tk.Frame(main_frame, bg="#34495e", width=400)
        left_frame.pack(side="left", fill="y", padx=20)

        tk.Label(left_frame, text="User Database", font=("Arial", 14, "bold"), bg="#34495e", fg="white").pack(pady=10)

        self.listbox = tk.Listbox(left_frame, font=("Arial", 14), width=30, height=20)
        self.listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        tk.Button(left_frame, text="Refresh List", command=self.fetch_users, bg="#7f8c8d", fg="white").pack(pady=10,
                                                                                                            fill="x")

        # RIGHT: Actions
        right_frame = tk.Frame(main_frame, bg="#2c3e50")
        right_frame.pack(side="right", fill="both", expand=True, padx=20)

        tk.Label(right_frame, text="Management Actions", font=("Arial", 16, "bold"), bg="#2c3e50", fg="white").pack(
            pady=10)

        self.btn_create = tk.Button(right_frame, text="➕ Create New User", command=self.create_user,
                                    font=("Arial", 12), bg="#27ae60", fg="white", width=30)
        self.btn_create.pack(pady=8)

        self.btn_delete = tk.Button(right_frame, text="❌ Delete Selected", command=self.delete_user,
                                    font=("Arial", 12), bg="#c0392b", fg="white", width=30)
        self.btn_delete.pack(pady=8)

        tk.Label(right_frame, text="--- Edit Selected ---", bg="#2c3e50", fg="#95a5a6").pack(pady=15)

        self.btn_time = tk.Button(right_frame, text="⏳ Add/Remove Time", command=self.manage_time,
                                  font=("Arial", 12), bg="#2980b9", fg="white", width=30)
        self.btn_time.pack(pady=8)

        self.btn_face = tk.Button(right_frame, text="📸 Recapture Face ID", command=self.recapture_face,
                                  font=("Arial", 12), bg="#e67e22", fg="white", width=30)
        self.btn_face.pack(pady=8)

        self.btn_edit_profile = tk.Button(right_frame, text="📝 Edit Details", command=self.edit_details,
                                          font=("Arial", 12), bg="#8e44ad", fg="white", width=30)
        self.btn_edit_profile.pack(pady=8)

        # Initial Load
        self.fetch_users()
        self.root.mainloop()

    # --- NEW: Minimize Logic ---
    def minimize_window(self):
        # We must disable 'topmost' briefly so the window doesn't fight the OS when minimized
        self.root.attributes('-topmost', False)
        self.root.iconify()
        # Bind the 'Map' event (which happens when window is restored) to re-enable topmost
        self.root.bind("<Map>", self.restore_topmost)

    def restore_topmost(self, event):
        if self.root.state() == 'normal':
            self.root.attributes('-topmost', True)
            self.root.attributes('-fullscreen', True)
            # Unbind to prevent loop
            self.root.unbind("<Map>")

    # --- EXISTING METHODS (Same as before) ---
    def fetch_users(self):
        self.listbox.delete(0, tk.END)
        response = self.net.send_request("FETCH_ALL_USERS", {})

        if response and response.get("status") == "SUCCESS":
            all_users = response.get("users", [])
            self.users_cache = []  # Clear the cache before rebuilding

            for u in all_users:
                # 1. Filter: Skip the currently logged-in admin
                if u['username'] == self.admin_username:
                    continue

                # 2. Add to valid cache (so clicks map to the right user)
                self.users_cache.append(u)

                # 3. Update UI
                display = f"{u['username']} | {u['role']} | {u['time_balance']}m"
                self.listbox.insert(tk.END, display)
        else:
            messagebox.showerror("Error", "Failed to fetch users.")

    def get_selected_user(self):
        idx = self.listbox.curselection()
        if not idx:
            messagebox.showwarning("Selection", "Please select a user first.")
            return None
        return self.users_cache[idx[0]]

    def create_user(self):
        username = simpledialog.askstring("New User", "Username:", parent=self.root)
        if not username: return
        password = simpledialog.askstring("New User", "Password:", parent=self.root)
        if not password: return
        fullname = simpledialog.askstring("New User", "Full Name:", parent=self.root)
        role = simpledialog.askstring("New User", "Role (user/root):", initialvalue="user", parent=self.root)

        response = self.net.send_request("CREATE_USER", {
            "username": username, "password": password, "full_name": fullname, "role": role
        })
        if response.get("status") == "SUCCESS":
            messagebox.showinfo("Success", "User Created!")
            self.fetch_users()
        else:
            messagebox.showerror("Error", response.get("message"))

    def delete_user(self):
        user = self.get_selected_user()
        if not user: return
        if user['username'] == self.admin_username:
            messagebox.showerror("Error", "You cannot delete yourself!")
            return

        confirm = messagebox.askyesno("Confirm", f"Delete user '{user['username']}' permanently?")
        if confirm:
            self.net.send_request("DELETE_USER", {"username": user['username']})
            self.fetch_users()

    def manage_time(self):
        user = self.get_selected_user()
        if not user: return

        # --- 1. SETUP CUSTOM DIALOG ---
        dialog = tk.Toplevel(self.root)
        dialog.title("Adjust Time")
        dialog.geometry("350x200")
        dialog.configure(bg="#34495e")
        dialog.attributes('-topmost', True)  # Keep it on top

        # Center the dialog
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 100
        dialog.geometry(f"+{x}+{y}")

        # --- 2. UI ELEMENTS ---
        tk.Label(dialog, text=f"Adjust Balance: {user['username']}",
                 font=("Arial", 12, "bold"), bg="#34495e", fg="white").pack(pady=(20, 2))

        tk.Label(dialog, text=f"Current: {user['time_balance']} mins",
                 font=("Arial", 10), bg="#34495e", fg="#bdc3c7").pack(pady=2)

        tk.Label(dialog, text="Enter minutes (+ or -):",
                 font=("Arial", 10), bg="#34495e", fg="white").pack(pady=2)

        # --- 3. INPUT FIELD WITH VALIDATION ---
        # Register the validation command
        vcmd = (dialog.register(self.validate_time_input), '%P')

        entry = tk.Entry(dialog, font=("Arial", 14), justify='center',
                         validate="key", validatecommand=vcmd)
        entry.pack(pady=8, padx=20, ipadx=5, ipady=3)
        entry.focus_set()  # Focus automatically

        # Variable to store result
        self.time_input_value = None

        def on_submit(event=None):  # Allow 'Enter' key to submit
            val = entry.get()
            if val == "" or val == "-":
                # If they leave it empty or just "-", do nothing
                dialog.destroy()
                return

            self.time_input_value = int(val)
            dialog.destroy()

        # Submit Button
        tk.Button(dialog, text="Update Balance", command=on_submit,
                  bg="#27ae60", fg="white", font=("Arial", 11, "bold")).pack(pady=8)

        # Bind 'Enter' key to submit
        dialog.bind('<Return>', on_submit)

        # --- 4. WAIT FOR INPUT ---
        self.root.wait_window(dialog)  # Code pauses here until dialog closes

        # --- 5. PROCESS RESULT ---
        if self.time_input_value is not None:
            self.net.send_request("ADD_TIME", {
                "username": user['username'],
                "minutes": self.time_input_value
            })
            self.fetch_users()
            messagebox.showinfo("Success", "Time balance updated.", parent=self.root)

    def edit_details(self):
        user = self.get_selected_user()
        if not user: return

        # CHANGED: 'password_hash' -> 'password'
        choice = simpledialog.askstring("Edit", "Type field to edit: 'full_name', 'password', 'username', 'role'",
                                        parent=self.root)

        if choice not in ['full_name', 'password', 'username', 'role']:
            messagebox.showerror("Error", "Invalid field name")
            return

        new_val = simpledialog.askstring("Edit", f"Enter new value for {choice}:", parent=self.root)
        if new_val:
            self.net.send_request("UPDATE_PROFILE", {"username": user['username'], "field": choice, "value": new_val})
            self.fetch_users()

    def recapture_face(self):
        user = self.get_selected_user()
        if not user: return

        confirm = messagebox.askyesno("Recapture",
                                      f"Recapture Face ID for {user['username']}?\n(Admin must operate camera)",
                                      parent=self.root)
        if not confirm: return

        self.root.withdraw()
        cap = cv2.VideoCapture(0)
        captured_encodings = []
        angles = ["Center", "Left", "Right", "Up", "Down"]

        try:
            for angle in angles:
                captured = False
                while not captured:
                    ret, frame = cap.read()
                    if not ret: break
                    cv2.putText(frame, f"User: {user['username']} - Look {angle}", (20, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.putText(frame, "Press SPACE to Capture", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 255, 255), 1)

                    cv2.imshow("Admin Face Setup", frame)
                    key = cv2.waitKey(1)
                    if key == 32:  # Space
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        boxes = face_recognition.face_locations(rgb)
                        if boxes:
                            encs = face_recognition.face_encodings(rgb, boxes)
                            if encs:
                                captured_encodings.append(encs[0].tolist())
                                captured = True
                                cv2.rectangle(frame, (0, 0), (640, 480), (0, 255, 0), 20)
                                cv2.imshow("Admin Face Setup", frame)
                                cv2.waitKey(500)
                    if key == 27:  # ESC
                        cap.release()
                        cv2.destroyAllWindows()
                        self.root.deiconify()
                        return

            # Simple auth check before sending
            admin_pass = simpledialog.askstring("Auth", "Enter ADMIN password to confirm:", show="*", parent=self.root)
            self.net.send_request("UPDATE_FACE", {
                "username": user['username'],
                "password": admin_pass,
                "face_data": captured_encodings
            })
            messagebox.showinfo("Info", "Request sent.")

        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.root.attributes('-topmost', True)

    def validate_time_input(self, P):
        """
        Callback for Entry widget validation.
        P is the text that WOULD be in the box if the change is accepted.
        """
        # Allow empty box (so they can delete everything)
        if P == "": return True
        # Allow just a minus sign (so they can start typing a negative number)
        if P == "-": return True

        # For everything else, it must be a valid integer
        try:
            int(P)
            return True
        except ValueError:
            return False

    def on_select(self, event):
        pass

    def close(self):
        self.root.destroy()

