import socket
from NetworkProtocol import Protocol
from Crypters import NoCrypter


class NetworkClient:
    """Handles all communication with the Central Server."""

    def __init__(self, server_ip="127.0.0.1", server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.protocol = None  # NEW: Hold the protocol instance

    def connect(self):
        """Establishes connection and sets up Protocol."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))

            # --- NEW: Initialize Protocol with NoCrypter ---
            crypter = NoCrypter()
            self.protocol = Protocol(self.sock, crypter)

            print(f"✅ Connected to Server at {self.server_ip}:{self.server_port}")
            return True
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            return False

    def send_request(self, action, data=None):
        """Sends a dictionary to the server and waits for a reply."""
        if not self.protocol:
            print("⚠ Error: Not connected to server.")
            return None

        req = {"action": action}
        if data:
            req.update(data)

        try:
            # --- NEW: Let the Protocol do all the work! ---
            self.protocol.create_message(req)
            response = self.protocol.get_message()
            return response

        except Exception as e:
            print(f"❌ Communication Error: {e}")
            self.close()
            return None

    def close(self):
        if self.sock:
            self.sock.close()