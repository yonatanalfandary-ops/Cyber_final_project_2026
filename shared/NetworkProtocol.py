import json
import struct


class Protocol:
    """
    Length-prefixed JSON messaging protocol over a TCP socket.

    Every message is sent as a 4-byte little-endian length header followed
    by an encrypted JSON payload. The crypter is injected so the same
    protocol class can be used with NoCrypter during the handshake and with
    a SymmetricCrypter once the secure channel has been established.
    """

    def __init__(self, sock, crypter):
        self.sock = sock
        self.crypter = crypter

    def create_and_send_message(self, data):
        """Serialises, encrypts, prefixes with a length header, and sends."""
        # Serialise the dictionary to a JSON string and then to raw bytes.
        json_string = json.dumps(data)
        raw_bytes = json_string.encode('utf-8')

        # Encrypt the payload using the currently configured crypter.
        encrypted_bytes = self.crypter.encrypt(raw_bytes)

        # Build a 4-byte length header for the encrypted payload.
        header = struct.pack('I', len(encrypted_bytes))

        # Transmit the header followed by the payload in a single send.
        self.sock.sendall(header + encrypted_bytes)

    def get_message(self):
        """Reads the length header, fetches the payload, decrypts, and deserialises."""
        # Read exactly 4 bytes for the length header, looping until they all arrive.
        header = b""
        while len(header) < 4:
            chunk = self.sock.recv(4 - len(header))
            if not chunk:
                return None
            header += chunk
        msg_length = struct.unpack('I', header)[0]

        # Read the payload in chunks until we have the full message.
        encrypted_data = b""
        while len(encrypted_data) < msg_length:
            chunk_size = min(4096, msg_length - len(encrypted_data))
            packet = self.sock.recv(chunk_size)
            if not packet:
                return None
            encrypted_data += packet

        # Decrypt the payload and parse it back into a Python dictionary.
        decrypted_bytes = self.crypter.decrypt(encrypted_data)

        return json.loads(decrypted_bytes.decode('utf-8'))