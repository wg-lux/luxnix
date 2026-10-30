import string
import stat
import unittest

from lx_administration.password import PasswordGenerator


class TestPasswordGenerator(unittest.TestCase):
    def setUp(self):
        """Set up test cases with specific configurations."""
        self.password_gen = PasswordGenerator(
            mode="password",
            key_length=32,
        )
        # Configure passphrase generator to match test expectations
        self.passphrase_gen = PasswordGenerator(
            mode="passphrase",
            num_words=4,
            require_digits=False,  # Disable for consistent word count
            require_special=False,  # Disable for consistent word count
        )

    def test_generate_random_password(self):
        """Test password generation with all requirements."""
        password = self.password_gen.generate_random_password()

        # Test length
        self.assertEqual(len(password), 32)

        # Test character requirements
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))

    def test_password_minimum_length(self):
        """Test minimum length validation."""
        with self.assertRaises(ValueError):
            PasswordGenerator(mode="password", key_length=8)

    def test_password_requires_at_least_one_character_class(self):
        """Reject password settings that cannot produce a character."""
        with self.assertRaisesRegex(ValueError, "requires a character class"):
            PasswordGenerator(
                mode="password",
                require_upper=False,
                require_lower=False,
                require_digits=False,
                require_special=False,
            )

    def test_password_always_contains_each_required_character_class(self):
        """Guarantee every enabled class without replacement collisions."""
        generator = PasswordGenerator(mode="password", require_special=True)

        password = generator.generate_random_password()

        self.assertTrue(any(character.isupper() for character in password))
        self.assertTrue(any(character.islower() for character in password))
        self.assertTrue(any(character.isdigit() for character in password))
        self.assertTrue(any(character in string.punctuation for character in password))

    def test_generate_random_passphrase(self):
        """
        Test the generate_random_passphrase method.
        """
        passphrase = self.passphrase_gen.generate_random_passphrase()
        self.assertEqual(len(passphrase.split("-")), 4)

    def test_passphrase_rejects_fewer_slots_than_required_elements(self):
        """Reject a word count that cannot fit digits and special characters."""
        with self.assertRaisesRegex(ValueError, "word count must be at least 2"):
            PasswordGenerator(
                mode="passphrase",
                num_words=1,
                require_digits=True,
                require_special=True,
            )

    def test_pipe_password_mode(self):
        """Test the pipe method in password mode."""
        result = self.password_gen.pipe()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "password")
        self.assertEqual(result[1][0], "password_hash")
        self.assertEqual(len(result[0][1]), 32)  # Updated to match new default length

    def test_pipe_passphrase_mode(self):
        """Test the pipe method in passphrase mode."""
        gen = PasswordGenerator(
            mode="passphrase", num_words=4, require_digits=False, require_special=False
        )
        result = gen.pipe()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "password")
        self.assertEqual(result[1][0], "password_hash")
        self.assertEqual(len(result[0][1].split("-")), 4)

    def test_create_password_hash(self):
        """
        Test the create_password_hash method to ensure it generates a valid hash for
        a given password.
        """
        password = "testpassword"
        password_hash = self.password_gen.create_password_hash(password)
        self.assertIsInstance(password_hash, str)
        self.assertGreater(len(password_hash), 0)

    def test_verify_password_hash(self):
        """
        Test the verify_password_hash method to ensure it correctly verifies a password
        against a hash.
        """
        password = "testpassword"
        password_hash = self.password_gen.create_password_hash(password)
        self.assertTrue(self.password_gen.verify_password_hash(password, password_hash))
        self.assertFalse(
            self.password_gen.verify_password_hash("wrongpassword", password_hash)
        )

    def test_nixos_password_hash_compatibility(self):
        """
        Test that generated hashes work in NixOS user password files.
        NixOS expects a crypt(3) compatible hash format starting with '$6$' (SHA-512).
        Format: $6$rounds=<rounds>$<salt>$<hash>
        """
        password = "test-password-123"
        password_hash = self.password_gen.create_password_hash(password)

        # Verify hash starts with $6$ (SHA-512)
        self.assertTrue(
            password_hash.startswith("$6$"),
            f"Hash should start with $6$ (SHA-512), got: {password_hash[:10]}...",
        )

        # Split hash parts
        parts = password_hash.split("$")
        self.assertEqual(
            len(parts), 5, "Hash should have format $6$rounds=<rounds>$<salt>$<hash>"
        )
        self.assertEqual(parts[1], "6", "First part should be '6' for SHA-512")
        self.assertTrue(
            parts[2].startswith("rounds="), "Second part should specify rounds"
        )

        # Verify hash can be written to and read from a file
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(password_hash)
            f.flush()

            # Read back and verify
            with open(f.name, "r") as f2:
                stored_hash = f2.read().strip()

            self.assertEqual(stored_hash, password_hash)
            self.assertTrue(
                self.password_gen.verify_password_hash(password, stored_hash)
            )

        os.unlink(f.name)


def test_user_passphrase_file_honors_explicit_word_count(tmp_path, monkeypatch):
    """Keep the historic word-count argument functional and validated."""
    monkeypatch.chdir(tmp_path)
    generator = PasswordGenerator(
        mode="passphrase",
        num_words=3,
        require_digits=False,
        require_special=False,
    )

    generator.create_user_passphrase_file("admin", "example", n_words=6)

    raw_secret = tmp_path / "secrets/user-passwords/admin@example_raw"
    hashed_secret = tmp_path / "secrets/user-passwords/admin@example_hashed"
    assert len(raw_secret.read_text(encoding="utf-8").split("-")) == 6
    assert stat.S_IMODE(raw_secret.stat().st_mode) == 0o600
    assert stat.S_IMODE(hashed_secret.stat().st_mode) == 0o600


if __name__ == "__main__":
    unittest.main()
