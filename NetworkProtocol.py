import json
import struct

class Protocol:
    def __init__(self, sock, crypter):
        self.sock = sock
        self.crypter = crypter

    def create_message(self, data):
        """Serializes, encrypts, attaches a length header, and sends."""
        # 1. Serialize Dictionary to JSON String, then to raw bytes
        json_string = json.dumps(data)
        raw_bytes = json_string.encode('utf-8')

        # 2. Encrypt the bytes using the injected Crypter
        encrypted_bytes = self.crypter.encrypt(raw_bytes)

        # 3. Create the 4-byte header indicating the length of the encrypted payload
        header = struct.pack('I', len(encrypted_bytes))

        # 4. Send it over the socket
        self.sock.sendall(header + encrypted_bytes)

    def get_message(self):
        """Reads header, fetches payload chunks, decrypts, and deserializes."""
        # 1. Read the 4-byte header
        header = self.sock.recv(4)
        if not header:
            return None
        msg_length = struct.unpack('I', header)[0]

        # 2. Read the body in chunks based on the header length
        encrypted_data = b""
        while len(encrypted_data) < msg_length:
            chunk_size = min(4096, msg_length - len(encrypted_data))
            packet = self.sock.recv(chunk_size)
            if not packet:
                return None
            encrypted_data += packet

        # 3. Decrypt the received bytes
        decrypted_bytes = self.crypter.decrypt(encrypted_data)

        # 4. Decode bytes back to string and parse JSON
        return json.loads(decrypted_bytes.decode('utf-8'))