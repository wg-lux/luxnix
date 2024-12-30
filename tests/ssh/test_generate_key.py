import os
import unittest
from unittest.mock import patch
from lx_administration.ssh.generate_key import create_openssh_keys

class TestCreateOpenSSHKeys(unittest.TestCase):

    @patch("lx_administration.ssh.generate_key.os.makedirs")
    @patch("lx_administration.ssh.generate_key.subprocess.run")
    def test_create_openssh_keys_rsa(self, mock_subprocess_run, mock_makedirs):
        output_dir = "/tmp/test_keys"
        key_name = "test_rsa"
        passphrase = "test_passphrase"
        key_type = "rsa"

        result = create_openssh_keys(output_dir, key_name, passphrase, key_type)

        expected_private_key_path = os.path.join(output_dir, key_name)
        expected_public_key_path = f"{expected_private_key_path}.pub"

        self.assertEqual(result["private_key"], expected_private_key_path)
        self.assertEqual(result["public_key"], expected_public_key_path)

        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_subprocess_run.assert_called_once_with(
            [
                "ssh-keygen",
                "-t", key_type,
                "-f", expected_private_key_path,
                "-N", passphrase,
                "-q",
                "-b", "4096"
            ],
            check=True
        )

    @patch("lx_administration.ssh.generate_key.os.makedirs")
    @patch("lx_administration.ssh.generate_key.subprocess.run")
    def test_create_openssh_keys_ed25519(self, mock_subprocess_run, mock_makedirs):
        output_dir = "/tmp/test_keys"
        key_name = "test_ed25519"
        passphrase = "test_passphrase"
        key_type = "ed25519"

        result = create_openssh_keys(output_dir, key_name, passphrase, key_type)

        expected_private_key_path = os.path.join(output_dir, key_name)
        expected_public_key_path = f"{expected_private_key_path}.pub"

        self.assertEqual(result["private_key"], expected_private_key_path)
        self.assertEqual(result["public_key"], expected_public_key_path)

        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_subprocess_run.assert_called_once_with(
            [
                "ssh-keygen",
                "-t", key_type,
                "-f", expected_private_key_path,
                "-N", passphrase,
                "-q"
            ],
            check=True
        )

    def test_create_openssh_keys_invalid_key_type(self):
        with self.assertRaises(ValueError) as context:
            create_openssh_keys("/tmp/test_keys", key_type="invalid_type")
        self.assertEqual(str(context.exception), "Key type must be 'rsa' or 'ed25519'.")

    def test_create_openssh_keys_empty_key_name(self):
        with self.assertRaises(ValueError) as context:
            create_openssh_keys("/tmp/test_keys", key_name=" ")
        self.assertEqual(str(context.exception),\
                         "Key name must not be empty or whitespace.")

if __name__ == "__main__":
    unittest.main()
