import socket
import json
import struct


class NetworkClient:
    """
    Handles all communication with the Central Server.
    """

    def __init__(self, server_ip="127.0.0.1", server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None

    def connect(self):
        """Establishes connection to the server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))
            print(f"✅ Connected to Server at {self.server_ip}:{self.server_port}")
            return True
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            return False

    def send_request(self, action, data=None):
        """
        Sends a JSON command to the server and waits for a reply.
        Example: send_request("FETCH_USERS")
        """
        if not self.sock:
            print("⚠ Error: Not connected to server.")
            return None

        req = {"action": action}
        if data:
            req.update(data)

        try:
            # 1. Serialize Data to JSON
            json_payload = json.dumps(req).encode('utf-8')

            # 2. Create Header (4 bytes containing the size of the message)
            # 'I' = unsigned int (4 bytes)
            header = struct.pack('I', len(json_payload))

            # 3. Send Header + Data
            self.sock.sendall(header + json_payload)

            # 4. Receive Response Header
            resp_header = self.sock.recv(4)
            if not resp_header:
                return None

            resp_length = struct.unpack('I', resp_header)[0]

            # 5. Receive Response Body (in chunks if large)
            resp_data = b""
            while len(resp_data) < resp_length:
                chunk = self.sock.recv(4096)
                if not chunk: break
                resp_data += chunk

            # 6. Decode
            return json.loads(resp_data.decode('utf-8'))

        except Exception as e:
            print(f"❌ Communication Error: {e}")
            self.close()
            return None

    def close(self):
        if self.sock:
            self.sock.close()