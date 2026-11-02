"""Restricted early SSH and restored login checks before installation."""

import json
import subprocess
from pathlib import Path

import pytest

from lx_administration.storage import boot_migration as migration

ROOT = Path(__file__).resolve().parents[1]


def test_remote_unlock_evaluates_restricted_and_retryable():
    expression = r"""
      let f = builtins.getFlake ("git+file://" + toString ./.);
          lib = f.inputs.nixpkgs.lib;
          h = f.nixosConfigurations.gc-09.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = lib.mkForce "boot-luks";
            luxnix.storage.operatorUnlocked.remoteUnlock = {
              enable = true; interface = "enp1s0"; address = "192.0.2.10/24";
              kernelModules = [ "e1000e" ];
              allowedSources = [ "192.0.2.1/32" ];
              authorizedKeys = [ (lib.fileContents (f.inputs.nixpkgs.outPath
                + "/nixos/tests/initrd-network-ssh/id_ed25519.pub")) ];
            };
          }]; }; c = h.config;
          bad = h.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.remoteUnlock.allowedSources =
              lib.mkForce [];
          }]; };
      in { failures = map (a: a.message)
             (builtins.filter (a: !a.assertion) c.assertions);
           ssh = { inherit (c.boot.initrd.network.ssh)
             hostKeys authorizedKeyFiles authorizedKeys extraConfig; };
           crypttab = c.boot.initrd.luks.devices.cryptroot.crypttabExtraOpts;
           network = { inherit
             (c.boot.initrd.systemd.network.networks."10-luxnix-unlock")
             matchConfig address; };
           rejected = map (a: a.message)
             (builtins.filter (a: !a.assertion) bad.config.assertions); }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["failures"] == []
    assert value["ssh"]["hostKeys"] == ["/etc/luxnix/initrd-ssh/ssh_host_ed25519_key"]
    assert value["ssh"]["authorizedKeyFiles"] == []
    assert all(
        'restrict,pty,from="192.0.2.1/32",command=' in k
        for k in value["ssh"]["authorizedKeys"]
    )
    assert "DisableForwarding yes" in value["ssh"]["extraConfig"]
    assert "ForceCommand " in value["ssh"]["extraConfig"]
    assert "tries=0" in value["crypttab"] and "timeout=0" in value["crypttab"]
    assert value["network"]["matchConfig"]["Name"] == "enp1s0"
    assert any("management client" in message for message in value["rejected"])


@pytest.mark.parametrize(
    "content", [b"", b"!", b"*", b"$6$short$bad", b"plaintext", b"\n\n"]
)
def test_bad_or_locked_account_hash_is_not_installed(tmp_path, content):
    path = tmp_path / "hash"
    path.write_bytes(content)
    with pytest.raises(migration.MigrationError, match="malformed"):
        migration.account_hash(path)


def test_restored_admin_hash_and_independent_login_keys_are_required(
    tmp_path, monkeypatch
):
    path = tmp_path / "hash"
    path.write_bytes(b"$6$test$" + b"A" * 86 + b"\n")
    monkeypatch.setattr(migration, "target_private", lambda *args: path)
    config = {
        "admin": {
            "normal": True,
            "wheel": True,
            "hash_file": "/var/lib/luxnix-account/admin-password.hash",
            "keys": ["ssh-ed25519 test-public"],
        }
    }
    migration.verify_accounts({"config": config})
    config["admin"]["keys"] = []
    with pytest.raises(migration.MigrationError, match="SSH public"):
        migration.verify_accounts({"config": config})
    config["admin"]["wheel"] = False
    with pytest.raises(migration.MigrationError, match="sudo access"):
        migration.verify_accounts({"config": config})


def test_unsafe_account_symlink_fails_without_reading_it(tmp_path, monkeypatch):
    (tmp_path / "hash").symlink_to("/etc/shadow")
    with pytest.raises(migration.MigrationError, match="symbolic"):
        migration.target_private("/hash", tmp_path)


def test_prepare_access_restores_only_missing_hash_and_preserves_ssh_identity(
    tmp_path, monkeypatch
):
    from contextlib import nullcontext
    from lx_administration.storage import boot

    root = tmp_path / "root"
    source = root / "etc/secrets/admin.hash"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"$6$test$" + b"A" * 86 + b"\n")
    plan = {
        "spec": {"host": "test-host"},
        "config": {
            "mounts": {"/": {"fsType": "ext4"}},
            "admin": {
                "normal": True,
                "wheel": True,
                "hash_file": "/var/lib/luxnix-account/admin.hash",
                "source": "/etc/secrets/admin.hash",
                "keys": ["ssh-ed25519 test-public"],
            },
            "remote_unlock": {
                "enable": True,
                "hostKey": "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key",
            },
        },
    }
    monkeypatch.setattr(migration, "installer_lock", nullcontext)
    monkeypatch.setattr(migration, "locked_state", lambda *a: nullcontext())
    monkeypatch.setattr(migration, "load_plan", lambda *a: plan)
    monkeypatch.setattr(migration, "load_progress", lambda *a: {})
    monkeypatch.setattr(migration, "check_gates", lambda *a: {1})
    monkeypatch.setattr(migration, "verify_independent_state", lambda *a: None)
    monkeypatch.setattr(migration, "device_disks", lambda *a: {1})
    monkeypatch.setattr(migration, "encrypted_storage", lambda *a: None)
    monkeypatch.setattr(
        migration, "target_private", lambda path, base=root: base / path.lstrip("/")
    )
    monkeypatch.setattr(boot, "verify_mount", lambda *a: None)
    first = migration.prepare_access(tmp_path, root)
    assert first["changed"] and first["unlock_host_public_key"].startswith(
        "ssh-ed25519 "
    )
    target = root / plan["config"]["admin"]["hash_file"].lstrip("/")
    assert target.read_bytes() == source.read_bytes()
    private_key = root / plan["config"]["remote_unlock"]["hostKey"].lstrip("/")
    before = private_key.read_bytes()
    source.write_bytes(b"new invalid source must not replace the restored credential")
    second = migration.prepare_access(tmp_path, root)
    assert (
        not second["changed"]
        and first["unlock_host_public_key"] == second["unlock_host_public_key"]
    )
    assert private_key.read_bytes() == before
