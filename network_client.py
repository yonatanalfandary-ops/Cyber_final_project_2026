import socket
import os
import sys
from NetworkProtocol import Protocol
from Crypters import NoCrypter, ASymetricCrypter, SymetricCrypter


class NetworkClient:
    def __init__(self, server_ip="10.0.0.24", server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.protocol = None

    def connect(self):
        """Establishes connection and performs Hybrid Encryption Handshake."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.server_ip, self.server_port))
            print(f"✅ Connected to Server at {self.server_ip}:{self.server_port}")

            # --- START HANDSHAKE ---
            # 1. Start with plaintext to receive the Server's Public Key
            self.protocol = Protocol(self.sock, NoCrypter())

            # 2. Wait for Server to send its Public Key
            msg = self.protocol.get_message()
            if not msg or msg.get("action") != "HANDSHAKE_PUB_KEY":
                print("❌ Encryption Handshake failed: Did not receive Public Key.")
                return False

            # Convert the hex string back into raw bytes
            pub_key_bytes = bytes.fromhex(msg.get("pub_key_hex"))

            # 3. Load Server's Public Key into our Asymmetric Crypter
            asym_crypter = ASymetricCrypter(public_key_bytes=pub_key_bytes)

            # 4. Generate our blazing-fast Symmetric Key
            sym_crypter = SymetricCrypter()
            sym_key_bytes = sym_crypter.get_key()

            # 5. Encrypt our Symmetric Key using the Server's Public Key
            encrypted_sym_key = asym_crypter.encrypt(sym_key_bytes)

            # 6. Send the encrypted Symmetric Key back to the Server (as a hex string)
            self.protocol.create_and_send_message({
                "action": "HANDSHAKE_SYM_KEY",
                "sym_key_hex": encrypted_sym_key.hex()
            })

            # 7. UPGRADE PROTOCOL: Swap NoCrypter for our new SymetricCrypter!
            self.protocol.crypter = sym_crypter
            print("🔐 Secure AES Encrypted Connection Established!")
            return True

        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            return False

    def send_request(self, action, data=None):
        if not self.protocol:
            return None

        req = {"action": action}
        if data: req.update(data)

        try:
            self.protocol.create_and_send_message(req)
            response = self.protocol.get_message()

            # --- THE KILL SWITCH INTERCEPT ---
            if response and response.get("action") == "COMMAND_UNREGISTER":
                print("💀 KILL SWITCH RECEIVED. Remote wipe triggered.")
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'station_config.json')
                if os.path.exists(config_path):
                    try:
                        os.remove(config_path)
                    except:
                        pass
                sys.exit(0)  # Terminate entirely

            return response

        except Exception as e:
            self.close()
            return None

    def close(self):
        if self.sock: self.sock.close()