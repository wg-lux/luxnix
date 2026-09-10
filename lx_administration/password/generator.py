from datetime import datetime
import os
import secrets
import shutil
import string

from faker import Faker
from passlib.hash import sha512_crypt  # type: ignore[import-untyped]
from pydantic import BaseModel, model_validator
from typing import Literal

from ..permissions import PRIVATE_FILE_MODE, ensure_private_directory
from .files import write_private_text


class PasswordGenerator(BaseModel):
    """Password and passphrase generator with configurable settings."""

    mode: Literal["password", "passphrase"] = "passphrase"
    key_length: int = 32
    min_length: int = 12
    num_words: int = 4
    require_upper: bool = True
    require_lower: bool = True
    require_digits: bool = True
    require_special: bool = False

    @model_validator(mode="after")
    def validate_configuration(self) -> "PasswordGenerator":
        """Reject configurations that cannot produce the requested secret."""
        if self.mode == "password":
            character_sets = self._password_character_sets()
            if not character_sets:
                raise ValueError("Password generation requires a character class")
            minimum_length = max(self.min_length, len(character_sets))
            if self.key_length < minimum_length:
                raise ValueError(
                    f"Password length must be at least {minimum_length}"
                )
        else:
            required_elements = int(self.require_digits) + int(self.require_special)
            minimum_words = max(1, required_elements)
            if self.num_words < minimum_words:
                raise ValueError(
                    f"Passphrase word count must be at least {minimum_words}"
                )
        return self

    def _password_character_sets(self) -> tuple[str, ...]:
        """Return the enabled character sets in a stable order."""
        character_sets = (
            (self.require_upper, string.ascii_uppercase),
            (self.require_lower, string.ascii_lowercase),
            (self.require_digits, string.digits),
            (self.require_special, string.punctuation),
        )
        return tuple(characters for enabled, characters in character_sets if enabled)

    def generate_random_password(self) -> str:
        """Generate a random password with required complexity."""
        character_sets = self._password_character_sets()
        all_characters = "".join(character_sets)

        password = [secrets.choice(characters) for characters in character_sets]
        password.extend(
            secrets.choice(all_characters)
            for _ in range(self.key_length - len(password))
        )
        secrets.SystemRandom().shuffle(password)
        return "".join(password)

    def generate_random_passphrase(self) -> str:
        """Generate a random passphrase with improved word selection."""
        fake = Faker()
        words: list[str] = []
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

    def create_user_passphrase_file(
        self, username: str, hostname: str, n_words: int | None = None
    ) -> None:
        generator = self
        if n_words is not None:
            settings = self.model_dump() | {"num_words": n_words}
            generator = type(self).model_validate(settings)

        passphrase = generator.generate_random_passphrase()
        hashed = self.create_password_hash(passphrase)

        timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
        raw_path = f"./secrets/user-passwords/{username}@{hostname}_raw"
        hashed_path = f"./secrets/user-passwords/{username}@{hostname}_hashed"
        archived_raw = f"./secrets/archived/{username}@{hostname}_raw_{timestamp}"
        archived_hashed = f"./secrets/archived/{username}@{hostname}_hashed_{timestamp}"

        for src, dest in [(raw_path, archived_raw), (hashed_path, archived_hashed)]:
            if os.path.exists(src):
                ensure_private_directory(os.path.dirname(dest))
                shutil.move(src, dest)
                os.chmod(dest, PRIVATE_FILE_MODE)

        ensure_private_directory(os.path.dirname(raw_path))
        write_private_text(raw_path, passphrase)
        write_private_text(hashed_path, hashed)

    def verify_password_hash(self, password: str, password_hash: str) -> bool:
        """
        Verify a password against a given hash using SHA-512.
        """
        return sha512_crypt.verify(password, password_hash)

    def pipe(self) -> list[tuple[str, str]]:
        """Generate password/passphrase and its hash."""
        if self.mode == "password":
            result = self.generate_random_password()
        else:
            result = self.generate_random_passphrase()

        hashed_result = self.create_password_hash(result)
        return [("password", result), ("password_hash", hashed_result)]
