
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
from lx_admin.managers.helpers.generate_sops_age_key import generate_sops_age_key

def generate_key_pair(key_type="rsa"):
    """
    Generates a private and public key pair for rsa, ed25519, or sops_age.

    Args:
        key_type (str): Type of key to generate ("rsa", "ed25519", "sops_age").

    Returns:
        tuple: (private_key_pem_or_text, public_key_pem_or_text)
    """
    if key_type == "rsa":
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        return private_key_pem, public_key_pem

    elif key_type == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        return private_key_pem, public_key_pem

    elif key_type == "sops_age":
        return generate_sops_age_key()

    else:
        raise ValueError(f"Unsupported key type: {key_type}")