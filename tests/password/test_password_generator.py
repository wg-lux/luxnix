import unittest
from lx_administration.password.generator import (
    PasswordGenerator,
)
import string


class TestPasswordGenerator(unittest.TestCase):
    """
    Unit tests for the PasswordGenerator class.
    """

    def setUp(self):
        """
        Set up the test case with instances of PasswordGenerator.
        """
        self.generator = PasswordGenerator(length=12)

    def test_generate_random_password(self):
        """
        Test the generate_random_password method to ensure it generates
        a password of the correct length and containing at least
        one lowercase letter, one uppercase letter, one digit,
        and one punctuation character.
        """
        password = self.generator.generate_random_password()
        self.assertEqual(len(password), 12)
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c in string.punctuation for c in password))

    def test_generate_random_passphrase(self):
        """
        Test the generate_random_passphrase method to ensure it generates a passphrase
        with the correct number of words.
        """
        passphrase = self.generator.generate_random_passphrase(num_words=4)
        self.assertEqual(len(passphrase.split("-")), 4)

    def test_create_password_hash(self):
        """
        Test the create_password_hash method to ensure it generates a valid hash for
        a given password.
        """
        password = "testpassword"
        password_hash = self.generator.create_password_hash(password)
        self.assertIsInstance(password_hash, str)
        self.assertGreater(len(password_hash), 0)

    def test_verify_password_hash(self):
        """
        Test the verify_password_hash method to ensure it correctly verifies a password
        against a hash.
        """
        password = "testpassword"
        password_hash = self.generator.create_password_hash(password)
        self.assertTrue(self.generator.verify_password_hash(password, password_hash))
        self.assertFalse(
            self.generator.verify_password_hash("wrongpassword", password_hash)
        )


if __name__ == "__main__":
    unittest.main()
