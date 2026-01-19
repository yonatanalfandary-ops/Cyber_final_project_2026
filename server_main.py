import socket
import threading
import json
import struct
from database_manager import DatabaseManager

# Configuration
SERVER_IP = "0.0.0.0"  # Listen on all available network interfaces
SERVER_PORT = 5000  # The port we open for clients


class RentalServer:
    def __init__(self):
        self.db = DatabaseManager()  # The server owns the DB connection now
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((SERVER_IP, SERVER_PORT))
        self.server_socket.listen(5)  # Allow up to 5 pending connections
        print(f"✅ SERVER STARTED on {SERVER_IP}:{SERVER_PORT}")
        print("Waiting for clients...")

    def send_json(self, client_socket, data):
        """
        Helper to send JSON data reliably.
        We prefix the message with its length (4 bytes) so the client knows how much to read.
        """
        try:
            message = json.dumps(data).encode('utf-8')
            # 'I' = unsigned int (4 bytes) representing the length
            header = struct.pack('I', len(message))
            client_socket.sendall(header + message)
        except Exception as e:
            print(f"❌ Send Error: {e}")

    def handle_client(self, client_socket, addr):
        """
        This runs in a separate thread for EACH connected computer.
        """
        print(f"🔗 New Connection from: {addr}")

        try:
            while True:
                # 1. Read the header (4 bytes) to get message length
                header = client_socket.recv(4)
                if not header: break  # Client disconnected

                msg_length = struct.unpack('I', header)[0]

                # 2. Read the actual message based on length
                data = b""
                while len(data) < msg_length:
                    packet = client_socket.recv(4096)
                    if not packet: break
                    data += packet

                if not data: break

                # 3. Process the Request
                request = json.loads(data.decode('utf-8'))
                action = request.get("action")
                print(f"📩 Request from {addr}: {action}")

                response = {"status": "ERROR", "message": "Unknown Action"}

                # --- ROUTING LOGIC ---
                if action == "FETCH_USERS":
                    users = self.db.get_all_users()
                    response = {"status": "SUCCESS", "users": users}

                elif action == "CHECK_RENTAL":
                    # Placeholder for future logic
                    user_id = request.get("user_id")
                    response = {"status": "SUCCESS", "rented": True, "time_left": 60}

                # 4. Send Response
                self.send_json(client_socket, response)

        except Exception as e:
            print(f"⚠ Connection Error {addr}: {e}")
        finally:
            print(f"❌ Disconnected: {addr}")
            client_socket.close()

    def start(self):
        while True:
            client_sock, addr = self.server_socket.accept()
            # Spin up a new thread for this client so others aren't blocked
            client_handler = threading.Thread(
                target=self.handle_client,
                args=(client_sock, addr)
            )
            client_handler.daemon = True  # Kills thread if server stops
            client_handler.start()


if __name__ == "__main__":
    server = RentalServer()
    server.start()