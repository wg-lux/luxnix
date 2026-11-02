"""Boot layout evaluation and fail-closed probes; physical boot is a separate lane."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
from lx_administration import secret_storage

previous_verifier = sys.modules.get("secret_storage")
sys.modules["secret_storage"] = secret_storage
spec = importlib.util.spec_from_file_location("boot_storage", ROOT / "lx_administration/storage/boot.py")
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
if previous_verifier is None:
    del sys.modules["secret_storage"]
else:
    sys.modules["secret_storage"] = previous_verifier


def test_missing_mount_fails_before_device_access(monkeypatch):
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": []})
    with pytest.raises(ValueError, match="Missing"):
        boot.verify_mount("/srv/data", "/dev/mapper/data")


def test_wrong_device_fails_before_encryption_probe(monkeypatch):
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": [
        {"source": "/dev/plain", "fstype": "ext4"}]})
    monkeypatch.setattr(boot.os, "stat", lambda p: SimpleNamespace(st_rdev=1 if p == "/dev/plain" else 2))
    with pytest.raises(ValueError, match="Unexpected"):
        boot.verify_mount("/srv/data", "/dev/mapper/data")


def test_existing_key_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(boot, "encrypted_storage", lambda p: None)
    key = tmp_path / "key"
    key.write_bytes(b"existing-key-material" * 4)
    key.chmod(0o400)
    actual_lstat = Path.lstat
    def root_stat(path):
        info = actual_lstat(path)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_size=info.st_size)
    monkeypatch.setattr(Path, "lstat", root_stat)
    before = key.read_bytes()
    boot.verify_key(str(key))
    boot.verify_key(str(key))
    assert key.read_bytes() == before
    key.chmod(0o644)
    with pytest.raises(ValueError, match="unsafe"):
        boot.verify_key(str(key))
    assert key.read_bytes() == before
    key.unlink()
    with pytest.raises(FileNotFoundError):
        boot.verify_key(str(key))
    assert not key.exists()


@pytest.fixture
def secondary_key_device(tmp_path, monkeypatch):
    identifier = "0f30e83c-c014-490a-a610-751eb4d301a0"
    dm = tmp_path / "253:2"
    (dm / "dm").mkdir(parents=True)
    (dm / "dm/uuid").write_text(f"CRYPT-LUKS2-{identifier.replace('-', '')}-data")
    (dm / "slaves/sda2").mkdir(parents=True)
    (dm / "slaves/sda2/dev").write_text("8:2")
    monkeypatch.setattr(boot, "BLOCK_SYSFS", tmp_path)
    original_stat = boot.os.stat
    def block_stat(path, **kwargs):
        if str(path) in {"/dev/mapper/data", "/dev/disk/by-partlabel/data"}:
            return SimpleNamespace(st_mode=stat.S_IFBLK,
                                   st_rdev=os.makedev(253, 2) if str(path).startswith("/dev/mapper/") else os.makedev(8, 2))
        return original_stat(path, **kwargs)
    monkeypatch.setattr(boot.os, "stat", block_stat)
    def luks_uuid(args, **kwargs):
        assert args == ["cryptsetup", "luksUUID", "/dev/disk/by-partlabel/data"]
        assert kwargs["timeout"] == 10
        return identifier
    monkeypatch.setattr(boot.subprocess, "check_output", luks_uuid)
    monkeypatch.setattr(boot, "verify_key", lambda path: None)
    return {"path": "/etc/luks-keys/data.key", "device": "/dev/disk/by-partlabel/data", "mapping": "data"}, dm


def test_secondary_unlock_is_read_only_even_when_mapping_is_open(secondary_key_device, monkeypatch):
    key, _ = secondary_key_device
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                          "stderr": subprocess.DEVNULL, "check": True, "timeout": 30}
    monkeypatch.setattr(boot.subprocess, "run", run)
    boot.verify_unlock(key)
    boot.verify_unlock(key)
    assert calls == [["cryptsetup", "open", "--type", "luks2", "--test-passphrase",
                      "--batch-mode", "--key-file", key["path"], key["device"]]] * 2


@pytest.mark.parametrize("failure", [subprocess.CalledProcessError(2, "cryptsetup"),
                                     subprocess.TimeoutExpired("cryptsetup", 30)])
def test_open_mapping_does_not_hide_wrong_key_or_timeout(secondary_key_device, monkeypatch, failure):
    key, _ = secondary_key_device
    def run(*args, **kwargs):
        raise failure
    monkeypatch.setattr(boot.subprocess, "run", run)
    with pytest.raises(ValueError, match="verification failed or timed out"):
        boot.verify_unlock(key)


@pytest.mark.parametrize("relative,content", [("dm/uuid", "CRYPT-LUKS2-wrong-data"),
                                               ("slaves/sda2/dev", "8:3")])
def test_wrong_uuid_or_backing_fails_before_key_test(secondary_key_device, monkeypatch, relative, content):
    key, dm = secondary_key_device
    (dm / relative).write_text(content)
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: pytest.fail("wrong device reached key test"))
    with pytest.raises(ValueError, match="UUID|backing"):
        boot.verify_unlock(key)


def test_device_identity_change_during_key_test_is_rejected(secondary_key_device, monkeypatch):
    key, dm = secondary_key_device
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **k: (dm / "slaves/sda2/dev").write_text("8:3"))
    with pytest.raises(ValueError, match="backing"):
        boot.verify_unlock(key)


@pytest.mark.parametrize("mounted", [False, True])
def test_cli_requires_keyslot_proof_except_for_running_consumer_checks(tmp_path, monkeypatch, mounted):
    config = tmp_path / "spec.json"
    key = {"path": "/etc/luks-keys/data.key", "device": "/dev/disk/by-partlabel/data", "mapping": "data"}
    config.write_text(json.dumps({"mounts": {}, "keys": [key], "paths": []}))
    calls = []
    checked_paths = []
    monkeypatch.setattr(boot, "verify_key", lambda k: calls.append(("permissions", k)))
    monkeypatch.setattr(boot, "verify_unlock", lambda k: calls.append(("unlock", k)))
    monkeypatch.setattr(boot, "encrypted_storage", lambda path, **kwargs: checked_paths.append(path))
    monkeypatch.setattr(sys, "argv", ["boot.py", str(config)] + (["--mounted-storage"] if mounted else []) + ["/srv/data"])
    boot.main()
    assert calls == [("permissions", key["path"])] if mounted else calls == [("unlock", key)]
    assert checked_paths == [Path("/srv/data")]


def test_real_luks_keyslot_accepts_enrolled_key_and_rejects_replacement(tmp_path, monkeypatch):
    # Disposable image only: no mapping, mount or production device is changed.
    image = tmp_path / "synthetic.luks"
    with image.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024)
    key = tmp_path / "synthetic.key"
    key.write_bytes(os.urandom(64))
    subprocess.run(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode",
                    "--pbkdf", "pbkdf2", "--pbkdf-force-iterations", "1000",
                    "--key-file", str(key), str(image)], check=True, capture_output=True, timeout=30)
    # Device ancestry and UUID binding are tested separately; this exercises the
    # real cryptsetup keyslot command against a regular disposable image.
    monkeypatch.setattr(boot, "verify_key", lambda path: None)
    monkeypatch.setattr(boot, "key_device", lambda *args: ("synthetic-image", 0, 0))
    specification = {"path": str(key), "device": str(image), "mapping": "synthetic"}
    before = image.read_bytes()
    boot.verify_unlock(specification)
    key.write_bytes(os.urandom(64))
    with pytest.raises(ValueError, match="verification failed"):
        boot.verify_unlock(specification)
    assert image.read_bytes() == before


def test_fleet_boot_contract():
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = f.inputs.nixpkgs.lib;
      fleet = lib.filterAttrs (_: h: h.config.luxnix.storage.operatorUnlocked.enable) f.nixosConfigurations;
      # Validate the final architecture even for hosts with an explicit temporary exception.
      hosts = builtins.mapAttrs (_: h: h.extendModules { modules = [{
        luxnix.storage.operatorUnlocked.layout = lib.mkForce "boot-luks";
      }]; }) fleet;
    in builtins.mapAttrs (_: h: let c = h.config; in {
      root = c.fileSystems."/".device;
      swap = map (s: s.device) c.swapDevices;
      initrd = builtins.attrNames c.boot.initrd.luks.devices;
      crypttab = c.environment.etc.crypttab.text;
      mounts = builtins.attrNames c.fileSystems;
      devices = builtins.mapAttrs (_: fs: fs.device) c.fileSystems;
      units = builtins.attrNames c.systemd.services;
      guard = c.system.preSwitchChecks.encryptedStorage;
      failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
    }) hosts
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    hosts = json.loads(result.stdout)
    assert len(hosts) == 15
    for host, cfg in hosts.items():
        # The unrelated existing s-04 identity/CRL gate remains a release blocker.
        expected = ["Hub transfer requires authenticated HTTPS CRL endpoints and an independently provisioned crlTlsCaFile."] if host == "s-04" else []
        assert cfg["failures"] == expected, (host, cfg["failures"])
        assert cfg["root"] == "/dev/mapper/cryptroot"
        assert cfg["initrd"] == ["cryptroot"], host
        assert "/etc/secrets" not in cfg["mounts"]
        assert not any(u.startswith("luxnix-storage-unlock-") for u in cfg["units"])
        assert "luxnix-storage-migrate" not in cfg["units"]
        assert "luxnix-verify-boot-storage" in cfg["guard"]
        for line in cfg["crypttab"].splitlines():
            if line:
                assert "/etc/luks-keys/" in line and "headless" in line
    assert hosts["gc-10"]["swap"] == []
    for path in ["/var/lib/lx-annotate", "/var/lib/postgresql", "/var/backup/postgresql"]:
        assert hosts["gc-10"]["devices"][path] == "/dev/mapper/lx-data_raid01_disk1-data_part"
    assert "archive_hdd" in hosts["gs-02"]["crypttab"]


def test_every_btrfs_member_is_checked(tmp_path, monkeypatch):
    fsid = "test-filesystem"
    members = tmp_path / fsid / "devices"
    for name, number in [("first", "253:0"), ("second", "8:1")]:
        (members / name).mkdir(parents=True)
        (members / name / "dev").write_text(number)
    monkeypatch.setattr(boot, "BTRFS_SYSFS", tmp_path)
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": [
        {"source": "/dev/mapper/data[/storage]", "fstype": "btrfs", "uuid": fsid}]})
    actual_stat = boot.os.stat
    monkeypatch.setattr(boot.os, "stat", lambda p, **kw: SimpleNamespace(st_rdev=1)
                        if str(p).startswith("/dev/") else actual_stat(p, **kw))
    monkeypatch.setattr(boot, "encrypted_storage", lambda *a, **kw: None)
    checked = []
    def verify(device):
        checked.append(device)
        if device == "/dev/block/8:1":
            raise ValueError("Unencrypted second member")
    monkeypatch.setattr(boot, "require_luks2", verify)
    with pytest.raises(ValueError, match="second member"):
        boot.verify_mount("/srv/data", "/dev/mapper/data")
    assert "/dev/block/8:1" in checked


def test_plain_dm_crypt_is_not_luks2(monkeypatch):
    monkeypatch.setattr(boot, "_require_encrypted_device", lambda *a: None)
    monkeypatch.setattr(boot, "probe", lambda *a: {"blockdevices": [
        {"name": "/dev/mapper/data", "type": "crypt"}]})
    monkeypatch.setattr(boot.subprocess, "check_output", lambda *a, **kw: "  type: PLAIN\n")
    with pytest.raises(ValueError, match="LUKS2"):
        boot.require_luks2("/dev/mapper/data")


def test_old_bind_mount_prevents_cutover(monkeypatch):
    monkeypatch.setattr(boot.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    with pytest.raises(ValueError, match="Legacy container/bind"):
        boot.reject_retired_mount("/etc/secrets")


def test_sops_identity_stays_on_root_after_initial_unlock():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
          c = (f.nixosConfigurations.gc-10.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = f.inputs.nixpkgs.lib.mkForce "boot-luks";
            security.sops.operatorStorageKey = {
              enable = true;
              # Evaluation-only ciphertext placeholder; no decrypt operation.
              secretsFile = ./flake.lock;
              applicationSecrets.example = {};
              consumers = [ "lx-annotate.service" ];
            };
          }]; }).config;
      in {
        identity = c.sops.age.keyFile;
        generate = c.sops.age.generateKey;
        after = c.systemd.services.sops-install-secrets.after;
        consumer = c.systemd.services.lx-annotate.requires;
        initrd = builtins.attrNames c.boot.initrd.secrets;
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      }
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    cfg = json.loads(result.stdout)
    assert cfg["failures"] == []
    assert cfg["identity"] == "/var/lib/luxnix-secrets/sops-age/keys.txt"
    assert cfg["generate"] is False
    assert cfg["after"] == ["local-fs.target"]
    assert "sops-install-secrets.service" in cfg["consumer"]
    assert cfg["identity"] not in cfg["initrd"]


def test_wrong_btrfs_subvolume_is_not_accepted(monkeypatch):
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": [
        {"source": "/dev/mapper/data[/wrong]", "fstype": "btrfs", "fsroot": "/wrong"}]})
    with pytest.raises(ValueError, match="subvolume"):
        boot.verify_mount("/srv/data", "/dev/mapper/data", "btrfs", "subvol=application")


def test_gc10_explicit_legacy_maintenance_profile():
    expression = r'''
    let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        c = f.nixosConfigurations.gc-10.config;
    in { layout = c.luxnix.storage.operatorUnlocked.layout;
         migration = c.luxnix.storage.operatorUnlocked.migration.enable;
         root = c.fileSystems."/".device;
         swap = c.swapDevices;
         app = c.fileSystems."/var/lib/lx-annotate".device;
         guard = c.systemd.services.luxnix-storage-check-lx-annotate.serviceConfig.ExecStart;
         failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions); }
    '''
    result = subprocess.run(['nix', 'eval', '--impure', '--json', '--expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state['layout'] == 'legacy-containers'
    assert state['migration'] is False and state['swap'] == []
    assert state['root'] != '/dev/mapper/cryptroot'
    assert state['app'] == '/var/lib/luxnix-app-storage/application'
    assert 'secret_storage.py' in state['guard']
    assert state['failures'] == []
