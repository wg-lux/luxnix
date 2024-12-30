import string
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
from cryptography.hazmat.primitives import hashes  # type: ignore
from cryptography.hazmat.backends import default_backend  # type: ignore
import base64
import os
import secrets
from faker import Faker
from datetime import datetime
import shutil


class PasswordGenerator:
    """
    A class to generate random passwords and passphrases, and create password hashes.
    """

    def __init__(self, length=12, security_level=1):
        """
        Initialize the PasswordGenerator with a specified length and security level.

        :param length: Length of the password to be generated.
        :param security_level: Security level (not used in current implementation).
        """
        self.length = length
        self.security_level = security_level

    def generate_random_password(self):
        """
        Generate a random password containing letters, digits, and punctuation.

        :return: A random password string.
        """
        characters = string.ascii_letters + string.digits + string.punctuation
        password = "".join(secrets.choice(characters) for _ in range(self.length))
        # Ensure the password contains at least one digit
        if not any(c.isdigit() for c in password):
            password = list(password)
            password[0] = secrets.choice(string.digits)
            secrets.SystemRandom().shuffle(password)
            password = "".join(password)
        return password

    def generate_random_passphrase(self, num_words=4):
        """
        Generate a random passphrase consisting of a specified number of words.

        :param num_words: Number of words in the passphrase.
        :return: A random passphrase string.
        """
        fake = Faker()
        words = [fake.word() for _ in range(num_words)]
        return "-".join(words)

    def create_password_hash(self, password):
        """
        Create a hash of the given password using PBKDF2HMAC.

        :param password: The password to hash.
        :return: A base64 encoded hash of the password.
        """
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        key = kdf.derive(password.encode())
        return base64.urlsafe_b64encode(salt + key).decode()

    def create_user_passphrase_file(self, username, hostname, n_words=4):
        passphrase = self.generate_random_passphrase(n_words)
        hashed = self.create_password_hash(passphrase)

        timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
        raw_path = f"./secrets/user-passwords/{username}@{hostname}_raw"
        hashed_path = f"./secrets/user-passwords/{username}@{hostname}_hashed"
        archived_raw = f"./secrets/archived/{username}@{hostname}_raw_{timestamp}"
        archived_hashed = f"./secrets/archived/{username}@{hostname}_hashed_{timestamp}"

        for src, dest in [(raw_path, archived_raw), (hashed_path, archived_hashed)]:
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(src, dest)

        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        with open(raw_path, "w") as raw_file:
            raw_file.write(passphrase)

        with open(hashed_path, "w") as hashed_file:
            hashed_file.write(hashed)
