from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import SecretTemplate, Vault
from lx_administration.password import PasswordGenerator


def _vault(tmp_path, *hostnames):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.all = [SimpleNamespace(hostname=name) for name in hostnames]
    return Vault(dir=str(tmp_path), inventory=inventory)


def test_secret_generator_selection_is_explicit():
    passphrase = SecretTemplate(
        name="user", owner_type="local", secret_type="password"
    ).get_secret_generator()
    system_password = SecretTemplate(
        name="service", owner_type="services", secret_type="system_password"
    ).get_secret_generator()

    assert passphrase.mode == "passphrase"
    assert system_password.mode == "password"


def test_create_secret_template_initializes_directory_and_generator(tmp_path):
    template = SecretTemplate.create_secret_template(
        name="admin",
        owner_type="local",
        vault_dir=tmp_path,
    )

    assert template.directory == str(tmp_path / "secrets/password/local/admin")
    assert template.generator is not None
    assert template.generator.mode == "passphrase"


def test_secret_generator_rejects_unknown_type():
    template = SecretTemplate(name="invalid", owner_type="local", secret_type="unknown")

    with pytest.raises(ValueError, match="Invalid secret_type: unknown"):
        template.get_secret_generator()


def test_template_validation_requires_a_real_directory(tmp_path):
    template = SecretTemplate(
        name="user",
        owner_type="local",
        directory=str(tmp_path / "missing"),
    )

    with pytest.raises(ValueError, match="does not exist"):
        template.assert_valid()


def test_secret_creation_requires_inventory(tmp_path):
    template = SecretTemplate(
        name="admin",
        owner_type="local",
        directory=str(tmp_path),
        generator=PasswordGenerator(mode="password"),
    )

    with pytest.raises(ValueError, match="Inventory must be loaded"):
        template.create_or_update_secrets(Vault(dir=str(tmp_path)))


@pytest.fixture
def materialized(tmp_path):
    vault = _vault(tmp_path, "gc-02")
    key = tmp_path / "master.key"
    key.write_text("synthetic-test-master-key")
    key.chmod(0o600)
    vault.key = str(key)
    template = SecretTemplate(
        name="admin@gc-02",
        owner_type="local",
        directory=str(tmp_path / "pair"),
        generator=PasswordGenerator(mode="password"),
    )
    logger = MagicMock()
    assert template.create_or_update_secrets(vault, logger=logger)
    from lx_administration.models.vault.secret import decrypt_secret

    assert decrypt_secret(vault.secrets[0].file, vault.key).decode() not in str(
        logger.mock_calls
    )
    return vault, template


def _state(vault, template):
    from pathlib import Path

    return (
        [item.model_dump() for item in vault.secrets],
        template.secret_names.copy(),
        {
            str(path): path.read_bytes()
            for path in Path(template.directory).iterdir()
            if path.is_file()
        },
    )


def test_fresh_pair_is_encrypted_matching_private_and_host_scoped(materialized):
    from pathlib import Path
    from passlib.hash import sha512_crypt
    from lx_administration.models.vault.secret import decrypt_secret

    vault, template = materialized
    password, password_hash = [
        decrypt_secret(item.file, vault.key) for item in vault.secrets
    ]
    assert sha512_crypt.verify(password, password_hash.decode())
    assert template.secret_names == [
        "admin@gc-02_password",
        "admin@gc-02_password_hash",
    ]
    for item in vault.secrets:
        path = Path(item.file)
        assert path.read_bytes().startswith(b"$ANSIBLE_VAULT;")
        assert password not in path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        assert "@gc-02" not in item.target_name


def test_complete_pair_is_unchanged_without_generation(materialized):
    vault, template = materialized
    before = _state(vault, template)
    with patch.object(PasswordGenerator, "pipe") as generate:
        assert template.create_or_update_secrets(vault) is False
    generate.assert_not_called()
    assert _state(vault, template) == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing_hash",
        "missing_password",
        "orphan_hash",
        "orphan_password",
        "duplicate",
        "metadata_path",
        "path_alias",
        "metadata_owner",
        "metadata_template",
        "metadata_type",
        "metadata_target",
        "secret_names",
        "missing_both",
        "symlink",
    ],
)
def test_partial_or_conflicting_pair_never_regenerates(materialized, damage):
    from pathlib import Path

    vault, template = materialized
    if damage.startswith("missing_"):
        indices = {"missing_hash": [1], "missing_password": [0], "missing_both": [0, 1]}
        for index in indices[damage]:
            Path(vault.secrets[index].file).unlink()
    elif damage.startswith("orphan_"):
        vault.secrets.pop(1 if damage == "orphan_hash" else 0)
    elif damage == "duplicate":
        vault.secrets.append(vault.secrets[1].model_copy())
    elif damage == "path_alias":
        vault.secrets.append(
            vault.secrets[1].model_copy(
                update={"name": "other", "template_name": "other"}
            )
        )
    elif damage == "metadata_path":
        vault.secrets[1].file += ".wrong"
    elif damage == "metadata_owner":
        vault.secrets[1].owner_type = "roles"
    elif damage == "metadata_template":
        vault.secrets[1].template_name = "other"
    elif damage == "metadata_target":
        vault.secrets[1].target_name = "unrelated"
    elif damage == "metadata_type":
        vault.secrets[1].secret_type = "system_password"
    elif damage == "secret_names":
        template.secret_names.pop()
    elif damage == "symlink":
        path = Path(vault.secrets[1].file)
        other = path.with_suffix(".saved")
        path.rename(other)
        path.symlink_to(other)
    before = _state(vault, template)
    with patch.object(PasswordGenerator, "pipe") as generate:
        with pytest.raises(ValueError):
            template.create_or_update_secrets(vault)
    generate.assert_not_called()
    assert _state(vault, template) == before


