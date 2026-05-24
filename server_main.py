import socket
import threading
from database_manager import DatabaseManager
from NetworkProtocol import Protocol
from Crypters import NoCrypter, AsymmetricCrypter, SymmetricCrypter

# --- Configuration ---
SERVER_IP = "0.0.0.0"
SERVER_PORT = 5000


class RentalServer:
    """
    Central server for the rental system. Accepts station connections,
    performs a hybrid RSA/AES handshake with each client, and dispatches
    incoming requests to the appropriate database operations.

    One thread is spawned per connected station, and the active_stations
    map is used to enforce the rule that any given station ID or user can
    only be active on one client at a time.
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.active_stations = {}  # {station_id: Protocol} — used by the kill switch and duplicate-login checks.
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((SERVER_IP, SERVER_PORT))
        self.server_socket.listen(5)
        print(f"CENTRAL SERVER STARTED on {SERVER_IP}:{SERVER_PORT}")
        print("Waiting for Stations to connect...")

    def handle_client(self, client_socket, addr):
        """Handles the full lifecycle of one connected station, from handshake to disconnect."""
        print(f"Connection from: {addr}")
        protocol = Protocol(client_socket, NoCrypter())
        # Declare up front so the 'finally' block can clean up even if we
        # never get as far as setting the station ID.
        station_id = None

        try:
            # --- Encryption handshake ---
            # Generate a fresh RSA key pair, send the public key to the
            # client, and wait for it to return a symmetric session key
            # encrypted under that public key. From that point on, the
            # protocol is upgraded to symmetric (Fernet) encryption.
            asym_crypter = AsymmetricCrypter()
            pub_key_bytes = asym_crypter.get_public_key_bytes()

            protocol.create_and_send_message({
                "action": "HANDSHAKE_PUB_KEY",
                "pub_key_hex": pub_key_bytes.hex()
            })

            handshake_reply = protocol.get_message()
            if not handshake_reply or handshake_reply.get("action") != "HANDSHAKE_SYM_KEY":
                print(f"Handshake failed with {addr}")
                client_socket.close()
                return

            encrypted_sym_key = bytes.fromhex(handshake_reply.get("sym_key_hex"))
            sym_key_bytes = asym_crypter.decrypt(encrypted_sym_key)

            protocol.crypter = SymmetricCrypter(key=sym_key_bytes)
            print(f"Secure AES Encrypted Connection Established with {addr}")
            # --- End handshake ---

            # --- Station initialisation & security check ---
            init_req = protocol.get_message()
            if not init_req: return

            init_action = init_req.get("action")

            if init_action == "REQUEST_NEW_STATION_ID":
                # First-time client — allocate a new station ID using gap logic.
                station_id = self.db.create_gap_station()
                protocol.create_and_send_message({"status": "SUCCESS", "new_id": station_id})

            elif init_action == "CONNECT_STATION":
                station_id = init_req.get("station_id")

                # Reject the connection if another client is already running
                # under this station ID.
                if station_id in self.active_stations:
                    print(f"Denied Connection: Station {station_id} is already in use!")
                    protocol.create_and_send_message({"status": "ERROR_STATION_IN_USE"})
                    return

                # Honour the kill switch: if the station was deleted from
                # the database while offline, instruct the client to wipe
                # its local config and exit.
                if not self.db.check_station_exists(station_id):
                    print(f"Denied Connection to wiped station: {station_id}")
                    protocol.create_and_send_message({"action": "COMMAND_UNREGISTER"})
                    return

                protocol.create_and_send_message({"status": "SUCCESS"})
            else:
                # Unknown initialisation action — drop the connection.
                return

            # Mark the station as Online both in memory and in the database.
            self.active_stations[station_id] = protocol
            self.db.update_station_state(station_id, 'Online', None)
            print(f"{station_id} is Online.")

            # Audit: record that this station came Online.
            self.db.log_station_status(station_id, 'Online')

            # --- Main request loop ---
            while True:
                request = protocol.get_message()
                if not request: break  # Client disconnected.

                action = request.get("action")
                print(f"Action '{action}' from {station_id} ({addr})")

                response = {"status": "ERROR", "message": "Unknown Action"}

                # CASE 1: Password login (admins only).
                if action == "LOGIN":
                    username = request.get("username")
                    password = request.get("password")

                    user = self.db.authenticate_user_login(username, password)

                    if user:
                        if user['role'] == 'user':
                            # Standard users authenticate via Face ID only;
                            # they're never allowed to log in by password
                            # even if a password happens to match.
                            print(f"Login Denied for {username}: Standard users must use Face ID.")
                            response = {
                                "status": "DENIED",
                                "message": "Standard users cannot use passwords. Please use Face ID."
                            }
                        else:
                            # Duplicate-admin check: refuse a login if the
                            # same admin account is already active on a
                            # different station.
                            requested_user = user['username']
                            is_duplicate = False
                            for sid, prot in self.active_stations.items():
                                if sid != station_id and getattr(prot, 'active_user', None) == requested_user:
                                    is_duplicate = True
                                    break

                            if is_duplicate:
                                print(f"Login Blocked: Admin {requested_user} is already active on another station.")
                                protocol.create_and_send_message({"status": "ERROR_USER_ALREADY_LOGGED_IN"})
                                continue

                            # NOTE: protocol.active_user is intentionally
                            # NOT set here. The client always follows up
                            # with a SYNC_STATE "In Use" call, which is the
                            # single canonical place that sets active_user
                            # and writes the 'Joined' audit log. Setting it
                            # here would make SYNC_STATE mistake the new
                            # login for a resume-from-pause and silently
                            # skip the audit log entry.
                            self.db.update_station_state(station_id, 'In Use', requested_user)
                            response = {
                                "status": "SUCCESS",
                                "username": user['username'],
                                "role": user['role'],
                                "time_balance": user['time_balance'],
                                "face_encoding": user['face_encoding']
                            }
                            print(f"Admin '{username}' logged in at {station_id}")
                    else:
                        response = {"status": "FAIL", "message": "Invalid Username or Password"}

                # CASE 1b: Logout.
                elif action == "LOGOUT":
                    # Audit: log the user leaving before clearing the active user reference.
                    departing_user = getattr(protocol, 'active_user', None)
                    if departing_user:
                        self.db.log_user_action(departing_user, station_id, 'Left')

                    protocol.active_user = None
                    self.db.update_station_state(station_id, 'Online', None)
                    response = {"status": "SUCCESS"}

                # CASE 1c: Sync station state (used by Face ID login and pause/resume).
                elif action == "SYNC_STATE":
                    new_status = request.get("state_status")
                    active_username = request.get("active_user")

                    # Duplicate-user check for face-ID and standard-user logins.
                    if new_status in ["In Use", "Paused"] and active_username:
                        is_duplicate = False
                        for sid, prot in self.active_stations.items():
                            if sid != station_id and getattr(prot, 'active_user', None) == active_username:
                                is_duplicate = True
                                break

                        if is_duplicate:
                            print(f"Sync Blocked: User {active_username} is already active on another station.")
                            protocol.create_and_send_message({"status": "ERROR_USER_ALREADY_LOGGED_IN"})
                            continue

                        # Audit: only log 'Joined' on a genuinely new login
                        # session. If protocol.active_user already matches
                        # the incoming name, this is a resume-from-pause
                        # and logging it would create a duplicate entry.
                        if new_status == "In Use":
                            previous_user = getattr(protocol, 'active_user', None)
                            if previous_user != active_username:
                                self.db.log_user_action(active_username, station_id, 'Joined')

                        protocol.active_user = active_username
                    else:
                        # Transitioning back to Online — there is no active user.
                        protocol.active_user = None

                    self.db.update_station_state(station_id, new_status, active_username)
                    response = {"status": "SUCCESS"}
                    print(f"{station_id} State Synced: {new_status} | User: {active_username}")

                # CASE 2: Register a new standard user (admin-only action).
                elif action == "REGISTER_USER":
                    if request.get("requester_role") == "root":
                        success = self.db.register_user(
                            request.get("new_username"),
                            request.get("new_password"),
                            request.get("face_data"),
                            role="user"
                        )
                        response = {"status": "SUCCESS" if success else "FAIL"}
                    else:
                        response = {"status": "DENIED", "message": "Only Root can create users."}

                # CASE 3: Register a new station (admin-only action).
                elif action == "REGISTER_STATION":
                    if request.get("requester_role") == "root":
                        success = self.db.register_station(
                            request.get("station_id"),
                            request.get("station_name")
                        )
                        response = {"status": "SUCCESS" if success else "FAIL"}
                    else:
                        response = {"status": "DENIED", "message": "Permission Denied"}

                # CASE 4: Update a user's face encoding.
                # Authorised if it's a self-update during an active session,
                # if the request includes the target user's password, or if
                # it includes a valid admin's password.
                elif action == "UPDATE_FACE":
                    target_username = request.get("username")
                    password = request.get("password")
                    new_face_data = request.get("face_data")
                    requester_username = request.get("requester_username")

                    is_self_update = (protocol.active_user == target_username)
                    user_auth = self.db.authenticate_user_login(target_username, password) if password else None
                    admin_auth = None
                    if requester_username and password:
                        admin_auth = self.db.authenticate_user_login(requester_username, password)
                    is_admin = admin_auth and admin_auth.get('role') == 'root'

                    if is_self_update or user_auth or is_admin:
                        success = self.db.update_user_face(target_username, new_face_data)
                        if success:
                            response = {"status": "SUCCESS", "message": "Face Updated"}
                            print(f"Face updated for {target_username}")
                        else:
                            response = {"status": "FAIL", "message": "Database Error"}
                    else:
                        print(f"Denied face update for {target_username} (Unauthorized)")
                        response = {"status": "DENIED", "message": "Unauthorized or Bad Password"}

                # CASE 4b: Update one field of a user's profile.
                elif action == "UPDATE_PROFILE":
                    username = request.get("username")
                    field = request.get("field")
                    value = request.get("value")

                    success, msg = self.db.update_user_field(username, field, value)
                    if success:
                        response = {"status": "SUCCESS", "message": "Profile Updated"}
                        print(f"Updated {field} for {username}")
                    else:
                        response = {"status": "ERROR", "message": msg}

                # CASE 5: Fetch all active renters (users with balance > 0 and a face encoding).
                elif action == "FETCH_ACTIVE_USERS":
                    active_users = self.db.get_active_renters()
                    response = {"status": "SUCCESS", "users": active_users}

                # CASE 6: Live time deduction during a session.
                elif action == "DEDUCT_TIME":
                    username = request.get("username")
                    seconds = request.get("seconds")
                    self.db.deduct_user_time(username, seconds)
                    response = {"status": "SUCCESS"}

                # CASE 6b: Force a user's balance to zero when their session expires.
                elif action == "EXPIRE_SESSION":
                    username = request.get("username")
                    self.db.expire_session(username)
                    print(f"Session expired for '{username}'. Balance zeroed.")
                    response = {"status": "SUCCESS"}

                # CASE 7: Add purchased minutes to a user's balance.
                elif action == "ADD_TIME":
                    username = request.get("username")
                    minutes = request.get("minutes")

                    if self.db.add_time(username, minutes):
                        # If this looks like a real purchase (positive
                        # minute count), record the revenue against the
                        # current station. Negative adjustments by an admin
                        # do not affect revenue.
                        revenue_earned = float(minutes) * 0.5
                        if revenue_earned > 0:
                            self.db.add_station_revenue(station_id, revenue_earned)
                            print(f"Added {minutes} mins for {username} at {station_id}. Revenue: +${revenue_earned:.2f}")
                        else:
                            print(f"Admin modified time for {username} by {minutes} mins. (Revenue unchanged)")
                        response = {"status": "SUCCESS"}
                    else:
                        response = {"status": "FAILURE"}

                # CASE 8: Fetch all users (dashboard view with live status).
                elif action == "FETCH_ALL_USERS":
                    users = self.db.get_all_users()
                    stations = self.db.get_all_stations()

                    # Build a lookup so each user can be annotated with the
                    # station they're currently connected to (if any).
                    active_user_map = {}
                    for st in stations:
                        if st.get('current_user'):
                            active_user_map[st['current_user']] = {
                                'station_id': st['station_id'],
                                'status': st['status']
                            }

                    for u in users:
                        username = u['username']
                        if username in active_user_map:
                            u['status'] = active_user_map[username]['status']
                            u['connected_station'] = active_user_map[username]['station_id']
                        else:
                            u['status'] = 'Offline'
                            u['connected_station'] = 'None'

                    response = {"status": "SUCCESS", "users": users}

                # CASE 8b: Fetch a single user by username (targeted login lookup).
                elif action == "FETCH_USER":
                    target_username = request.get("username")
                    user = self.db.get_user_by_username(target_username)

                    if user:
                        # Attach live station status, matching the shape returned by FETCH_ALL_USERS.
                        stations = self.db.get_all_stations()
                        active_user_map = {
                            st['current_user']: st
                            for st in stations
                            if st.get('current_user')
                        }
                        if user['username'] in active_user_map:
                            st = active_user_map[user['username']]
                            user['status'] = st['status']
                            user['connected_station'] = st['station_id']
                        else:
                            user['status'] = 'Offline'
                            user['connected_station'] = 'None'

                        response = {"status": "SUCCESS", "user": user}
                    else:
                        response = {"status": "ERROR", "message": "User not found"}

                # CASE 9: Create a user.
                elif action == "CREATE_USER":
                    success, msg = self.db.create_user(
                        request.get("username"),
                        request.get("password"),
                        request.get("full_name"),
                        request.get("role", "user")
                    )
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                # CASE 10: Delete a user.
                elif action == "DELETE_USER":
                    success, msg = self.db.delete_user(request["username"])
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                # CASE 11: Kill switch — delete a station and notify it if still connected.
                elif action == "DELETE_STATION":
                    target_id = request.get("station_id")

                    if target_id:
                        self.db.delete_station(target_id)
                        # If the target station is currently connected,
                        # push it the kill-switch command so it wipes its
                        # local config and exits immediately.
                        if target_id in self.active_stations:
                            try:
                                self.active_stations[target_id].create_and_send_message(
                                    {"action": "COMMAND_UNREGISTER"})
                            except:
                                pass
                        response = {"status": "SUCCESS"}
                    else:
                        response = {"status": "ERROR", "message": "Missing station ID"}

                # CASE 12: Fetch every station's current state (dashboard view).
                elif action == "FETCH_STATIONS":
                    stations = self.db.get_all_stations()
                    response = {"status": "SUCCESS", "stations": stations}

                # CASE 13: Fetch the user audit log (newest first).
                elif action == "FETCH_USER_AUDIT":
                    rows = self.db.get_user_audit()
                    response = {"status": "SUCCESS", "records": rows}

                # CASE 14: Fetch the station audit log (newest first).
                elif action == "FETCH_STATION_AUDIT":
                    rows = self.db.get_station_audit()
                    response = {"status": "SUCCESS", "records": rows}

                # CASE 15: Read a setting value.
                elif action == "GET_SETTING":
                    key = request.get("key")
                    value = self.db.get_setting(key)
                    if value is not None:
                        response = {"status": "SUCCESS", "value": value}
                    else:
                        response = {"status": "ERROR", "message": "Setting not found"}

                # CASE 16: Write a setting value.
                elif action == "SET_SETTING":
                    key   = request.get("key")
                    value = request.get("value")
                    success = self.db.set_setting(key, value)
                    response = {"status": "SUCCESS" if success else "ERROR"}

                # CASE 17: Station overview report — total online time per station.
                elif action == "FETCH_STATION_OVERVIEW":
                    rows = self.db.get_station_overview()
                    response = {"status": "SUCCESS", "records": rows}

                # CASE 18: User overview report — total session time per user.
                elif action == "FETCH_USER_OVERVIEW":
                    rows = self.db.get_user_overview()
                    response = {"status": "SUCCESS", "records": rows}

                # CASE 19: Clear the user audit log.
                elif action == "CLEAR_USER_AUDIT":
                    success = self.db.clear_user_audit()
                    response = {"status": "SUCCESS" if success else "ERROR"}

                # CASE 21: Clear the station audit log.
                elif action == "CLEAR_STATION_AUDIT":
                    success = self.db.clear_station_audit()
                    response = {"status": "SUCCESS" if success else "ERROR"}

                protocol.create_and_send_message(response)

        except Exception as e:
            print(f"Connection Error {addr}: {e}")
        finally:
            if station_id:
                print(f"{station_id} Disconnected.")

                # Audit: if a user was still active when the socket dropped,
                # log them out so the audit log remains balanced.
                orphaned_user = getattr(protocol, 'active_user', None)
                if orphaned_user:
                    self.db.log_user_action(orphaned_user, station_id, 'Left')

                # Audit: record that the station went Offline.
                self.db.log_station_status(station_id, 'Offline')

                self.db.update_station_state(station_id, 'Offline', None)
                if station_id in self.active_stations:
                    del self.active_stations[station_id]

            client_socket.close()

    def start(self):
        """Accepts incoming connections and dispatches each to its own daemon thread."""
        while True:
            client_sock, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()


if __name__ == "__main__":
    server = RentalServer()
    server.start()