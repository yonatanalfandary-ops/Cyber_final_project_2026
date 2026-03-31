import socket
import threading
from database_manager import DatabaseManager
from NetworkProtocol import Protocol
from Crypters import NoCrypter, ASymetricCrypter, SymetricCrypter

# Configuration
SERVER_IP = "0.0.0.0"
SERVER_PORT = 5000


class RentalServer:
    def __init__(self):
        self.db = DatabaseManager()
        self.active_stations = {}  # Tracks {station_id: protocol} for Kill Switch
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((SERVER_IP, SERVER_PORT))
        self.server_socket.listen(5)
        print(f"✅ CENTRAL SERVER STARTED on {SERVER_IP}:{SERVER_PORT}")
        print("Waiting for Stations to connect...")

    def handle_client(self, client_socket, addr):
        """Handles requests from Stations."""
        print(f"🔗 Connection from: {addr}")
        protocol = Protocol(client_socket, NoCrypter())
        station_id = None  # Declare here so the 'finally' block can see it

        try:
            # --- START HANDSHAKE ---
            asym_crypter = ASymetricCrypter()
            pub_key_bytes = asym_crypter.get_public_key_bytes()

            protocol.create_and_send_message({
                "action": "HANDSHAKE_PUB_KEY",
                "pub_key_hex": pub_key_bytes.hex()
            })

            handshake_reply = protocol.get_message()
            if not handshake_reply or handshake_reply.get("action") != "HANDSHAKE_SYM_KEY":
                print(f"❌ Handshake failed with {addr}")
                client_socket.close()
                return

            encrypted_sym_key = bytes.fromhex(handshake_reply.get("sym_key_hex"))
            sym_key_bytes = asym_crypter.decrypt(encrypted_sym_key)

            protocol.crypter = SymetricCrypter(key=sym_key_bytes)
            print(f"🔐 Secure AES Encrypted Connection Established with {addr}")
            # --- END HANDSHAKE ---

            # --- NEW: STATION INITIALIZATION & SECURITY CHECK ---
            init_req = protocol.get_message()
            if not init_req: return

            init_action = init_req.get("action")

            if init_action == "REQUEST_NEW_STATION_ID":
                station_id = self.db.create_gap_station()
                protocol.create_and_send_message({"status": "SUCCESS", "new_id": station_id})


            elif init_action == "CONNECT_STATION":
                station_id = init_req.get("station_id")

                # --- TASK 12 FIX: Check for duplicate Station ID ---
                if station_id in self.active_stations:
                    print(f"⛔ Denied Connection: Station {station_id} is already in use!")
                    protocol.create_and_send_message({"status": "ERROR_STATION_IN_USE"})
                    return  # Drop the duplicate connection instantly

                # SECURITY CHECK: Was it deleted from the DB while offline?
                if not self.db.check_station_exists(station_id):
                    print(f"⛔ Denied Connection to wiped station: {station_id}")
                    protocol.create_and_send_message({"action": "COMMAND_UNREGISTER"})
                    return
                protocol.create_and_send_message({"status": "SUCCESS"})
            else:
                return  # Invalid boot sequence, drop connection.

            # Register station as Online
            self.active_stations[station_id] = protocol
            self.db.update_station_state(station_id, 'Online', None)
            print(f"🖥️  {station_id} is Online.")

            # --- MAIN LOOP ---
            while True:
                request = protocol.get_message()
                if not request: break  # Client disconnected

                action = request.get("action")
                print(f"📩 Action '{action}' from {station_id} ({addr})")

                response = {"status": "ERROR", "message": "Unknown Action"}

                # CASE 1: User Login (Password)
                if action == "LOGIN":
                    username = request.get("username")
                    password = request.get("password")

                    user = self.db.authenticate_user_login(username, password)

                    if user:
                        if user['role'] == 'user':
                            print(f"⛔ Login Denied for {username}: Standard users must use Face ID.")
                            response = {
                                "status": "DENIED",
                                "message": "Standard users cannot use passwords. Please use Face ID."
                            }
                        else:
                            # --- TASK 15 FIX: Prevent Duplicate Admin Login ---
                            requested_user = user['username']
                            is_duplicate = False
                            for sid, prot in self.active_stations.items():
                                if sid != station_id and getattr(prot, 'active_user', None) == requested_user:
                                    is_duplicate = True
                                    break

                            if is_duplicate:
                                print(f"⛔ Login Blocked: Admin {requested_user} is already active on another station.")
                                protocol.create_and_send_message({"status": "ERROR_USER_ALREADY_LOGGED_IN"})
                                continue  # Skip the rest of the loop, forcing client to handle the error

                            # Proceed with Admin Login & Update Station State
                            protocol.active_user = requested_user  # Track user in server memory
                            self.db.update_station_state(station_id, 'In Use', requested_user)
                            response = {
                                "status": "SUCCESS",
                                "username": user['username'],
                                "role": user['role'],
                                "time_balance": user['time_balance'],
                                "face_encoding": user['face_encoding']
                            }
                            print(f"✅ Admin '{username}' logged in at {station_id}")
                    else:
                        response = {"status": "FAIL", "message": "Invalid Username or Password"}

                # CASE 1b: Logout
                elif action == "LOGOUT":
                    protocol.active_user = None  # Clear user from server memory
                    self.db.update_station_state(station_id, 'Online', None)
                    response = {"status": "SUCCESS"}

                # CASE 1c: Sync Station State (Used by Face ID & UI Updates)
                elif action == "SYNC_STATE":
                    new_status = request.get("state_status")
                    active_username = request.get("active_user")

                    # --- TASK 15 FIX: Prevent Duplicate Face ID / Normal User Login ---
                    if new_status in ["In Use", "Paused"] and active_username:
                        is_duplicate = False
                        for sid, prot in self.active_stations.items():
                            if sid != station_id and getattr(prot, 'active_user', None) == active_username:
                                is_duplicate = True
                                break

                        if is_duplicate:
                            print(f"⛔ Sync Blocked: User {active_username} is already active on another station.")
                            protocol.create_and_send_message({"status": "ERROR_USER_ALREADY_LOGGED_IN"})
                            continue  # Skip the rest of the loop, forcing client to handle the error

                        protocol.active_user = active_username  # Track user in server memory
                    else:
                        protocol.active_user = None  # Clear if returning to Online/Lock screen

                    self.db.update_station_state(station_id, new_status, active_username)
                    response = {"status": "SUCCESS"}
                    print(f"🔄 {station_id} State Synced: {new_status} | User: {active_username}")

                # CASE 2: Register New User
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

                # CASE 3: Register Station
                elif action == "REGISTER_STATION":
                    if request.get("requester_role") == "root":
                        success = self.db.register_station(
                            request.get("station_id"),
                            request.get("station_name")
                        )
                        response = {"status": "SUCCESS" if success else "FAIL"}
                    else:
                        response = {"status": "DENIED", "message": "Permission Denied"}

                # CASE 4: Update User Face
                elif action == "UPDATE_FACE":
                    target_username = request.get("username")
                    password = request.get("password")
                    new_face_data = request.get("face_data")
                    requester_username = request.get("requester_username")

                    # 1. Check if it's a self-update by the currently actively logged-in user
                    is_self_update = (protocol.active_user == target_username)

                    # 2. Try authenticating the regular user (if a password was provided)
                    user_auth = self.db.authenticate_user_login(target_username, password) if password else None

                    # 3. Try authenticating the root user requesting the override
                    admin_auth = None
                    if requester_username and password:
                        admin_auth = self.db.authenticate_user_login(requester_username, password)
                    is_admin = admin_auth and admin_auth.get('role') == 'root'

                    # AUTHORIZATION LOGIC:
                    # Allow if it's an active self-update OR they provided a valid user password OR valid root password
                    if is_self_update or user_auth or is_admin:
                        success = self.db.update_user_face(target_username, new_face_data)
                        if success:
                            response = {"status": "SUCCESS", "message": "Face Updated"}
                            print(f"📸 Face updated for {target_username}")
                        else:
                            response = {"status": "FAIL", "message": "Database Error"}
                    else:
                        print(f"⛔ Denied face update for {target_username} (Unauthorized)")
                        response = {"status": "DENIED", "message": "Unauthorized or Bad Password"}

                # CASE 4b: Update Profile
                elif action == "UPDATE_PROFILE":
                    username = request.get("username")
                    field = request.get("field")
                    value = request.get("value")

                    success, msg = self.db.update_user_field(username, field, value)
                    if success:
                        response = {"status": "SUCCESS", "message": "Profile Updated"}
                        print(f"✅ Updated {field} for {username}")
                    else:
                        response = {"status": "ERROR", "message": msg}

                # CASE 5: Fetch Active Renters
                elif action == "FETCH_ACTIVE_USERS":
                    active_users = self.db.get_active_renters()
                    response = {"status": "SUCCESS", "users": active_users}

                # CASE 6: Live Time Deduction
                elif action == "DEDUCT_TIME":
                    username = request.get("username")
                    seconds = request.get("seconds")
                    self.db.deduct_user_time(username, seconds)
                    response = {"status": "SUCCESS"}

                # CASE 7: Add Rented Time
                elif action == "ADD_TIME":
                    username = request.get("username")
                    minutes = request.get("minutes")

                    if self.db.add_time(username, minutes):
                        revenue_earned = float(minutes) * 0.5

                        # --- THE FIX: Only add to station revenue if it's a positive purchase ---
                        if revenue_earned > 0:
                            self.db.add_station_revenue(station_id, revenue_earned)
                            print(
                                f"💰 Added {minutes} mins for {username} at {station_id}. Revenue: +${revenue_earned:.2f}")
                        else:
                            print(f"⚖️ Admin modified time for {username} by {minutes} mins. (Revenue unchanged)")

                        response = {"status": "SUCCESS"}
                    else:
                        response = {"status": "FAILURE"}

                # CASE 8: Fetch All Users
                elif action == "FETCH_ALL_USERS":
                    users = self.db.get_all_users()
                    response = {"status": "SUCCESS", "users": users}

                # CASE 9: Create User
                elif action == "CREATE_USER":
                    success, msg = self.db.create_user(
                        request.get("username"),
                        request.get("password"),
                        request.get("full_name"),
                        request.get("role", "user")
                    )
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                # CASE 10: Delete User
                elif action == "DELETE_USER":
                    success, msg = self.db.delete_user(request["username"])
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                # CASE 11: Kill Switch (Admin Panel Command)
                elif action == "DELETE_STATION":
                    target_id = request.get("target_id")
                    self.db.delete_station(target_id)
                    # If the deleted station is currently connected, fire the wipe payload!
                    if target_id in self.active_stations:
                        try:
                            self.active_stations[target_id].create_and_send_message({"action": "COMMAND_UNREGISTER"})
                        except:
                            pass
                    response = {"status": "SUCCESS"}

                protocol.create_and_send_message(response)

        except Exception as e:
            print(f"⚠ Connection Error {addr}: {e}")
        finally:
            if station_id:
                print(f"🔌 {station_id} Disconnected.")
                # Mark offline and remove from Kill Switch registry
                self.db.update_station_state(station_id, 'Offline', None)
                if station_id in self.active_stations:
                    del self.active_stations[station_id]
            client_socket.close()

    def start(self):
        while True:
            client_sock, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()


if __name__ == "__main__":
    server = RentalServer()
    server.start()