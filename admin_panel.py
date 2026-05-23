import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import cv2
import face_recognition
from settings_window import SettingsWindow


class AdminPanel:
    """
    Top-level administrator interface. Provides four tabs: Users Overview,
    Stations Overview, User Management, and Usage History. Polls the
    server every five seconds for live dashboard data and supports user
    CRUD, time-balance adjustments, face-ID recapture, and audit reports.
    """

    def __init__(self, network_client, admin_username):
        self.net = network_client
        self.admin_username = admin_username
        self.root = None
        self.listbox = None

        # Data caches populated by the polling loop.
        self.users_cache = []
        self.dashboard_users_data = []
        self.dashboard_stations_data = []

        # UI state
        self.current_user_filter = "Show All"
        self._poll_timer = None
        self.privacy_screen_on = False  # Cached value of the privacy_screen setting.

        # Tracks which Usage History view is currently active.
        self.audit_mode = "user_audit"  # "user_audit" | "station_overview" | "user_overview"

    def show(self):
        """Builds the admin window and enters the Tk event loop."""
        self.root = tk.Tk()

        # Kiosk-mode window.
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg="#2c3e50")

        # ttk styling — applied to Treeviews, Notebook tabs, and Frames.
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#2c3e50", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Arial", 12, "bold"), padding=[15, 5], background="#34495e",
                        foreground="white")
        style.map("TNotebook.Tab", background=[("selected", "#2980b9")])

        style.configure("Treeview", font=("Arial", 12), rowheight=30, background="#ecf0f1", fieldbackground="#ecf0f1")
        style.configure("Treeview.Heading", font=("Arial", 13, "bold"), background="#bdc3c7")

        style.configure("Audit.TFrame", background="#2c3e50")

        # Top control bar — header with admin name and global action buttons.
        top_bar = tk.Frame(self.root, bg="#34495e", height=60)
        top_bar.pack(side="top", fill="x")
        top_bar.pack_propagate(False)

        self.lbl_title = tk.Label(top_bar, text=f"🔧 ADMIN PANEL | {self.admin_username}",
                                  font=("Arial", 18, "bold"), bg="#34495e", fg="#ecf0f1")
        self.lbl_title.pack(side="left", padx=20)

        tk.Button(top_bar, text="LOGOUT", command=self.close,
                  font=("Arial", 12, "bold"), bg="#c0392b", fg="white", width=10).pack(side="right", padx=10, pady=10)

        tk.Button(top_bar, text="_ Minimize", command=self.minimize_window,
                  font=("Arial", 12, "bold"), bg="#7f8c8d", fg="white", width=10).pack(side="right", padx=10, pady=10)

        tk.Button(top_bar, text="⚙ Settings", command=self.open_admin_settings,
                  font=("Arial", 12, "bold"), bg="#f39c12", fg="white", width=10).pack(side="right", padx=10, pady=10)

        # Privacy-screen toggle — its label is updated by _update_privacy_btn.
        self.btn_privacy = tk.Button(
            top_bar, text="🔒 Privacy: OFF",
            command=self._toggle_privacy_screen,
            font=("Arial", 12, "bold"), bg="#7f8c8d", fg="white", width=14
        )
        self.btn_privacy.pack(side="right", padx=10, pady=10)

        # Main content area: a Notebook holding the four primary tabs.
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)

        # Construct the tab frames.
        self.tab_users_overview   = tk.Frame(self.notebook, bg="#2c3e50")
        self.tab_stations_overview = tk.Frame(self.notebook, bg="#2c3e50")
        self.tab_management       = tk.Frame(self.notebook, bg="#2c3e50")
        self.tab_history          = tk.Frame(self.notebook, bg="#2c3e50")

        self.notebook.add(self.tab_users_overview,   text="Users Overview")
        self.notebook.add(self.tab_stations_overview, text="Stations Overview")
        self.notebook.add(self.tab_management,        text="User Management")
        self.notebook.add(self.tab_history,           text="Usage History")

        self._build_users_overview_tab()
        self._build_stations_overview_tab()
        self._build_management_tab()
        self._build_history_tab()

        # Kick off initial data load and start the polling loop.
        self.fetch_users()
        self.poll_dashboard_data()

        # Defer the first audit load until after the window has been drawn.
        self.root.after(100, self._load_current_view)

        # Sync the privacy toggle's visual state with the server's setting.
        self.root.after(150, self._fetch_privacy_setting)

        self.root.mainloop()

    # ==========================================
    # UI BUILDERS
    # ==========================================
    def _build_users_overview_tab(self):
        """Builds the Users Overview tab — filterable Treeview of all users."""
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

        cols = ("Username", "Connected Station", "Status", "Time Left")
        self.tree_users = ttk.Treeview(self.tab_users_overview, columns=cols, show="headings")

        for col in cols:
            self.tree_users.heading(col, text=col)
            self.tree_users.column(col, anchor="center")

        self.tree_users.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_stations_overview_tab(self):
        """Builds the Stations Overview tab — list of stations with a delete action."""
        actions_frame = tk.Frame(self.tab_stations_overview, bg="#2c3e50")
        actions_frame.pack(fill="x", pady=10)

        tk.Button(actions_frame, text="❌ Delete Selected Station", command=self.delete_station,
                  font=("Arial", 12, "bold"), bg="#c0392b", fg="white").pack(side="left", padx=10)

        cols = ("Station ID", "Status", "Current User")
        self.tree_stations = ttk.Treeview(self.tab_stations_overview, columns=cols, show="headings")

        for col in cols:
            self.tree_stations.heading(col, text=col)
            self.tree_stations.column(col, anchor="center")

        self.tree_stations.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_management_tab(self):
        """Builds the User Management tab — user list on the left, actions on the right."""
        left_frame = tk.Frame(self.tab_management, bg="#34495e", width=400)
        left_frame.pack(side="left", fill="y", padx=20, pady=20)

        tk.Label(left_frame, text="User Database", font=("Arial", 14, "bold"), bg="#34495e", fg="white").pack(pady=10)

        # Pack the Refresh button first so it always reserves space at the
        # bottom. If the listbox were packed first with expand=True it would
        # absorb all available height and push this button out of view.
        tk.Button(left_frame, text="Refresh List", command=self.fetch_users,
                  bg="#7f8c8d", fg="white").pack(side="bottom", pady=10, fill="x")

        self.listbox = tk.Listbox(left_frame, font=("Arial", 14), width=30, height=20)
        self.listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

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

    def _build_history_tab(self):
        """Builds the Usage History tab with three switchable views."""

        # Top row: view-toggle buttons plus Refresh and Clear actions.
        control_frame = tk.Frame(self.tab_history, bg="#2c3e50")
        control_frame.pack(fill="x", padx=20, pady=(15, 5))

        tk.Label(control_frame, text="View:", font=("Arial", 13, "bold"),
                 bg="#2c3e50", fg="white").pack(side="left", padx=(0, 10))

        # Three mutually exclusive toggle buttons. The active one renders
        # sunken/blue; the inactive ones render raised/grey.
        self._btn_user_audit = tk.Button(
            control_frame, text="👥 User Audit",
            command=self._switch_to_user_audit,
            font=("Arial", 12, "bold"), width=14,
            bg="#2980b9", fg="white", relief="sunken")   # Starts active.
        self._btn_user_audit.pack(side="left", padx=5)

        self._btn_station_overview = tk.Button(
            control_frame, text="🖥️ Station Overview",
            command=self._switch_to_station_overview,
            font=("Arial", 12, "bold"), width=18,
            bg="#34495e", fg="white", relief="raised")
        self._btn_station_overview.pack(side="left", padx=5)

        self._btn_user_overview = tk.Button(
            control_frame, text="👤 User Overview",
            command=self._switch_to_user_overview,
            font=("Arial", 12, "bold"), width=15,
            bg="#34495e", fg="white", relief="raised")
        self._btn_user_overview.pack(side="left", padx=5)

        tk.Button(control_frame, text="🔄 Refresh", command=self._refresh_audit,
                  font=("Arial", 12), bg="#27ae60", fg="white", width=10).pack(side="left", padx=20)

        tk.Button(control_frame, text="🗑️ Clear History", command=self._clear_audit,
                  font=("Arial", 12), bg="#c0392b", fg="white", width=14).pack(side="left", padx=5)

        self.lbl_audit_status = tk.Label(control_frame, text="", font=("Arial", 11, "italic"),
                                         bg="#2c3e50", fg="#bdc3c7")
        self.lbl_audit_status.pack(side="left", padx=10)

        # Content area holds two frames; only one is visible at a time.
        # Frame A — raw audit log rendered into a monospaced Listbox.
        self._frame_audit = tk.Frame(self.tab_history, bg="#2c3e50")
        self._frame_audit.pack(fill="both", expand=True, padx=20, pady=(5, 20))

        scrollbar_a = tk.Scrollbar(self._frame_audit, orient="vertical")
        self.audit_listbox = tk.Listbox(
            self._frame_audit,
            font=("Courier", 12),
            bg="#1e272e", fg="#dfe6e9",
            selectbackground="#2980b9",
            activestyle="none",
            yscrollcommand=scrollbar_a.set,
            borderwidth=0, highlightthickness=0
        )
        scrollbar_a.config(command=self.audit_listbox.yview)
        scrollbar_a.pack(side="right", fill="y")
        self.audit_listbox.pack(side="left", fill="both", expand=True)

        # Frame B — Treeview shared by Station Overview and User Overview.
        # Not packed yet; it stays hidden until an overview mode is selected.
        self._frame_overview = tk.Frame(self.tab_history, bg="#2c3e50")

        self.overview_tree = ttk.Treeview(self._frame_overview, show="headings")
        scrollbar_b = tk.Scrollbar(self._frame_overview, orient="vertical",
                                   command=self.overview_tree.yview)
        self.overview_tree.configure(yscrollcommand=scrollbar_b.set)
        scrollbar_b.pack(side="right", fill="y")
        self.overview_tree.pack(fill="both", expand=True)

    # ==========================================
    # AUDIT / HISTORY LOGIC
    # ==========================================

    @staticmethod
    def _format_duration(total_seconds):
        """Converts a raw second count into a human-readable string (e.g. '2h 15m 30s')."""
        if not total_seconds or total_seconds <= 0:
            return "0s"
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        elif m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def _set_active_toggle(self, active_btn):
        """Updates the toggle buttons so only active_btn appears pressed."""
        all_btns = [self._btn_user_audit, self._btn_station_overview, self._btn_user_overview]
        for btn in all_btns:
            if btn is active_btn:
                btn.config(bg="#2980b9", relief="sunken")
            else:
                btn.config(bg="#34495e", relief="raised")

    def _show_audit_frame(self):
        """Swaps the content area to show the raw audit Listbox."""
        self._frame_overview.pack_forget()
        self._frame_audit.pack(fill="both", expand=True, padx=20, pady=(5, 20))

    def _show_overview_frame(self):
        """Swaps the content area to show the Overview Treeview."""
        self._frame_audit.pack_forget()
        self._frame_overview.pack(fill="both", expand=True, padx=20, pady=(5, 20))

    def _switch_to_user_audit(self):
        """Switches the Usage History view to the User Audit log."""
        self.audit_mode = "user_audit"
        self._set_active_toggle(self._btn_user_audit)
        self._show_audit_frame()
        self.root.after(0, self._load_current_view)

    def _switch_to_station_overview(self):
        """Switches the Usage History view to the Station Overview report."""
        self.audit_mode = "station_overview"
        self._set_active_toggle(self._btn_station_overview)
        self._show_overview_frame()
        # Configure the Treeview columns for Station Overview.
        self.overview_tree.config(columns=("Station ID", "Total Online Time"))
        for col, anchor, width in [("Station ID", "center", 200), ("Total Online Time", "center", 250)]:
            self.overview_tree.heading(col, text=col)
            self.overview_tree.column(col, anchor=anchor, width=width)
        self.root.after(0, self._load_current_view)

    def _switch_to_user_overview(self):
        """Switches the Usage History view to the User Overview report."""
        self.audit_mode = "user_overview"
        self._set_active_toggle(self._btn_user_overview)
        self._show_overview_frame()
        # Configure the Treeview columns for User Overview.
        self.overview_tree.config(columns=("Username", "Total Usage Time"))
        for col, anchor, width in [("Username", "center", 200), ("Total Usage Time", "center", 250)]:
            self.overview_tree.heading(col, text=col)
            self.overview_tree.column(col, anchor=anchor, width=width)
        self.root.after(0, self._load_current_view)

    def _refresh_audit(self):
        """Manual refresh — deferred via root.after() for Tk thread safety."""
        self.lbl_audit_status.config(text="Loading…")
        self.root.after(0, self._load_current_view)

    def _load_current_view(self):
        """Dispatcher that loads data for whichever Usage History mode is active."""
        if self.audit_mode == "user_audit":
            self._load_audit_data()
        else:
            self._load_overview_data()

    def _load_audit_data(self):
        """Populates the Listbox with raw user-audit records."""
        self.audit_listbox.delete(0, tk.END)
        try:
            response = self.net.send_request("FETCH_USER_AUDIT", {})
            if response and response.get("status") == "SUCCESS":
                records = response.get("records", [])
                for rec in records:
                    line = (f"{rec.get('username', '?'):<20} "
                            f"{rec.get('action', '?'):<6} "
                            f"on {rec.get('station_id', '?'):<12} "
                            f"at {rec.get('timestamp', '?')}")
                    self.audit_listbox.insert(tk.END, line)
                self.lbl_audit_status.config(text=f"{len(records)} record(s)")
            else:
                self.lbl_audit_status.config(text="Failed to load.")
        except Exception as e:
            print(f"Audit Load Error: {e}")
            self.lbl_audit_status.config(text="Error loading audit data.")

    def _load_overview_data(self):
        """Populates the Treeview with either the Station or User overview records."""
        for row in self.overview_tree.get_children():
            self.overview_tree.delete(row)
        try:
            if self.audit_mode == "station_overview":
                response = self.net.send_request("FETCH_STATION_OVERVIEW", {})
                if response and response.get("status") == "SUCCESS":
                    records = response.get("records", [])
                    for rec in records:
                        duration = self._format_duration(rec.get("total_seconds", 0))
                        self.overview_tree.insert("", tk.END, values=(
                            rec.get("station_id", "?"),
                            duration
                        ))
                    self.lbl_audit_status.config(text=f"{len(records)} station(s)")
                else:
                    self.lbl_audit_status.config(text="Failed to load.")

            else:  # user_overview
                response = self.net.send_request("FETCH_USER_OVERVIEW", {})
                if response and response.get("status") == "SUCCESS":
                    records = response.get("records", [])
                    for rec in records:
                        duration = self._format_duration(rec.get("total_seconds", 0))
                        self.overview_tree.insert("", tk.END, values=(
                            rec.get("username", "?"),
                            duration
                        ))
                    self.lbl_audit_status.config(text=f"{len(records)} user(s)")
                else:
                    self.lbl_audit_status.config(text="Failed to load.")
        except Exception as e:
            print(f"Overview Load Error: {e}")
            self.lbl_audit_status.config(text="Error loading data.")

    def _clear_audit(self):
        """Permanently clears the audit table backing the currently active view."""
        mode_map = {
            "user_audit":        ("User Audit",        "CLEAR_USER_AUDIT"),
            "station_overview":  ("Station Overview",  "CLEAR_STATION_AUDIT"),
            "user_overview":     ("User Overview",     "CLEAR_USER_AUDIT"),
        }
        label, action = mode_map.get(self.audit_mode, ("", ""))
        if not action:
            return

        msg = "Are you sure you want to permanently delete all " + label + " records?\nThis cannot be undone."
        confirm = messagebox.askyesno("Clear History", msg, parent=self.root)
        if not confirm:
            return

        response = self.net.send_request(action, {})
        if response and response.get("status") == "SUCCESS":
            self.root.after(0, self._load_current_view)
        else:
            messagebox.showerror("Error", "Failed to clear audit log.", parent=self.root)


    # ==========================================
    # PRIVACY SCREEN SETTING
    # ==========================================

    def _fetch_privacy_setting(self):
        """Reads the current privacy_screen value from the server and syncs the toggle button."""
        try:
            response = self.net.send_request("GET_SETTING", {"key": "privacy_screen"})
            if response and response.get("status") == "SUCCESS":
                self.privacy_screen_on = (response.get("value") == "1")
                self._update_privacy_btn()
        except Exception as e:
            print(f"Privacy fetch error: {e}")

    def _toggle_privacy_screen(self):
        """Flips the privacy_screen setting on the server and updates the button."""
        new_value = "0" if self.privacy_screen_on else "1"
        response = self.net.send_request("SET_SETTING", {"key": "privacy_screen", "value": new_value})
        if response and response.get("status") == "SUCCESS":
            self.privacy_screen_on = (new_value == "1")
            self._update_privacy_btn()
        else:
            messagebox.showerror("Error", "Failed to update privacy screen setting.", parent=self.root)

    def _update_privacy_btn(self):
        """Refreshes the privacy toggle button's text and colour to match current state."""
        if self.privacy_screen_on:
            self.btn_privacy.config(text="🔒 Privacy: ON",  bg="#27ae60")
        else:
            self.btn_privacy.config(text="🔒 Privacy: OFF", bg="#7f8c8d")

    # ==========================================
    # DASHBOARD LOGIC (REAL-TIME POLLING)
    # ==========================================
    def poll_dashboard_data(self):
        """Fetches live dashboard data from the server every five seconds on the main thread."""
        try:
            users_resp    = self.net.send_request("FETCH_ALL_USERS", {})
            stations_resp = self.net.send_request("FETCH_STATIONS", {})

            if users_resp and users_resp.get("status") == "SUCCESS":
                self.dashboard_users_data = users_resp.get("users", [])

            if stations_resp and stations_resp.get("status") == "SUCCESS":
                self.dashboard_stations_data = stations_resp.get("stations", [])

            self._update_users_tree()
            self._update_stations_tree()

        except Exception as e:
            print(f"Dashboard Polling Error: {e}")

        self._poll_timer = self.root.after(5000, self.poll_dashboard_data)

    def _apply_user_filter(self):
        """Re-renders the users tree with the currently selected filter applied."""
        self.current_user_filter = self.filter_var.get()
        self._update_users_tree()

    def _update_users_tree(self):
        """Re-populates the Users Overview Treeview from the cached data."""
        for item in self.tree_users.get_children():
            self.tree_users.delete(item)

        sorted_users = sorted(self.dashboard_users_data, key=lambda x: x.get('username', '').lower())

        for u in sorted_users:
            status = u.get('status', 'Offline')

            # Apply the radio-button filter before inserting the row.
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
        """Re-populates the Stations Overview Treeview from the cached data."""
        for item in self.tree_stations.get_children():
            self.tree_stations.delete(item)

        for s in self.dashboard_stations_data:
            self.tree_stations.insert("", tk.END, values=(
                s.get('station_id', 'Unknown'),
                s.get('status', 'Offline'),
                s.get('current_user', 'None')
            ))

    def delete_station(self):
        """Deletes the selected station via the kill-switch action."""
        selected = self.tree_stations.selection()
        if not selected:
            messagebox.showwarning("Selection", "Please select a station to delete.")
            return

        item = self.tree_stations.item(selected[0])
        station_id, status, current_user = item['values']

        # Refuse to delete a station that is currently being used; admins
        # must wait for the user to log out first.
        if status in ['In Use', 'Paused']:
            messagebox.showerror("Error",
                                 "Cannot delete a station while it is in use or paused. Please wait for the user to log out.",
                                 parent=self.root)
            return

        confirm = messagebox.askyesno("Confirm Deletion",
                                      f"Are you sure you want to delete Station '{station_id}'?\nThis will execute the kill switch.",
                                      parent=self.root)
        if confirm:
            response = self.net.send_request("DELETE_STATION", {"station_id": station_id})
            if response and response.get("status") == "SUCCESS":
                messagebox.showinfo("Success", f"Station {station_id} deleted successfully.", parent=self.root)
                self.poll_dashboard_data()
            else:
                messagebox.showerror("Error", f"Failed to delete station: {response.get('message', 'Unknown Error')}",
                                     parent=self.root)

    # ==========================================
    # USER MANAGEMENT LOGIC
    # ==========================================
    def minimize_window(self):
        """Drops the always-on-top attribute and iconifies the window."""
        self.root.attributes('-topmost', False)
        self.root.iconify()
        self.root.bind("<Map>", self.restore_topmost)

    def open_admin_settings(self):
        """Opens the SettingsWindow for the currently logged-in admin."""
        self.root.attributes('-topmost', False)
        settings = SettingsWindow(self.net, self.admin_username, self.root, role="root")
        new_username = settings.show()
        # If the admin changed their own username inside Settings, reflect it in the header.
        if new_username and new_username != self.admin_username:
            self.admin_username = new_username
            self.lbl_title.config(text=f"🔧 ADMIN PANEL | {self.admin_username}")
        self.root.attributes('-topmost', True)

    def restore_topmost(self, event):
        """Re-applies topmost + fullscreen when the window is restored from minimised state."""
        if self.root.state() == 'normal':
            self.root.attributes('-topmost', True)
            self.root.attributes('-fullscreen', True)
            self.root.unbind("<Map>")

    def fetch_users(self):
        """Refreshes the User Management listbox with every account except the current admin."""
        self.listbox.delete(0, tk.END)
        response = self.net.send_request("FETCH_ALL_USERS", {})
        if response and response.get("status") == "SUCCESS":
            all_users = response.get("users", [])
            self.users_cache = []
            for u in all_users:
                # Skip the current admin so they can't delete themselves by accident.
                if u['username'] == self.admin_username: continue
                self.users_cache.append(u)
                display = f"{u['username']} | {u['role']} | {u['time_balance']}m"
                self.listbox.insert(tk.END, display)

    def get_selected_user(self):
        """Returns the user dict currently selected in the management listbox, or None."""
        idx = self.listbox.curselection()
        if not idx:
            messagebox.showwarning("Selection", "Please select a user first.")
            return None
        return self.users_cache[idx[0]]

    def create_user(self):
        """Opens a modal dialog for creating a new user account."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Create New User")
        dialog.geometry("350x450")
        dialog.configure(bg="#34495e")
        dialog.attributes('-topmost', True)

        # Centre the dialog over the admin panel window.
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 225
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="Create New User", font=("Arial", 16, "bold"), bg="#34495e", fg="white").pack(pady=15)

        username_var = tk.StringVar()
        fullname_var = tk.StringVar()
        password_var = tk.StringVar()
        role_var = tk.StringVar(value="user")

        def on_role_change(*args):
            # Standard users authenticate via Face ID only, so disable the
            # password field unless the new account is being set up as root.
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
            pwd  = password_var.get().strip()
            rle  = role_var.get()

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
        """Deletes the currently selected user after confirmation."""
        user = self.get_selected_user()
        if not user: return
        # Defensive check — get_selected_user already filters out the admin
        # themselves, but this guards against any future regression.
        if user['username'] == self.admin_username:
            messagebox.showerror("Error", "You cannot delete yourself!")
            return

        confirm = messagebox.askyesno("Confirm", f"Delete user '{user['username']}' permanently?")
        if confirm:
            self.net.send_request("DELETE_USER", {"username": user['username']})
            self.fetch_users()

    def manage_time(self):
        """Opens a dialog for adding or removing minutes from the selected user's balance."""
        user = self.get_selected_user()
        if not user: return

        dialog = tk.Toplevel(self.root)
        dialog.title("Adjust Time")
        dialog.geometry("350x200")
        dialog.configure(bg="#34495e")
        dialog.attributes('-topmost', True)

        # Centre the dialog over the admin panel window.
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 100
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text=f"Adjust Balance: {user['username']}", font=("Arial", 12, "bold"), bg="#34495e",
                 fg="white").pack(pady=(20, 2))
        tk.Label(dialog, text=f"Current: {user['time_balance']} mins", font=("Arial", 10), bg="#34495e",
                 fg="#bdc3c7").pack(pady=2)
        tk.Label(dialog, text="Enter minutes (+ or -):", font=("Arial", 10), bg="#34495e", fg="white").pack(pady=2)

        # Restrict input to integers (optionally signed) via a Tk validator.
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
        """Opens a flow for editing one field of the selected user's profile."""
        user = self.get_selected_user()
        if not user: return

        # Only root users have a password; standard users use Face ID only.
        allowed_fields = ['full_name', 'username', 'role']
        if user['role'] == 'root':
            allowed_fields.append('password')

        fields_str = ", ".join([f"'{f}'" for f in allowed_fields])
        choice = simpledialog.askstring("Edit", f"Type field to edit: {fields_str}", parent=self.root)

        if not choice: return
        choice = choice.lower().strip()

        if choice not in allowed_fields:
            # Special-case the password message so the admin understands why
            # it's not editable for a standard user.
            if choice == 'password':
                messagebox.showerror("Error", "Standard users are Biometric-Only and do not use passwords.",
                                     parent=self.root)
            else:
                messagebox.showerror("Error", "Invalid field name.", parent=self.root)
            return

        new_val = simpledialog.askstring("Edit", f"Enter new value for {choice}:", parent=self.root)
        if new_val:
            resp = self.net.send_request("UPDATE_PROFILE", {"username": user['username'], "field": choice, "value": new_val})
            if not (resp and resp.get("status") == "SUCCESS"):
                messagebox.showerror("Error", resp.get("message", "Update failed.") if resp else "No server response.", parent=self.root)
                return

            # Role-change side effects.
            if choice == 'role':
                if new_val.lower() == 'root':
                    # Promoted to admin — they must have a password set
                    # immediately so they can use the manual login flow.
                    messagebox.showinfo("Password Required",
                                       f"'{user['username']}' was promoted to admin.\nPlease set a password for them now.",
                                       parent=self.root)
                    while True:
                        new_pass = simpledialog.askstring(
                            "Set Password",
                            f"Enter a password for '{user['username']}':",
                            show='*', parent=self.root
                        )
                        if not new_pass:
                            messagebox.showwarning("Required", "A password is required for admin accounts. Please enter one.", parent=self.root)
                            continue
                        confirm_pass = simpledialog.askstring(
                            "Confirm Password",
                            "Confirm the password:",
                            show='*', parent=self.root
                        )
                        if new_pass != confirm_pass:
                            messagebox.showerror("Mismatch", "Passwords do not match. Please try again.", parent=self.root)
                            continue
                        self.net.send_request("UPDATE_PROFILE", {
                            "username": user['username'], "field": "password", "value": new_pass
                        })
                        messagebox.showinfo("Done", f"Password set for '{user['username']}'.", parent=self.root)
                        break

                elif new_val.lower() == 'user':
                    # Demoted to standard user — clear any stored password.
                    self.net.send_request("UPDATE_PROFILE", {
                        "username": user['username'], "field": "password", "value": ""
                    })

            self.fetch_users()

    def recapture_face(self):
        """Admin-driven flow for recapturing a user's face encodings."""
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

                    if key == 32:  # SPACE — capture the current frame.
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        boxes = face_recognition.face_locations(rgb)
                        if boxes:
                            encs = face_recognition.face_encodings(rgb, boxes)
                            if encs:
                                captured_encodings.append(encs[0].tolist())
                                captured = True
                                # Flash a green confirmation border.
                                cv2.rectangle(frame, (0, 0), (640, 480), (0, 255, 0), 20)
                                cv2.imshow("Admin Face Setup", frame)
                                cv2.waitKey(300)

                    if key == 27:  # ESC — abort capture.
                        print("Capture Cancelled.")
                        return

            capture_successful = True

        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.root.deiconify()
            self.root.attributes('-topmost', True)

        if capture_successful:
            # Guard against a partially completed capture (e.g. one frame failed to read).
            if len(captured_encodings) != 5:
                messagebox.showerror("Capture Incomplete",
                                     f"Only {len(captured_encodings)}/5 angles were captured "
                                     f"(camera read failed on one). Please try again.",
                                     parent=self.root)
                return

            # Require the admin to re-enter their password to authorise the
            # update — this prevents a walk-up attack where someone uses an
            # unattended admin panel to replace another user's face encoding.
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
        """Tk validator allowing empty, lone '-', or integer strings only."""
        if P in ("", "-"): return True
        try:
            int(P)
            return True
        except ValueError:
            return False

    def on_select(self, event):
        """Placeholder selection handler — no action required on selection."""
        pass

    def close(self):
        """Stops the polling loop and tears down the admin window."""
        if self._poll_timer is not None:
            self.root.after_cancel(self._poll_timer)
        self.root.destroy()