from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization


class NoCrypter:
    """
    Pass-through crypter used before the encryption handshake completes.
    Returns the data unmodified for both encrypt and decrypt operations.
    """

    def __init__(self):
        pass

    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


class SymmetricCrypter(NoCrypter):
    """
    Symmetric encryption wrapper backed by Fernet (AES-128 in CBC mode with
    HMAC authentication). Used for all post-handshake traffic on both the
    client and server sides.
    """

    def __init__(self, key=None):
        # Generate a fresh key if none is provided; otherwise reuse the
        # supplied key (the server reuses the key received from the client).
        if key is None:
            self.key = Fernet.generate_key()
        else:
            self.key = key
        self.fernet = Fernet(self.key)

    def get_key(self) -> bytes:
        """Returns the raw symmetric key bytes."""
        return self.key

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self.fernet.decrypt(data)


class AsymmetricCrypter(NoCrypter):
    """
    RSA-2048 asymmetric crypter used only during the initial handshake to
    securely transport the symmetric session key from client to server.

    The server instantiates this class with no arguments to generate a new
    key pair; the client instantiates it with the server's public key bytes
    so it can encrypt its symmetric key for transit.
    """

    def __init__(self, private_key=None, public_key_bytes=None):
        self.private_key = private_key
        self.public_key = None

        # Server mode: generate a fresh RSA key pair.
        if private_key is None and public_key_bytes is None:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            self.public_key = self.private_key.public_key()

        # Client mode: load the server's public key from the bytes received
        # during the handshake.
        elif public_key_bytes is not None:
            self.public_key = serialization.load_pem_public_key(public_key_bytes)

    def get_public_key_bytes(self) -> bytes:
        """
        Serialises the public key into PEM-encoded bytes so it can be
        transmitted to the client over the network.
        """
        if not self.public_key:
            return b""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def encrypt(self, data: bytes) -> bytes:
        """
        Encrypts data with the public key using OAEP padding.
        Called by the client to wrap the symmetric session key before
        sending it to the server.
        """
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
        """
        Decrypts data with the private key using OAEP padding.
        Only the server holds the private key, so only the server can
        recover the symmetric session key from the handshake payload.
        """
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