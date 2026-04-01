import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import cv2
import face_recognition
from settings_window import SettingsWindow


class AdminPanel:
    def __init__(self, network_client, admin_username):
        self.net = network_client
        self.admin_username = admin_username
        self.root = None
        self.listbox = None

        # Data Caches
        self.users_cache = []
        self.dashboard_users_data = []
        self.dashboard_stations_data = []

        # State
        self.current_user_filter = "Show All"
        self._poll_timer = None

    def show(self):
        self.root = tk.Tk()

        # --- KIOSK MODE SETUP ---
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg="#2c3e50")

        # --- STYLING (For ttk components) ---
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#2c3e50", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Arial", 12, "bold"), padding=[15, 5], background="#34495e",
                        foreground="white")
        style.map("TNotebook.Tab", background=[("selected", "#2980b9")])

        style.configure("Treeview", font=("Arial", 12), rowheight=30, background="#ecf0f1", fieldbackground="#ecf0f1")
        style.configure("Treeview.Heading", font=("Arial", 13, "bold"), background="#bdc3c7")

        # --- TOP CONTROL BAR (Header) ---
        top_bar = tk.Frame(self.root, bg="#34495e", height=60)
        top_bar.pack(side="top", fill="x")
        top_bar.pack_propagate(False) # Prevent shrinking

        # Title (Left) - CHANGED: Saved to self.lbl_title so it can update dynamically
        self.lbl_title = tk.Label(top_bar, text=f"🔧 ADMIN PANEL | {self.admin_username}",
                                  font=("Arial", 18, "bold"), bg="#34495e", fg="#ecf0f1")
        self.lbl_title.pack(side="left", padx=20)

        # Logout Button (Right)
        tk.Button(top_bar, text="LOGOUT", command=self.close,
                  font=("Arial", 12, "bold"), bg="#c0392b", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # Minimize Button (Right)
        tk.Button(top_bar, text="_ Minimize", command=self.minimize_window,
                  font=("Arial", 12, "bold"), bg="#7f8c8d", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # Settings Button
        tk.Button(top_bar, text="⚙ Settings", command=self.open_admin_settings,
                  font=("Arial", 12, "bold"), bg="#f39c12", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # --- MAIN CONTENT (Tabs) ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)

        # Create Tab Frames
        self.tab_users_overview = tk.Frame(self.notebook, bg="#2c3e50")
        self.tab_stations_overview = tk.Frame(self.notebook, bg="#2c3e50")
        self.tab_management = tk.Frame(self.notebook, bg="#2c3e50")

        self.notebook.add(self.tab_users_overview, text="Users Overview")
        self.notebook.add(self.tab_stations_overview, text="Stations Overview")
        self.notebook.add(self.tab_management, text="User Management")

        self._build_users_overview_tab()
        self._build_stations_overview_tab()
        self._build_management_tab()

        # Initial Load & Start Polling
        self.fetch_users()
        self.poll_dashboard_data()
        self.root.mainloop()

    # ==========================================
    # UI BUILDERS
    # ==========================================
    def _build_users_overview_tab(self):
        # Filter Frame
        filter_frame = tk.Frame(self.tab_users_overview, bg="#2c3e50")
        filter_frame.pack(fill="x", pady=10)

        tk.Label(filter_frame, text="Filter:", font=("Arial", 14, "bold"), bg="#2c3e50", fg="white").pack(side="left",
                                                                                                          padx=10)

        filters = ["Show All", "Show Only Online", "Show Only Offline"]
        self.filter_var = tk.StringVar(value=filters[0])

        for f in filters:
            tk.Radiobutton(filter_frame, text=f, variable=self.filter_var, value=f,
                           command=self._apply_user_filter, font=("Arial", 12),
                           bg="#2c3e50", fg="white", selectcolor="#34495e").pack(side="left", padx=10)

        # Treeview
        cols = ("Username", "Connected Station", "Status", "Time Left")
        self.tree_users = ttk.Treeview(self.tab_users_overview, columns=cols, show="headings")

        for col in cols:
            self.tree_users.heading(col, text=col)
            self.tree_users.column(col, anchor="center")

        self.tree_users.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_stations_overview_tab(self):
        # Actions Frame
        actions_frame = tk.Frame(self.tab_stations_overview, bg="#2c3e50")
        actions_frame.pack(fill="x", pady=10)

        tk.Button(actions_frame, text="❌ Delete Selected Station", command=self.delete_station,
                  font=("Arial", 12, "bold"), bg="#c0392b", fg="white").pack(side="left", padx=10)

        # Treeview
        cols = ("Station ID", "Status", "Current User")
        self.tree_stations = ttk.Treeview(self.tab_stations_overview, columns=cols, show="headings")

        for col in cols:
            self.tree_stations.heading(col, text=col)
            self.tree_stations.column(col, anchor="center")

        self.tree_stations.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_management_tab(self):
        # LEFT: User List
        left_frame = tk.Frame(self.tab_management, bg="#34495e", width=400)
        left_frame.pack(side="left", fill="y", padx=20, pady=20)

        tk.Label(left_frame, text="User Database", font=("Arial", 14, "bold"), bg="#34495e", fg="white").pack(pady=10)

        self.listbox = tk.Listbox(left_frame, font=("Arial", 14), width=30, height=20)
        self.listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        tk.Button(left_frame, text="Refresh List", command=self.fetch_users, bg="#7f8c8d", fg="white").pack(pady=10,
                                                                                                            fill="x")

        # RIGHT: Actions
        right_frame = tk.Frame(self.tab_management, bg="#2c3e50")
        right_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        tk.Label(right_frame, text="Management Actions", font=("Arial", 16, "bold"), bg="#2c3e50", fg="white").pack(
            pady=10)

        self.btn_create = tk.Button(right_frame, text="➕ Create New User", command=self.create_user, font=("Arial", 12),
                                    bg="#27ae60", fg="white", width=30)
        self.btn_create.pack(pady=8)

        self.btn_delete = tk.Button(right_frame, text="❌ Delete Selected", command=self.delete_user, font=("Arial", 12),
                                    bg="#c0392b", fg="white", width=30)
        self.btn_delete.pack(pady=8)

        tk.Label(right_frame, text="--- Edit Selected ---", bg="#2c3e50", fg="#95a5a6").pack(pady=15)

        self.btn_time = tk.Button(right_frame, text="⏳ Add/Remove Time", command=self.manage_time, font=("Arial", 12),
                                  bg="#2980b9", fg="white", width=30)
        self.btn_time.pack(pady=8)

        self.btn_face = tk.Button(right_frame, text="📸 Recapture Face ID", command=self.recapture_face,
                                  font=("Arial", 12), bg="#e67e22", fg="white", width=30)
        self.btn_face.pack(pady=8)

        self.btn_edit_profile = tk.Button(right_frame, text="📝 Edit Details", command=self.edit_details,
                                          font=("Arial", 12), bg="#8e44ad", fg="white", width=30)
        self.btn_edit_profile.pack(pady=8)

    # ==========================================
    # DASHBOARD LOGIC (REAL-TIME POLLING)
    # ==========================================
    def poll_dashboard_data(self):
        """Fetches live data from the server every 5 seconds securely on the main thread."""
        try:
            # 1. Fetch Data
            users_resp = self.net.send_request("FETCH_ALL_USERS", {})
            stations_resp = self.net.send_request("FETCH_STATIONS", {})  # Ensure your server supports this endpoint

            if users_resp and users_resp.get("status") == "SUCCESS":
                self.dashboard_users_data = users_resp.get("users", [])

            if stations_resp and stations_resp.get("status") == "SUCCESS":
                self.dashboard_stations_data = stations_resp.get("stations", [])

            # 2. Update UIs
            self._update_users_tree()
            self._update_stations_tree()

        except Exception as e:
            print(f"Dashboard Polling Error: {e}")

        # 3. Schedule next poll in 5000ms (5 seconds)
        self._poll_timer = self.root.after(5000, self.poll_dashboard_data)

    def _apply_user_filter(self):
        self.current_user_filter = self.filter_var.get()
        self._update_users_tree()

    def _update_users_tree(self):
        # Clear existing
        for item in self.tree_users.get_children():
            self.tree_users.delete(item)

        # Sort Alphabetically by username
        sorted_users = sorted(self.dashboard_users_data, key=lambda x: x.get('username', '').lower())

        for u in sorted_users:
            # Note: Ensure your server provides 'status' and 'connected_station' fields!
            # If a user isn't connected to a station, default them to 'Offline'
            status = u.get('status', 'Offline')

            # Apply Filtering
            if self.current_user_filter == "Show Only Online" and status == "Offline":
                continue
            if self.current_user_filter == "Show Only Offline" and status != "Offline":
                continue

            self.tree_users.insert("", tk.END, values=(
                u.get('username', 'Unknown'),
                u.get('connected_station', 'None'),
                status,
                f"{float(u.get('time_balance', 0)):.1f} mins"
            ))

    def _update_stations_tree(self):
        for item in self.tree_stations.get_children():
            self.tree_stations.delete(item)

        for s in self.dashboard_stations_data:
            self.tree_stations.insert("", tk.END, values=(
                s.get('station_id', 'Unknown'),
                s.get('status', 'Offline'),
                s.get('current_user', 'None')
            ))

    def delete_station(self):
        selected = self.tree_stations.selection()
        if not selected:
            messagebox.showwarning("Selection", "Please select a station to delete.")
            return

        item = self.tree_stations.item(selected[0])
        station_id, status, current_user = item['values']

        # Protection Logic
        if status in ['In Use', 'Paused']:
            messagebox.showerror("Error",
                                 "Cannot delete a station while it is in use or paused. Please wait for the user to log out.",
                                 parent=self.root)
            return

        confirm = messagebox.askyesno("Confirm Deletion",
                                      f"Are you sure you want to delete Station '{station_id}'?\nThis will execute the kill switch.",
                                      parent=self.root)
        if confirm:
            # Trigger server-side deletion / kill switch
            response = self.net.send_request("DELETE_STATION", {"station_id": station_id})
            if response and response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", f"Station {station_id} deleted successfully.", parent=self.root)
                self.poll_dashboard_data()  # Force immediate refresh
            else:
                messagebox.showerror("Error", f"Failed to delete station: {response.get('message', 'Unknown Error')}",
                                     parent=self.root)

    # ==========================================
    # EXISTING USER MANAGEMENT LOGIC
    # ==========================================
    # --- Minimize Logic ---
    def minimize_window(self):
        self.root.attributes('-topmost', False)
        self.root.iconify()
        self.root.bind("<Map>", self.restore_topmost)

    def open_admin_settings(self):
        self.root.attributes('-topmost', False)
        settings = SettingsWindow(self.net, self.admin_username, self.root, role="root")
        new_username = settings.show()
        if new_username and new_username != self.admin_username:
            self.admin_username = new_username
            self.lbl_title.config(text=f"🔧 ADMIN PANEL | {self.admin_username}")
        self.root.attributes('-topmost', True)

    def restore_topmost(self, event):
        if self.root.state() == 'normal':
            self.root.attributes('-topmost', True)
            self.root.attributes('-fullscreen', True)
            self.root.unbind("<Map>")

    def fetch_users(self):
        self.listbox.delete(0, tk.END)
        response = self.net.send_request("FETCH_ALL_USERS", {})
        if response and response.get("status") == "SUCCESS":
            all_users = response.get("users", [])
            self.users_cache = []
            for u in all_users:
                if u['username'] == self.admin_username: continue
                self.users_cache.append(u)
                display = f"{u['username']} | {u['role']} | {u['time_balance']}m"
                self.listbox.insert(tk.END, display)

    def get_selected_user(self):
        idx = self.listbox.curselection()
        if not idx:
            messagebox.showwarning("Selection", "Please select a user first.")
            return None
        return self.users_cache[idx[0]]

    def create_user(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create New User")
        dialog.geometry("350x450")
        dialog.configure(bg="#34495e")
        dialog.attributes('-topmost', True)

        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 225
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="Create New User", font=("Arial", 16, "bold"), bg="#34495e", fg="white").pack(pady=15)

        username_var = tk.StringVar()
        fullname_var = tk.StringVar()
        password_var = tk.StringVar()
        role_var = tk.StringVar(value="user")

        def on_role_change(*args):
            if role_var.get() == "user":
                entry_pass.config(state="disabled")
                password_var.set("")
            else:
                entry_pass.config(state="normal")

        role_var.trace_add("write", on_role_change)

        tk.Label(dialog, text="Role:", bg="#34495e", fg="#bdc3c7").pack(anchor="w", padx=30)
        role_frame = tk.Frame(dialog, bg="#34495e")
        role_frame.pack(fill="x", padx=30, pady=5)
        tk.Radiobutton(role_frame, text="Standard User", variable=role_var, value="user", bg="#34495e", fg="white",
                       selectcolor="#2c3e50").pack(side="left")
        tk.Radiobutton(role_frame, text="Admin (Root)", variable=role_var, value="root", bg="#34495e", fg="white",
                       selectcolor="#2c3e50").pack(side="right")

        tk.Label(dialog, text="Username:", bg="#34495e", fg="#bdc3c7").pack(anchor="w", padx=30, pady=(10, 0))
        tk.Entry(dialog, textvariable=username_var, font=("Arial", 12)).pack(fill="x", padx=30, pady=5)

        tk.Label(dialog, text="Full Name:", bg="#34495e", fg="#bdc3c7").pack(anchor="w", padx=30)
        tk.Entry(dialog, textvariable=fullname_var, font=("Arial", 12)).pack(fill="x", padx=30, pady=5)

        tk.Label(dialog, text="Password (Admins Only):", bg="#34495e", fg="#bdc3c7").pack(anchor="w", padx=30)
        entry_pass = tk.Entry(dialog, textvariable=password_var, font=("Arial", 12), state="disabled", show="*")
        entry_pass.pack(fill="x", padx=30, pady=5)

        def submit():
            user = username_var.get().strip()
            full = fullname_var.get().strip()
            pwd = password_var.get().strip()
            rle = role_var.get()

            if not user or not full:
                messagebox.showerror("Error", "Username and Full Name are required.", parent=dialog)
                return
            if rle == "root" and not pwd:
                messagebox.showerror("Error", "Admin accounts require a password.", parent=dialog)
                return

            response = self.net.send_request("CREATE_USER", {
                "username": user, "password": pwd, "full_name": full, "role": rle
            })

            if response and response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", f"User '{user}' Created!", parent=self.root)
                self.fetch_users()
                dialog.destroy()
            else:
                messagebox.showerror("Error", response.get("message", "Unknown error"), parent=dialog)

        tk.Button(dialog, text="Create Account", command=submit, bg="#27ae60", fg="white",
                  font=("Arial", 11, "bold")).pack(pady=20)

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

        dialog = tk.Toplevel(self.root)
        dialog.title("Adjust Time")
        dialog.geometry("350x200")
        dialog.configure(bg="#34495e")
        dialog.attributes('-topmost', True)

        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 100
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text=f"Adjust Balance: {user['username']}", font=("Arial", 12, "bold"), bg="#34495e",
                 fg="white").pack(pady=(20, 2))
        tk.Label(dialog, text=f"Current: {user['time_balance']} mins", font=("Arial", 10), bg="#34495e",
                 fg="#bdc3c7").pack(pady=2)
        tk.Label(dialog, text="Enter minutes (+ or -):", font=("Arial", 10), bg="#34495e", fg="white").pack(pady=2)

        vcmd = (dialog.register(self.validate_time_input), '%P')
        entry = tk.Entry(dialog, font=("Arial", 14), justify='center', validate="key", validatecommand=vcmd)
        entry.pack(pady=8, padx=20, ipadx=5, ipady=3)
        entry.focus_set()

        self.time_input_value = None

        def on_submit(event=None):
            val = entry.get()
            if val in ("", "-"):
                dialog.destroy()
                return
            self.time_input_value = int(val)
            dialog.destroy()

        tk.Button(dialog, text="Update Balance", command=on_submit, bg="#27ae60", fg="white",
                  font=("Arial", 11, "bold")).pack(pady=8)
        dialog.bind('<Return>', on_submit)
        self.root.wait_window(dialog)

        if self.time_input_value is not None:
            self.net.send_request("ADD_TIME", {"username": user['username'], "minutes": self.time_input_value})
            self.fetch_users()
            messagebox.showinfo("Success", "Time balance updated.", parent=self.root)

    def edit_details(self):
        user = self.get_selected_user()
        if not user: return

        allowed_fields = ['full_name', 'username', 'role']
        if user['role'] == 'root':
            allowed_fields.append('password')

        fields_str = ", ".join([f"'{f}'" for f in allowed_fields])
        choice = simpledialog.askstring("Edit", f"Type field to edit: {fields_str}", parent=self.root)

        if not choice: return
        choice = choice.lower().strip()

        if choice not in allowed_fields:
            if choice == 'password':
                messagebox.showerror("Error", "Standard users are Biometric-Only and do not use passwords.",
                                     parent=self.root)
            else:
                messagebox.showerror("Error", "Invalid field name.", parent=self.root)
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
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        captured_encodings = []
        angles = ["Center", "Left", "Right", "Up", "Down"]
        capture_successful = False

        try:
            for angle in angles:
                captured = False
                while not captured:
                    ret, frame = cap.read()
                    if not ret: break

                    cv2.putText(frame, f"User: {user['username']}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (255, 255, 255), 1)
                    cv2.putText(frame, f"Look: {angle}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)
                    cv2.putText(frame, "Press [SPACE] to Capture", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (200, 200, 200), 1)
                    cv2.putText(frame, "Press ESC to cancel", (20, 475), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                    cv2.imshow("Admin Face Setup", frame)
                    key = cv2.waitKey(1)

                    if key == 32:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        boxes = face_recognition.face_locations(rgb)
                        if boxes:
                            encs = face_recognition.face_encodings(rgb, boxes)
                            if encs:
                                captured_encodings.append(encs[0].tolist())
                                captured = True
                                cv2.rectangle(frame, (0, 0), (640, 480), (0, 255, 0), 20)
                                cv2.imshow("Admin Face Setup", frame)
                                cv2.waitKey(300)

                    if key == 27:
                        print("Capture Cancelled.")
                        return

            capture_successful = True

        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.root.attributes('-topmost', True)

        if capture_successful:
            admin_pass = simpledialog.askstring("Security Check",
                                                f"Enter password for admin '{self.admin_username}' to authorize:",
                                                show="*", parent=self.root)
            if not admin_pass: return

            response = self.net.send_request("UPDATE_FACE", {
                "username": user['username'],
                "password": admin_pass,
                "face_data": captured_encodings,
                "requester_username": self.admin_username
            })

            if response and response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", f"✅ Face ID updated for {user['username']}", parent=self.root)
            else:
                error_msg = response.get("message", "Unknown Error") if response else "No Server Response"
                messagebox.showerror("Failed", f"❌ Update Denied.\nReason: {error_msg}", parent=self.root)

    def validate_time_input(self, P):
        if P in ("", "-"): return True
        try:
            int(P)
            return True
        except ValueError:
            return False

    def on_select(self, event):
        pass

    def close(self):
        # Prevent memory leaks by canceling the polling timer before destroying the window
        if self._poll_timer is not None:
            self.root.after_cancel(self._poll_timer)
        self.root.destroy()