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


if __name__ == "__main__":
    unittest.main()
