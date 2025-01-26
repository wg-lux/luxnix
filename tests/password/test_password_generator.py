import unittest
from lx_administration.password.generator import PasswordGenerator
import string


class TestPasswordGenerator(unittest.TestCase):
    def setUp(self):
        """
        Set up the test case with instances of PasswordGenerator.
        """
        self.generator = PasswordGenerator(mode="password", length=12)
        self.passphrase_generator = PasswordGenerator(mode="passphrase", num_words=4)

    def test_generate_random_password(self):
        """
        Test the generate_random_password method to ensure it generates
        a password of the correct length with required characters.
        """
        password = self.generator.generate_random_password()
        self.assertEqual(len(password), 12)
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c in string.punctuation for c in password))

    def test_generate_random_passphrase(self):
        """
        Test the generate_random_passphrase method.
        """
        passphrase = self.passphrase_generator.generate_random_passphrase()
        self.assertEqual(len(passphrase.split("-")), 4)

    def test_pipe_password_mode(self):
        """
        Test the pipe method in password mode.
        """
        result = self.generator.pipe()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "password")
        self.assertEqual(result[1][0], "password_hash")
        self.assertEqual(len(result[0][1]), 12)

    def test_pipe_passphrase_mode(self):
        """
        Test the pipe method in passphrase mode.
        """
        result = self.passphrase_generator.pipe()
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
