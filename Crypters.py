from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization


class NoCrypter:
    def __init__(self):
        pass

    def encrypt(self, data: bytes) -> bytes: 
        return data

    def decrypt(self, data: bytes) -> bytes: 
        return data


class SymetricCrypter(NoCrypter):
    def __init__(self, key=None):
        # Fernet is a secure implementation of AES-128 encryption
        if key is None:
            self.key = Fernet.generate_key()
        else:
            self.key = key
        self.fernet = Fernet(self.key)

    def get_key(self) -> bytes:
        return self.key

    def encrypt(self, data: bytes) -> bytes: 
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes: 
        return self.fernet.decrypt(data)


class ASymetricCrypter(NoCrypter):
    def __init__(self, private_key=None, public_key_bytes=None):
        """
        Server will generate the private_key.
        Client will initialize this by passing the server's public_key_bytes.
        """
        self.private_key = private_key
        self.public_key = None

        # 1. Server Mode: Generate brand new keys
        if private_key is None and public_key_bytes is None:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            self.public_key = self.private_key.public_key()

        # 2. Client Mode: Load the Server's public key
        elif public_key_bytes is not None:
            self.public_key = serialization.load_pem_public_key(public_key_bytes)

    def get_public_key_bytes(self) -> bytes:
        """Exports the public key so it can be sent over the network."""
        if not self.public_key:
            return b""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def encrypt(self, data: bytes) -> bytes: 
        """Uses the PUBLIC key to lock data. (Client uses this on the Symmetric Key)"""
        if not self.public_key:
            raise ValueError("Public key not loaded!")

        return self.public_key.encrypt(
            data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def decrypt(self, data: bytes) -> bytes: 
        """Uses the PRIVATE key to unlock data. (Server uses this to read the Symmetric Key)"""
        if not self.private_key:
            raise ValueError("Private key not loaded! Clients cannot decrypt asymmetric data.")

        return self.private_key.decrypt(
            data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )