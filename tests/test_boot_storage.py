"""Boot layout evaluation and fail-closed probes; physical boot is a separate lane."""
import importlib.util
import json
from pathlib import Path
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


def test_fleet_boot_contract():
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = f.inputs.nixpkgs.lib;
      hosts = lib.filterAttrs (_: h: h.config.luxnix.storage.operatorUnlocked.enable) f.nixosConfigurations;
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
