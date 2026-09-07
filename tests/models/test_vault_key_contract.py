"""Real Ansible crypto with only synthetic keys and isolated CLI configuration."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
from ansible.parsing.vault import VaultLib, VaultSecret

from lx_administration.models.vault import PreSharedKey, Secret, Vault
from lx_administration.models.vault.secret import decrypt_secret


def key(tmp_path, name):
    path = tmp_path / name
    path.write_text(f"synthetic-{name}-only-for-tests")
    path.chmod(0o600)
    return path


def secret(path):
    return Secret(
        name="sample",
        file=str(path),
        owner_type="local",
        template_name="sample",
        target_name="SCRT_sample",
    )


def migration():
    path = Path(__file__).resolve().parents[2] / "scripts/vault/migrate_local_key.py"
    spec = importlib.util.spec_from_file_location("migrate_local_key", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate_file


def test_real_cli_roundtrip_separates_master_and_host_keys(tmp_path, monkeypatch):
    master, host, wrong = [key(tmp_path, n) for n in ("master", "host", "wrong")]
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nvault_identity_list = ambient@" + str(wrong) + "\n")
    monkeypatch.setenv("ANSIBLE_CONFIG", str(config))
    monkeypatch.setenv("ANSIBLE_VAULT_PASSWORD_FILE", str(wrong))
    vault = Vault(key=str(master), local_hostname_override="unrelated-host")
    vault.pre_shared_keys = [PreSharedKey(name="client", file=str(host))]
    source, export = tmp_path / "source", tmp_path / "export"
    Secret.create_secret("roundtrip-value", source, vault)
    secret(source).create_re_encrypted_file(export, host, vault)
    empty_config = tmp_path / "isolated.cfg"
    empty_config.write_text("[defaults]\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANSIBLE_")}
    env["ANSIBLE_CONFIG"] = str(empty_config)
    env["ANSIBLE_VAULT_ID_MATCH"] = "True"
    for path, valid_key, invalid_key, label in (
        (source, master, host, "luxnix-master"),
        (export, host, master, "client"),
    ):
        for candidate, expected in ((valid_key, 0), (invalid_key, 1)):
            result = subprocess.run(
                [
                    "ansible-vault",
                    "view",
                    "--vault-id",
                    f"{label}@{candidate}",
                    str(path),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            assert (result.returncode == 0) == (expected == 0)
            if expected == 0:
                assert result.stdout.strip() == "roundtrip-value"
            else:
                assert "roundtrip-value" not in result.stdout + result.stderr


@pytest.mark.parametrize("operation", ["update", "export", "validate"])
def test_wrong_master_fails_closed_preserving_files(tmp_path, operation):
    master, wrong, host = [key(tmp_path, n) for n in ("master", "wrong", "host")]
    source, export = tmp_path / "source", tmp_path / "export"
    vault = Vault(key=str(master))
    Secret.create_secret("original", source, vault)
    entry = secret(source)
    vault.secrets = [entry]
    before = source.read_bytes()
    export.write_text("last-good-export")
    vault.key = str(wrong)
    with pytest.raises(ValueError, match="decryption failed"):
        if operation == "update":
            entry.value = "replacement"
            entry.update_file_encryption(vault)
        elif operation == "export":
            entry.create_re_encrypted_file(export, host, vault)
        else:
            vault.validate_local_key()
    assert source.read_bytes() == before
    assert export.read_text() == "last-good-export"


@pytest.mark.parametrize("invalid", ["missing", "empty", "public", "symlink"])
def test_invalid_master_key_never_creates_ciphertext(tmp_path, invalid):
    master = tmp_path / "master"
    if invalid != "missing":
        master.write_text("" if invalid == "empty" else "synthetic-key")
        master.chmod(0o644 if invalid == "public" else 0o600)
    if invalid == "symlink":
        link = tmp_path / "link"
        link.symlink_to(master)
        master = link
    with pytest.raises(ValueError, match="Vault key"):
        Secret.create_secret("secret", tmp_path / "output", Vault(key=str(master)))
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("label", ["legacy-host", "default"])
def test_legacy_migration_is_explicit_and_preserves_original(tmp_path, label):
    legacy, master = key(tmp_path, "legacy"), key(tmp_path, "master")
    old_key = VaultSecret(legacy.read_bytes())
    source, output = tmp_path / "source", tmp_path / "output"
    ciphertext = VaultLib([(label, old_key)]).encrypt(
        b"legacy-value", secret=old_key, vault_id=label
    )
    source.write_bytes(ciphertext)
    with pytest.raises(ValueError, match="migration required"):
        secret(source).create_re_encrypted_file(output, legacy, Vault(key=str(master)))
    migration()(source, output, legacy, label, master)
    assert decrypt_secret(output, master) == b"legacy-value"
    assert source.read_bytes() == ciphertext
    assert legacy.exists()
    with pytest.raises(FileExistsError):
        migration()(source, output, legacy, label, master)
    with pytest.raises(ValueError, match="decryption failed"):
        decrypt_secret(output, legacy)


def test_migration_wrong_legacy_key_leaves_no_output(tmp_path):
    legacy, wrong, master = [key(tmp_path, n) for n in ("legacy", "wrong", "master")]
    old = VaultSecret(legacy.read_bytes())
    source, output = tmp_path / "source", tmp_path / "output"
    source.write_bytes(VaultLib([("old", old)]).encrypt(b"secret", old, "old"))
    before = source.read_bytes()
    with pytest.raises(ValueError, match="decryption failed"):
        migration()(source, output, wrong, "old", master)
    assert source.read_bytes() == before
    assert not output.exists()


def test_plaintext_and_mislabeled_ciphertext_rejected_before_update(tmp_path):
    master = key(tmp_path, "master")
    source = tmp_path / "source"
    source.write_text("plaintext")
    with pytest.raises(ValueError, match="migration required"):
        Secret.create_secret("new", source, Vault(key=str(master)))
    assert source.read_text() == "plaintext"


def test_load_dir_honors_explicit_key_over_saved_metadata(tmp_path):
    import yaml

    root = tmp_path / "vault"
    root.mkdir()
    (root / "vault.yml").write_text(yaml.safe_dump({"dir": "/old", "key": "/old-key"}))
    explicit = key(tmp_path, "explicit")
    vault = Vault.load_dir(str(root), str(explicit))
    assert vault.key == str(explicit)
    assert vault.dir == str(root)


@pytest.mark.parametrize("registration", ["missing", "duplicate", "master-label"])
def test_export_requires_unique_separate_registered_identity(tmp_path, registration):
    master, host = key(tmp_path, "master"), key(tmp_path, "host")
    vault = Vault(key=str(master))
    source, output = tmp_path / "source", tmp_path / "output"
    Secret.create_secret("secret", source, vault)
    if registration == "duplicate":
        vault.pre_shared_keys = [
            PreSharedKey(name=name, file=str(host)) for name in ("one", "two")
        ]
    elif registration == "master-label":
        vault.pre_shared_keys = [PreSharedKey(name="luxnix-master", file=str(host))]
    with pytest.raises(ValueError, match="identity"):
        secret(source).create_re_encrypted_file(output, host, vault)
    assert not output.exists()


@pytest.mark.parametrize("sync", [False, True])
def test_real_bootstrap_import_export_and_wrong_key_preflight(tmp_path, sync):
    import sys
    import yaml

    from lx_administration.models.ansible import (
        AnsibleInventory,
        AnsibleInventoryHost,
    )

    repo = Path(__file__).resolve().parents[2]
    root = tmp_path
    vault_dir = root / "vault"
    vault_dir.mkdir(mode=0o700)
    master = root / "master.key"
    master.write_text("synthetic-integration-master")
    master.chmod(0o600)
    mapping = root / "passwords.yml"
    mapping.write_text("admin_passwords:\n  client: synthetic-integration-password\n")
    mapping.chmod(0o600)
    cfg = root / "ansible.cfg"
    cfg.write_text("[defaults]\n")
    vault = Vault(
        dir=str(vault_dir),
        key=str(master),
        inventory=AnsibleInventory(all=[AnsibleInventoryHost(hostname="client")]),
    )
    if not sync:
        (vault_dir / "vault.yml").write_text(
            yaml.safe_dump(vault.model_dump(mode="json"))
        )
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANSIBLE_")}
    env["PYTHONPATH"] = str(repo)
    env["ANSIBLE_CONFIG"] = str(cfg)
    command = [
        sys.executable,
        str(repo / "scripts/bootstrap-lx-vault.py"),
        "--vault-dir",
        str(vault_dir),
        "--vault-key",
        str(master),
        "--ansible-cfg",
        str(cfg),
        "--inventory",
        str(root / "unused-inventory.yml"),
        "--local-hostname",
        "client",
        "--admin-passwords",
        str(mapping),
        "--skip-sync",
        "--export",
    ]
    if sync:
        command.remove("--skip-sync")
        (root / "unused-inventory.yml").write_text(
            yaml.safe_dump(vault.inventory.model_dump(mode="json"))
        )
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError("bootstrap failed")
    loaded = Vault.load_dir(str(vault_dir), str(master))
    loaded.validate_local_key()
    assert len(loaded.secrets) >= 2
    exported = sorted((vault_dir / "deploy/client").iterdir())
    assert len(exported) == len(loaded.secrets)
    for entry in loaded.secrets:
        assert Path(entry.file).is_relative_to(vault_dir)
        assert decrypt_secret(
            vault_dir / "deploy/client" / entry.target_name,
            vault_dir / "psk/client.psk",
            "client",
        ) == decrypt_secret(entry.file, master)
    validate = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/validate-admin-passwords.py"),
            "--vault-dir",
            str(vault_dir),
            "--vault-key",
            str(master),
            "--admin-passwords",
            str(mapping),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stderr
    snapshot = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    wrong = root / "wrong.key"
    wrong.write_text("synthetic-wrong-master")
    wrong.chmod(0o600)
    invalid = command.copy()
    invalid[invalid.index("--vault-key") + 1] = str(wrong)
    result = subprocess.run(invalid, cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    for path, previous in snapshot.items():
        assert (root / path).read_bytes() == previous, path
    assert "synthetic-integration-password" not in result.stdout + result.stderr


def test_load_dir_retains_key_symlink_for_fail_closed_validation(tmp_path):
    import yaml

    root = tmp_path / "vault"
    root.mkdir()
    (root / "vault.yml").write_text(yaml.safe_dump({"secrets": []}))
    master = key(tmp_path, "master")
    link = tmp_path / "linked-key"
    link.symlink_to(master)
    vault = Vault.load_dir(str(root), str(link))
    assert vault.key == str(link)
    with pytest.raises(ValueError, match="non-symlink"):
        vault.validate_local_key()
