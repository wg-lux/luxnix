import unittest
from lx_administration.password.generator import PasswordGenerator
import string


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
        self.assertTrue(any(c in string.punctuation for c in password))

    def test_password_minimum_length(self):
        """Test minimum length validation."""
        with self.assertRaises(ValueError):
            PasswordGenerator(mode="password", key_length=8)

    def test_generate_random_passphrase(self):
        """
        Test the generate_random_passphrase method.
        """
        passphrase = self.passphrase_gen.generate_random_passphrase()
        self.assertEqual(len(passphrase.split("-")), 4)

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
        Test that generated password hashes are compatible with NixOS user password files.
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


if __name__ == "__main__":
    unittest.main()
