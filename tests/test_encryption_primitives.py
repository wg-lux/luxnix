"""Real crypto/component tests, not host boot, custody or ENC-09 acceptance.

Only the encrypted-storage fixture is substituted for synthetic vault material.
dm-verity verifies disposable regular-file images without mounting any device.
"""
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess

import pytest

from lx_administration.models.vault import secret


@pytest.fixture
def verity_image(tmp_path):
    tool = shutil.which("veritysetup")
    assert tool, "veritysetup from cryptsetup is required for this component test"
    data, tree = tmp_path / "root.img", tmp_path / "root.verity"
    data.write_bytes(secrets.token_bytes(4096 * 128))
    result = subprocess.run([tool, "format", str(data), str(tree)],
                            capture_output=True, text=True, check=True)
    match = re.search(r"^Root hash:\s+([0-9a-f]+)$", result.stdout, re.MULTILINE)
    assert match, "veritysetup did not return a root hash"
    return tool, data, tree, match.group(1)


def verify(image, root_hash=None):
    tool, data, tree, trusted = image
    return subprocess.run([tool, "verify", str(data), str(tree), root_hash or trusted],
                          capture_output=True).returncode


@pytest.mark.parametrize("target", ["data", "tree", "trusted_root"])
def test_verity_rejects_tamper_and_substituted_trust_root(verity_image, target):
    assert verify(verity_image) == 0
    if target == "trusted_root":
        assert verify(verity_image, "0" * len(verity_image[3])) != 0
        return
    path = verity_image[1 if target == "data" else 2]
    original = path.read_bytes()
    damaged = bytearray(original)
    # Skip the verity superblock: corrupt authenticated hash data instead.
    offset = 4096 if target == "tree" else 8192
    damaged[offset] ^= 1
    path.write_bytes(damaged)
    assert verify(verity_image) != 0
    path.write_bytes(original)
    assert verify(verity_image) == 0


def test_recomputed_tree_does_not_override_pinned_root(verity_image):
    tool, data, tree, trusted = verity_image
    data.write_bytes(secrets.token_bytes(data.stat().st_size))
    tree.unlink()
    forged = subprocess.run([tool, "format", str(data), str(tree)],
                            capture_output=True, text=True, check=True)
    replacement = re.search(r"^Root hash:\s+([0-9a-f]+)$", forged.stdout, re.MULTILINE).group(1)
    assert replacement != trusted
    assert verify(verity_image) != 0
    # Mutation witness: trusting the attacker's new root makes the bad image pass.
    assert verify(verity_image, replacement) == 0


def test_encrypted_generation_bundle_survives_loss_and_rejects_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setattr(secret, "encrypted_storage", lambda *args, **kwargs: None)
    key = tmp_path / "custodian.key"
    key.write_text(secrets.token_hex(32))
    key.chmod(0o600)
    # Synthetic generations only; this does not authorize exporting machine salts.
    bundle = {"host": "test-node", "active_generation": 2,
              "generations": {"1": secrets.token_hex(32), "2": secrets.token_hex(32)}}
    live = tmp_path / "live.json"
    live.write_text(json.dumps(bundle))
    ciphertext = secret._encrypt_bytes(live.read_bytes(), key, secret.MASTER_VAULT_ID)
    archive = tmp_path / "emergency.vault"
    archive.write_bytes(ciphertext)
    live.unlink()
    assert all(value.encode() not in ciphertext for value in bundle["generations"].values())
    assert json.loads(secret.decrypt_secret(archive, key)) == bundle
    wrong = tmp_path / "wrong.key"
    wrong.write_text(secrets.token_hex(32))
    wrong.chmod(0o600)
    with pytest.raises(ValueError, match="decryption failed"):
        secret.decrypt_secret(archive, wrong)
    damaged = bytearray(ciphertext)
    # Keep the envelope valid while invalidating its authenticated payload.
    offset = ciphertext.index(b"\n") + 10
    damaged[offset] = ord('0') if damaged[offset] != ord('0') else ord('1')
    archive.write_bytes(damaged)
    with pytest.raises(ValueError):
        secret.decrypt_secret(archive, key)
