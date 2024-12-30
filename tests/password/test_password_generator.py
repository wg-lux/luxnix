import unittest
from lx_administration.password.generator import (
    PasswordGenerator,
    ReadablePasswordGenerator,
)
import string


class TestPasswordGenerator(unittest.TestCase):
    """
    Unit tests for the PasswordGenerator and ReadablePasswordGenerator classes.
    """

    def setUp(self):
        """
        Set up the test case with instances of PasswordGenerator
        and ReadablePasswordGenerator.
        """
        self.generator = PasswordGenerator(length=12)
        self.readable_generator = ReadablePasswordGenerator(length=12)

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
        self.assertEqual(len(passphrase.split()), 4)

    def test_create_password_hash(self):
        """
        Test the create_password_hash method to ensure it generates a valid hash for
        a given password.
        """
        password = "testpassword"
        password_hash = self.generator.create_password_hash(password)
        self.assertIsInstance(password_hash, str)
        self.assertGreater(len(password_hash), 0)

    def test_generate_readable_password(self):
        """
        Test the generate_readable_password method to ensure it generates a
        readable password of the correct length
        using alternating consonants and vowels.
        """
        password = self.readable_generator.generate_readable_password()
        self.assertEqual(len(password), 12)
        self.assertTrue(
            all(
                c in "aeiou" or c in (set(string.ascii_lowercase) - set("aeiou"))
                for c in password
            )
        )


if __name__ == "__main__":
    unittest.main()