def test_preexisting_orphan_ciphertext_is_not_overwritten(materialized):
    vault, template = materialized
    vault.secrets.clear()
    template.secret_names.clear()
    before = _state(vault, template)
    with patch.object(PasswordGenerator, "pipe") as generate:
        with pytest.raises(ValueError, match="file/metadata mismatch"):
            template.create_or_update_secrets(vault)
    generate.assert_not_called()
    assert _state(vault, template) == before


def test_mismatching_encrypted_pair_is_not_accepted(materialized):
    from lx_administration.models.vault import Secret

    vault, template = materialized
    Secret.create_secret("unrelated-password", vault.secrets[0].file, vault)
    before = _state(vault, template)
    with patch.object(PasswordGenerator, "pipe") as generate:
        with pytest.raises(ValueError, match="does not match"):
            template.create_or_update_secrets(vault)
    generate.assert_not_called()
    assert _state(vault, template) == before


@pytest.mark.parametrize("race", [False, True])
def test_second_publication_failure_preserves_metadata_and_competing_file(
    materialized,
    race,
):
    from pathlib import Path
    from lx_administration.models.vault import secret as secret_module

    vault, template = materialized
    for item in vault.secrets:
        Path(item.file).unlink()
    vault.secrets.clear()
    template.secret_names.clear()
    publish = secret_module._publish_ciphertext
    calls = 0
    competing = b"competing-writer-material"

    def fail_second(data, path, *, replace=True):
        nonlocal calls
        calls += 1
        if calls == 2:
            if race:
                path.write_bytes(competing)
            else:
                raise OSError("injected second publication failure")
        return publish(data, path, replace=replace)

    with patch.object(secret_module, "_publish_ciphertext", side_effect=fail_second):
        with pytest.raises(OSError):
            template.create_or_update_secrets(vault)
    assert vault.secrets == []
    assert template.secret_names == []
    paths = template._secret_paths(vault)
    assert not paths[0].exists()
    if race:
        assert paths[1].read_bytes() == competing
    else:
        assert not paths[1].exists()
        assert template.create_or_update_secrets(vault)
    assert not list(paths[0].parent.glob(".*"))


def test_sync_preflights_all_pairs_before_any_generation(materialized):
    from pathlib import Path

    vault, broken = materialized
    fresh = broken.model_copy(update={"name": "new", "secret_names": []})
    vault.secret_templates = [fresh, broken]
    Path(vault.secrets[1].file).unlink()
    before = _state(vault, broken)
    with (
        patch.object(Vault, "_sync_role_secret_templates"),
        patch.object(Vault, "_sync_group_secret_templates"),
        patch.object(Vault, "_build_local_user_secret_templates"),
        patch.object(PasswordGenerator, "pipe") as generate,
    ):
        with pytest.raises(ValueError, match="file/metadata mismatch"):
            vault.sync_secret_templates()
    generate.assert_not_called()
    assert _state(vault, broken) == before
    assert fresh.secret_names == []


@pytest.mark.parametrize(
    "secret_type", ["id_ed25519", "id_rsa", "ssh_cert", "openvpn_cert"]
)
def test_unsupported_generators_fail_before_creating_directories(tmp_path, secret_type):
    with pytest.raises(ValueError, match="Unsupported generated"):
        SecretTemplate.create_secret_template("key", "local", secret_type, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "owner,kind", [("groups", "password"), ("roles", "system_password")]
)
def test_name_collision_never_returns_a_different_template(tmp_path, owner, kind):
    vault = _vault(tmp_path)
    original, _ = vault.get_or_create_secret_template("same", "roles", "password")
    with pytest.raises(ValueError, match="Conflicting template identity"):
        vault.get_or_create_secret_template("same", owner, kind)
    assert vault.secret_templates == [original]


@pytest.mark.parametrize("operation", ["validate", "key", "export", "direct-export"])
def test_mixed_pair_is_rejected_by_every_distribution_boundary(
    materialized, tmp_path, operation
):
    from lx_administration.models.vault import Secret

    vault, template = materialized
    vault.secret_templates = [template]
    Secret.create_secret("a-different-password", vault.secrets[0].file, vault)
    before = _state(vault, template)
    with pytest.raises(ValueError, match="pair does not match"):
        if operation == "validate":
            vault.validate_vault()
        elif operation == "key":
            vault.validate_local_key()
        elif operation == "export":
            vault.export_secrets_by_client()
        else:
            vault.secrets[0].create_re_encrypted_file(
                tmp_path / "export", tmp_path / "psk", vault
            )
    assert _state(vault, template) == before
    assert not (tmp_path / "deploy").exists()
