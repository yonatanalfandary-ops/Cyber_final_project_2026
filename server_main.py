import socket
import threading
import json
import struct
from database_manager import DatabaseManager

# Configuration
SERVER_IP = "0.0.0.0"
SERVER_PORT = 5000


class RentalServer:
    def __init__(self):
        self.db = DatabaseManager()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((SERVER_IP, SERVER_PORT))
        self.server_socket.listen(5)
        print(f"✅ CENTRAL SERVER STARTED on {SERVER_IP}:{SERVER_PORT}")
        print("Waiting for Stations to connect...")

    def send_json(self, client_socket, data):
        """Sends JSON data with a length header."""
        try:
            message = json.dumps(data).encode('utf-8')
            header = struct.pack('I', len(message))
            client_socket.sendall(header + message)
        except Exception as e:
            print(f"❌ Send Error: {e}")

    def handle_client(self, client_socket, addr):
        """Handles requests from Stations."""
        print(f"🔗 Connection from: {addr}")

        try:
            while True:
                # 1. Read Header
                header = client_socket.recv(4)
                if not header: break
                msg_length = struct.unpack('I', header)[0]

                # 2. Read Body
                data = b""
                while len(data) < msg_length:
                    packet = client_socket.recv(4096)
                    if not packet: break
                    data += packet
                if not data: break

                # 3. Process Request
                request = json.loads(data.decode('utf-8'))
                action = request.get("action")
                print(f"📩 Action '{action}' from {addr}")

                response = {"status": "ERROR", "message": "Unknown Action"}

                # CASE 1: User Login
                if action == "LOGIN":
                    username = request.get("username")
                    password = request.get("password")
                    station_id = request.get("station_id")

                    user = self.db.authenticate_user_login(username, password)

                    if user:
                        self.db.activate_station(station_id)
                        response = {
                            "status": "SUCCESS",
                            "username": user['username'],
                            "role": user['role'],
                            "time_balance": user['time_balance'],
                            "face_encoding": user['face_encoding']
                        }
                        print(f"✅ User '{username}' logged in at {station_id}")
                    else:
                        response = {"status": "FAIL", "message": "Invalid Username or Password"}

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

                # CASE 4: Update User Face (FIXED)
                elif action == "UPDATE_FACE":
                    target_username = request.get("username")
                    password = request.get("password")
                    new_face_data = request.get("face_data")

                    # A. Check if it's the user themselves
                    user_auth = self.db.authenticate_user_login(target_username, password)

                    # B. Check if it's the Admin overriding (Root Override)
                    admin_auth = self.db.authenticate_user_login("admin", password)
                    is_admin = admin_auth and admin_auth['role'] == 'root'

                    if user_auth or is_admin:
                        success = self.db.update_user_face(target_username, new_face_data)
                        if success:
                            response = {"status": "SUCCESS", "message": "Face Updated"}
                            print(f"📸 Face updated for {target_username}")
                        else:
                            response = {"status": "FAIL", "message": "Database Error"}
                    else:
                        print(f"⛔ Denied face update for {target_username} (Bad Password)")
                        response = {"status": "DENIED", "message": "Bad Password"}

                # CASE 4b: Update Profile (Username, Password, Full Name)
                elif action == "UPDATE_PROFILE":
                    username = request.get("username")
                    field = request.get("field")
                    value = request.get("value")

                    # Call the existing method in your Database Manager
                    # This keeps the SQL logic inside database_manager.py
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
                        response = {"status": "SUCCESS"}
                        print(f"💰 Added {minutes} mins for {username}")
                    else:
                        response = {"status": "FAILURE"}

                # CASE 8: Fetch All Users
                elif action == "FETCH_ALL_USERS":
                    users = self.db.get_all_users()
                    response = {"status": "SUCCESS", "users": users}

                # CASE 9: Create User (Admin Panel)
                elif action == "CREATE_USER":
                    success, msg = self.db.create_user(
                        request["username"], request["password"],
                        request["full_name"], request["role"]
                    )
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                # CASE 10: Delete User
                elif action == "DELETE_USER":
                    success, msg = self.db.delete_user(request["username"])
                    response = {"status": "SUCCESS" if success else "FAILURE", "message": msg}

                self.send_json(client_socket, response)

        except Exception as e:
            print(f"⚠ Connection Error {addr}: {e}")
        finally:
            client_socket.close()

    def start(self):
        while True:
            client_sock, addr = self.server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True).start()


if __name__ == "__main__":
    server = RentalServer()
    server.start()