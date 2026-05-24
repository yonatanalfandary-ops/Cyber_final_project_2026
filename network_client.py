import socket
import os
import sys
from NetworkProtocol import Protocol
from Crypters import NoCrypter, AsymmetricCrypter, SymmetricCrypter


class NetworkClient:
    """
    TCP client wrapper that handles the secure handshake with the server
    and exposes a simple request/response interface for the rest of the
    client application.
    """

    def __init__(self, server_ip="10.0.0.24", server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.protocol = None

    def connect(self):
        """
        Establishes a TCP connection and performs the hybrid encryption
        handshake. The server sends its RSA public key, the client generates
        a symmetric (Fernet) session key and returns it encrypted with that
        public key, and from that point on all traffic is symmetrically
        encrypted.
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))
            print(f"Connected to Server at {self.server_ip}:{self.server_port}")

            # Begin handshake in plaintext mode so the public key can be received.
            self.protocol = Protocol(self.sock, NoCrypter())

            # Step 1: wait for the server to send its RSA public key.
            msg = self.protocol.get_message()
            if not msg or msg.get("action") != "HANDSHAKE_PUB_KEY":
                print("Encryption Handshake failed: Did not receive Public Key.")
                return False

            # The key is transmitted as a hex string; convert it back to raw bytes.
            pub_key_bytes = bytes.fromhex(msg.get("pub_key_hex"))

            # Step 2: load the server's public key into an AsymmetricCrypter.
            asym_crypter = AsymmetricCrypter(public_key_bytes=pub_key_bytes)

            # Step 3: generate a fresh symmetric session key.
            sym_crypter = SymmetricCrypter()
            sym_key_bytes = sym_crypter.get_key()

            # Step 4: wrap the symmetric key with the server's public key.
            encrypted_sym_key = asym_crypter.encrypt(sym_key_bytes)

            # Step 5: send the wrapped symmetric key back to the server.
            self.protocol.create_and_send_message({
                "action": "HANDSHAKE_SYM_KEY",
                "sym_key_hex": encrypted_sym_key.hex()
            })

            # Step 6: swap the crypter on the protocol to the symmetric one so
            # all subsequent messages are sent over the secure channel.
            self.protocol.crypter = sym_crypter
            print("Secure AES Encrypted Connection Established!")
            return True

        except Exception as e:
            print(f"Connection Failed: {e}")
            return False

    def send_request(self, action, data=None):
        """
        Sends a request to the server and returns the parsed response, or
        None if the connection has failed. Also intercepts the kill-switch
        command and terminates the client immediately if it is received.
        """
        if not self.protocol:
            return None

        req = {"action": action}
        if data:
            req.update(data)

        try:
            self.protocol.create_and_send_message(req)
            response = self.protocol.get_message()

            # Kill-switch intercept: if the server tells us to unregister, wipe
            # the local station configuration and terminate the process.
            if response and response.get("action") == "COMMAND_UNREGISTER":
                print("KILL SWITCH RECEIVED. Remote wipe triggered.")
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'station_config.json')
                if os.path.exists(config_path):
                    try:
                        os.remove(config_path)
                    except:
                        pass
                sys.exit(0)

            return response

        except Exception as e:
            self.close()
            return None

    def close(self):
        """Closes the underlying socket if one is open."""
        if self.sock:
            self.sock.close()