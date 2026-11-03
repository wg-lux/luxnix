from datetime import datetime
import os
import hashlib
import math
from functools import lru_cache
from pathlib import Path
import secrets
import shutil
import string

from passlib.hash import sha512_crypt  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from ..permissions import PRIVATE_FILE_MODE, ensure_private_directory
from .files import write_private_text


MIN_PASSPHRASE_ENTROPY_BITS = 128
WORDLIST_SHA256 = "8f5ca830b8bffb6fe39c9736c024a00a6a6411adb3f83a9be8bfeeb6e067ae69"


@lru_cache(maxsize=1)
def passphrase_words() -> tuple[str, ...]:
    """Load the pinned EFF list, refusing missing or altered package data."""
    data = Path(__file__).with_name("eff_short_wordlist_1.txt").read_bytes()
    if hashlib.sha256(data).hexdigest() != WORDLIST_SHA256:
        raise ValueError("Passphrase wordlist integrity check failed")
    words = tuple(line.split()[1] for line in data.decode().splitlines())
    if (len(words) != 1296 or len(set(words)) != len(words)
            or not all(w.isascii() and w.replace("-", "").isalpha()
                       and w.islower() for w in words)):
        raise ValueError("Invalid passphrase wordlist")
    return words


class PasswordGenerator(BaseModel):
    """Password and passphrase generator with configurable settings."""

    mode: Literal["password", "passphrase"] = "passphrase"
    key_length: int = 32
    min_length: int = Field(default=12, ge=1)
    num_words: int = Field(default=4, ge=1)
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

    @property
    def passphrase_word_count(self) -> int:
        """Effective minimum word count; decorations never reduce entropy."""
        entropy_words = math.ceil(
            MIN_PASSPHRASE_ENTROPY_BITS / math.log2(len(passphrase_words()))
        )
        return max(self.num_words, entropy_words)

    @property
    def passphrase_entropy_bits(self) -> float:
        """Conservative lower bound from uniform words alone, excluding suffixes."""
        return self.passphrase_word_count * math.log2(len(passphrase_words()))

    def generate_random_passphrase(self) -> str:
        """Choose at least 128 bits of words with the OS-backed secrets RNG.

        num_words is a minimum. Extra words satisfy min_length. Uppercase is a
        reversible first-word transformation; remaining words stay lowercase.
        Digits and punctuation append without replacing any random word.
        """
        vocabulary = passphrase_words()
        words = [secrets.choice(vocabulary) for _ in range(self.passphrase_word_count)]
        if self.require_upper:
            words[0] = words[0].capitalize()
        suffix = []
        if self.require_digits:
            suffix.append(f"{secrets.randbelow(1000):03d}")
        if self.require_special:
            suffix.append(secrets.choice(string.punctuation.replace("-", "")))
        while len(" ".join(words + suffix)) < self.min_length:
            words.append(secrets.choice(vocabulary))
        return " ".join(words + suffix)

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
