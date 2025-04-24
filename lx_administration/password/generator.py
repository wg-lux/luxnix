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
from pydantic import BaseModel, field_validator, model_validator
from typing import Union, Tuple, Optional, List, Literal
from passlib.hash import sha512_crypt


class PasswordGenerator(BaseModel):
    """Password and passphrase generator with configurable settings."""

    mode: Union[Literal["password"], Literal["passphrase"]] = "passphrase"
    key_length: int = 32  # Default length for passwords
    min_length: int = 12  # Minimum length for passwords
    num_words: int = 4  # Default number of words for passphrases
    require_upper: bool = True
    require_lower: bool = True
    require_digits: bool = True
    require_special: bool = False

    @model_validator(mode="after")
    def validate_length(self) -> "PasswordGenerator":
        """Ensure password length meets minimum requirements."""
        if self.mode == "password" and self.key_length < self.min_length:
            raise ValueError(f"Password length must be at least {self.min_length}")
        return self

    def generate_random_password(self) -> str:
        """Generate a random password with required complexity."""
        characters = ""
        if self.require_upper:
            characters += string.ascii_uppercase
        if self.require_lower:
            characters += string.ascii_lowercase
        if self.require_digits:
            characters += string.digits
        if self.require_special:
            characters += string.punctuation

        # Generate initial password
        password = [secrets.choice(characters) for _ in range(self.key_length)]

        # Ensure all required character types are included
        requirements = []
        if self.require_upper:
            requirements.append((string.ascii_uppercase, any))
        if self.require_lower:
            requirements.append((string.ascii_lowercase, any))
        if self.require_digits:
            requirements.append((string.digits, any))
        if self.require_special:
            requirements.append((string.punctuation, any))

        # Replace characters if requirements not met
        for char_set, check_func in requirements:
            if not check_func(c in char_set for c in password):
                pos = secrets.randbelow(self.key_length)
                password[pos] = secrets.choice(char_set)

        # Shuffle the final password
        secrets.SystemRandom().shuffle(password)
        return "".join(password)

    def generate_random_passphrase(self) -> str:
        """Generate a random passphrase with improved word selection."""
        fake = Faker()
        words = []
        total_words = self.num_words

        # Reduce word count if we need to add digits/special chars
        if self.require_digits:
            total_words -= 1
        if self.require_special:
            total_words -= 1

        while len(words) < total_words:
            word = fake.word()
            # Ensure word meets minimum quality standards
            if len(word) >= 3 and word.isalpha():
                words.append(word)

        # Add required elements
        if self.require_digits:
            words.append(str(secrets.randbelow(1000)))
        if self.require_special:
            words.append(secrets.choice(string.punctuation))

        # Shuffle words
        secrets.SystemRandom().shuffle(words)
        return "-".join(words)

    def create_password_hash(self, password: str) -> str:
        """
        Create a password hash using SHA-512 (compatible with NixOS).
        Uses passlib's sha512_crypt which is compatible with crypt's SHA512 format.
        """
        return sha512_crypt.hash(password)

    def create_user_passphrase_file(self, username, hostname, n_words=4):
        # TODO rm n_words
        passphrase = self.generate_random_passphrase()
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
        with open(raw_path, "w", encoding="utf-8") as raw_file:
            raw_file.write(passphrase)

        with open(hashed_path, "w", encoding="utf-8") as hashed_file:
            hashed_file.write(hashed)  #

    def verify_password_hash(self, password: str, password_hash: str) -> bool:
        """
        Verify a password against a given hash using SHA-512.
        """
        return sha512_crypt.verify(password, password_hash)

    def pipe(self) -> List[Tuple[str, str]]:
        """Generate password/passphrase and its hash."""
        if self.mode == "password":
            result = self.generate_random_password()
        else:
            result = self.generate_random_passphrase()

        hashed_result = self.create_password_hash(result)
        return [("password", result), ("password_hash", hashed_result)]
