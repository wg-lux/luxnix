import random
import string
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
import os
import secrets

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
        password = ''.join(secrets.choice(characters) for _ in range(self.length))
        # Ensure the password contains at least one digit
        if not any(c.isdigit() for c in password):
            password = list(password)
            password[0] = secrets.choice(string.digits)
            secrets.SystemRandom().shuffle(password)
            password = ''.join(password)
        return password

    def generate_random_passphrase(self, num_words=4):
        """
        Generate a random passphrase consisting of a specified number of words.

        :param num_words: Number of words in the passphrase.
        :return: A random passphrase string.
        """
        try:
            with open('/usr/share/dict/words') as f:
                words = f.read().splitlines()
        except FileNotFoundError:
            words = ["example", "word", "list", "for", "testing"]
        return ' '.join(secrets.choice(words) for _ in range(num_words))

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
            backend=default_backend()
        )
        key = kdf.derive(password.encode())
        return base64.urlsafe_b64encode(salt + key).decode()

class ReadablePasswordGenerator(PasswordGenerator):
    """
    A class to generate readable passwords using alternating consonants and vowels.
    """

    def __init__(self, length=12, security_level=1):
        """
        Initialize the ReadablePasswordGenerator with a specified length and security level.

        :param length: Length of the password to be generated.
        :param security_level: Security level (not used in current implementation).
        """
        super().__init__(length, security_level)

    def generate_readable_password(self):
        """
        Generate a readable password using alternating consonants and vowels.

        :return: A readable password string.
        """
        vowels = 'aeiou'
        consonants = ''.join(set(string.ascii_lowercase) - set(vowels))
        password = []
        for i in range(self.length):
            if i % 2 == 0:
                password.append(secrets.choice(consonants))
            else:
                password.append(secrets.choice(vowels))
        return ''.join(password)
