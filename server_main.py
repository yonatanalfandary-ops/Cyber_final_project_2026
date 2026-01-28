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

                # --- NEW LOGIC FOR RBAC SYSTEM ---

                # CASE 1: User Login (Station -> Server)
                if action == "LOGIN":
                    username = request.get("username")
                    password = request.get("password")
                    station_id = request.get("station_id")

                    # Authenticate User
                    user = self.db.authenticate_user_login(username, password)

                    if user:
                        # User found! Now activate the station
                        self.db.activate_station(station_id)
                        response = {
                            "status": "SUCCESS",
                            "username": user['username'],
                            "role": user['role'],
                            "time_balance": user['time_balance'],
                            "face_encoding": user['face_encoding']  # Send ONLY this user's face
                        }
                        print(f"✅ User '{username}' logged in at {station_id}")
                    else:
                        response = {"status": "FAIL", "message": "Invalid Username or Password"}

                # CASE 2: Register New User (Only Root can do this)
                elif action == "REGISTER_USER":
                    # Check who is asking? (In real system, we'd check a session token)
                    # For now, we trust the client to send 'requester_role'
                    if request.get("requester_role") == "root":
                        success = self.db.register_user(
                            request.get("new_username"),
                            request.get("new_password"),
                            request.get("face_data"),  # Expecting List of Lists
                            role="user"
                        )
                        if success:
                            response = {"status": "SUCCESS", "message": "User Created"}
                        else:
                            response = {"status": "FAIL", "message": "User already exists"}
                    else:
                        response = {"status": "DENIED", "message": "Only Root can create users."}

                # CASE 3: Register Station (Only Admin/Root can do this)
                elif action == "REGISTER_STATION":
                    if request.get("requester_role") == "root":
                        success = self.db.register_station(
                            request.get("station_id"),
                            request.get("station_name")
                        )
                        response = {"status": "SUCCESS" if success else "FAIL"}
                    else:
                        response = {"status": "DENIED", "message": "Permission Denied"}

                # CASE 4: Update User Face (For fixing the fake data)
                elif action == "UPDATE_FACE":
                    username = request.get("username")
                    password = request.get("password")
                    new_face_data = request.get("face_data")

                    # Security Check: Verify password before allowing change!
                    user = self.db.authenticate_user_login(username, password)

                    if user:
                        success = self.db.update_user_face(username, new_face_data)
                        if success:
                            response = {"status": "SUCCESS", "message": "Face Updated"}
                        else:
                            response = {"status": "FAIL", "message": "Database Error"}
                    else:
                        response = {"status": "DENIED", "message": "Bad Password"}

                # CASE 5: Get Active Renters (For Face-First Login)
                elif action == "FETCH_ACTIVE_USERS":
                    # In a real app, we would verify the station_id here
                    active_users = self.db.get_active_renters()
                    response = {"status": "SUCCESS", "users": active_users}

                # CASE 6: Live Time Deduction
                elif action == "DEDUCT_TIME":
                    username = request.get("username")
                    seconds = request.get("seconds")
                    self.db.deduct_user_time(username, seconds)
                    # We don't necessarily need to send a response for every heartbeat
                    # to keep traffic low, but let's send a simple OK for now.
                    response = {"status": "SUCCESS"}

                # CASE 7: Update Face Data (Multi-Angle)
                elif action == "UPDATE_FACE":
                    username = request.get("username")
                    password = request.get("password")
                    face_data = request.get("face_data")

                    # 1. Verify credentials first
                    user = self.db.validate_user(username, password)

                    if user:
                        # 2. Update the face data
                        if self.db.update_user_face(username, face_data):
                            response = {"status": "SUCCESS"}
                        else:
                            response = {"status": "FAILURE", "message": "Database Error"}
                    else:
                        response = {"status": "FAILURE", "message": "Invalid Password"}

                # CASE 8: Add Rented Time
                elif action == "ADD_TIME":
                    username = request.get("username")
                    minutes = request.get("minutes")

                    if self.db.add_time(username, minutes):
                        response = {"status": "SUCCESS"}
                        print(f"💰 Added {minutes} mins for {username}")
                    else:
                        response = {"status": "FAILURE"}

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