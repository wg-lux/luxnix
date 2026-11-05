"""Boot layout evaluation and fail-closed probes; physical boot is a separate lane."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import warnings
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
      arrays = builtins.mapAttrs (_: a: {
        inherit (a) level;
        inherit (a.content) type name device;
        filesystem = a.content.content.type;
      }) c.disko.devices.mdadm;
      swraid = c.boot.swraid.enable;
      swap = map (s: s.device) c.swapDevices;
      initrd = builtins.attrNames c.boot.initrd.luks.devices;
      crypttab = c.environment.etc.crypttab.text;
      mounts = builtins.attrNames c.fileSystems;
      devices = builtins.mapAttrs (_: fs: fs.device) c.fileSystems;
      mountOptions = builtins.mapAttrs (_: fs: fs.options) c.fileSystems;
      units = builtins.attrNames c.systemd.services;
      guard = c.system.preSwitchChecks.encryptedStorage;
      rootPrompt = c.boot.initrd.luks.devices.cryptroot.crypttabExtraOpts;
      rootKeyFile = c.boot.initrd.luks.devices.cryptroot.keyFile;
      bootKeyTools = builtins.filter (p:
        builtins.match ".*boot-decryption.*" (p.name or "") != null)
        c.environment.systemPackages;
      splash = c.boot.plymouth.enable;
      initrdUnits = builtins.attrNames c.boot.initrd.systemd.services;
      menuTimeout = c.boot.loader.timeout;
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
        for device in cfg["swap"]:
            if device.startswith("/dev/mapper/"):
                assert device == "/dev/mapper/cryptswap", host
        for line in cfg["crypttab"].splitlines():
            if line:
                name = line.split()[0]
                assert name in {"cryptswap", "luxnix-app-storage", "luxnix-secrets"} or name.startswith("luxnix-data-"), (host, name)
        assert "/etc/secrets" not in cfg["mounts"]
        assert not any(u.startswith("luxnix-storage-unlock-") for u in cfg["units"])
        assert "luxnix-storage-migrate" not in cfg["units"]
        assert "luxnix-verify-boot-storage" in cfg["guard"]
        assert "luxnix-setup-boot-password" in cfg["guard"]
        assert 'case "$2" in' in cfg["guard"]
        assert cfg["rootKeyFile"] is None, host
        assert cfg["bootKeyTools"] == [], host
        assert not any(
            option.startswith(("fido2-", "tpm2-", "pkcs11-", "keyfile-"))
            for option in cfg["rootPrompt"]
        ), host
        # Splash prompt without time or attempt limit; restart reaches older generations.
        assert {"timeout=0", "tries=0"} <= set(cfg["rootPrompt"]), host
        assert "x-systemd.device-timeout=0" in cfg["mountOptions"]["/"], host
        assert cfg["splash"], host
        assert {"luxnix-reboot-to-boot-menu", "luxnix-unlock-recovery-hint"} <= set(cfg["initrdUnits"]), host
        assert cfg["menuTimeout"] and cfg["menuTimeout"] > 0, host
        for line in cfg["crypttab"].splitlines():
            if line:
                assert "/etc/luks-keys/" in line and "headless" in line
    assert hosts["gc-10"]["swap"] == []
    for path in ["/var/lib/lx-annotate", "/var/lib/postgresql", "/var/backup/postgresql"]:
        assert hosts["gc-10"]["devices"][path] == "/dev/mapper/luxnix-app-storage"
    assert hosts["gc-10"]["arrays"] == {"application": {
        "level": 1, "type": "luks", "name": "luxnix-app-storage",
        "device": "/dev/md/application", "filesystem": "btrfs",
    }}
    assert hosts["gc-10"]["swraid"]
    assert "/dev/md/application" in hosts["gc-10"]["crypttab"]
    assert "archive_hdd" in hosts["gs-02"]["crypttab"]
    options = hosts["gs-02"]["mountOptions"]
    def dependencies(mount):
        return [option.replace(r"\x2d", "-") for option in options[mount]
                if option.startswith("x-systemd.requires=")]
    assert len(dependencies("/data2")) == 1
    assert "luxnix-data-data2" in dependencies("/data2")[0]
    assert len(dependencies("/archive")) == 4
    assert all("luxnix-data-archive" in option for option in dependencies("/archive"))


def test_boot_luks_requires_splash_password_screen():
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = f.inputs.nixpkgs.lib;
      c = (f.nixosConfigurations.gc-02.extendModules { modules = [{
        boot.plymouth.enable = lib.mkForce false;
      }]; }).config;
    in map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions)
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    assert any("Plymouth splash screen" in m for m in json.loads(result.stdout))



@pytest.mark.parametrize("host,splash,autologin", [
    ("gc-02", True, False),    # boot LUKS with explicit account chooser
    ("gc-05", True, False),    # shared fleet chooser policy
    ("s-01", True, False),     # boot LUKS, Plasma, no client account
    ("lx-test", False, False), # no operator-unlocked storage
])
def test_splash_and_wallet_unlock_follow_storage_layout(host, splash, autologin):
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      c = f.nixosConfigurations.HOST.config;
    in {
      splash = c.boot.plymouth.enable;
      autologin = c.services.displayManager.autoLogin.enable;
      user = c.services.displayManager.autoLogin.user;
      client = c.user.client.name;
      keyring = c.systemd.services.display-manager.serviceConfig.KeyringMode or null;
      pam = c.security.pam.services.sddm-autologin.text;
    }
    '''.replace("HOST", host)
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["splash"] is splash
    assert config["autologin"] is autologin
    loadkey = "pam_systemd_loadkey.so" in config["pam"]
    assert loadkey is autologin
    assert config["keyring"] != "inherit"


@pytest.mark.parametrize("option", [
    "roles.desktop.addons.plasma.bootAutoLogin",
    "services.displayManager.autoLogin.enable",
])
def test_desktop_autologin_cannot_be_reenabled(option):
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = f.inputs.nixpkgs.lib;
      c = (f.nixosConfigurations.gc-02.extendModules { modules = [{
        OPTION = lib.mkForce true;
        luxnix.storage.operatorUnlocked.remoteUnlock.enable = lib.mkForce true;
      }]; }).config;
    in map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions)
    '''.replace("OPTION", option)
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    assert any("autologin is disabled fleet-wide" in m for m in json.loads(result.stdout))


def test_every_exported_host_uses_password_login():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + toString ./.);
      in builtins.mapAttrs (_: h: let c = h.config; in {
        auto = c.services.displayManager.autoLogin.enable;
        bootAuto = c.roles.desktop.addons.plasma.bootAutoLogin;
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      }) f.nixosConfigurations
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    hosts = json.loads(result.stdout)
    assert {"gc-02", "gc-09", "gc-10", "gs-02"} <= hosts.keys()
    for name, policy in hosts.items():
        assert not policy["auto"] and not policy["bootAuto"], name
        login_failures = [message for message in policy["failures"]
                          if any(word in message.lower() for word in
                                 ("password", "autologin", "admin ", "client credentials"))]
        assert login_failures == [], (name, login_failures)
        if policy["failures"]:
            warnings.warn(f"{name}: unrelated deployment assertions remain: {policy['failures']}")


@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("encrypted", [False, True])
def test_every_btrfs_member_is_checked(tmp_path, monkeypatch, missing, encrypted):
    fsid = "4261572b-5aab-467a-b105-d7ab0beb9d7a"
    members = tmp_path / fsid / "devices"
    for name, number in [("first", "253:0"), ("second", "8:1")]:
        (members / name).mkdir(parents=True)
        (members / name / "dev").write_text(number)
    for identifier in ("1", "2"):
        metadata = tmp_path / fsid / "devinfo" / identifier
        metadata.mkdir(parents=True)
        (metadata / "missing").write_text("1" if missing else "0")
    monkeypatch.setattr(secret_storage, "BTRFS_SYSFS", tmp_path)
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": [
        {"source": "/dev/mapper/data[/storage]", "fstype": "btrfs", "uuid": fsid}]})
    actual_stat = boot.os.stat
    def block_stat(path, **kwargs):
        if str(path).startswith("/dev/"):
            return SimpleNamespace(st_mode=stat.S_IFBLK,
                st_rdev=os.makedev(8, 1) if str(path) == "/dev/block/8:1"
                else os.makedev(253, 0))
        return actual_stat(path, **kwargs)
    monkeypatch.setattr(boot.os, "stat", block_stat)
    monkeypatch.setattr(boot, "encrypted_storage", lambda *a, **kw: None)
    checked = []
    def verify(device):
        checked.append(device)
        if device == "/dev/block/8:1":
            raise ValueError("Unencrypted second member")
    monkeypatch.setattr(boot, "require_luks2", verify)
    if missing or encrypted:
        with pytest.raises(ValueError, match="Missing|second member"):
            boot.verify_mount("/srv/data", "/dev/mapper/data", encrypted=encrypted)
    else:
        boot.verify_mount("/srv/data", "/dev/mapper/data", encrypted=encrypted)
    assert bool(checked) == (encrypted and not missing)
    if checked:
        assert "/dev/block/8:1" in checked
    assert boot.filesystem_devices is secret_storage.filesystem_devices


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


@pytest.mark.parametrize("host", ["gc-09"])
def test_former_legacy_hosts_use_fleet_boot_luks(host):
    """gc-09 targets boot LUKS; gc-10 retains its installed container layout."""
    expression = r'''
    let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        c = f.nixosConfigurations.HOST.config;
    in { layout = c.luxnix.storage.operatorUnlocked.layout;
         root = c.boot.initrd.luks.devices.cryptroot.device;
         openbao = c.luxnix.openbao.local.enable;
         legacyUnits = builtins.filter (n: builtins.elem n [ "luxnix-storage-restack"
           "luxnix-storage-migrate" "luxnix-storage-unlock-luxnix-secrets" ])
           (builtins.attrNames c.systemd.services);
         secretsBind = c.fileSystems ? "/etc/secrets";
         preSwitch = c.system.preSwitchChecks ? encryptedStorage;
         failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions); }
    '''.replace("HOST", host)
    result = subprocess.run(['nix', 'eval', '--impure', '--json', '--expr', expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state['layout'] == 'boot-luks'
    assert state['root'] == '/dev/disk/by-partlabel/nixos_root'
    assert state['openbao'] is False
    assert state['legacyUnits'] == [] and state['secretsBind'] is False
    # Blocks switch/boot onto the still-plaintext installed disks.
    assert state['preSwitch'] is True
    assert state['failures'] == []


@pytest.mark.parametrize("same_directory", [False, True])
def test_bind_requires_exact_source_directory_not_only_encrypted_device(
    tmp_path, monkeypatch, same_directory
):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(boot, "probe", lambda *a: {"filesystems": [{
        "source": "/dev/mapper/data[/subvolume]", "fstype": "ext4",
        "fsroot": "/subvolume/actual", "uuid": "synthetic",
    }]})
    monkeypatch.setattr(boot.os.path, "samefile", lambda *a: same_directory)
    original_stat = boot.os.stat
    monkeypatch.setattr(boot.os, "stat", lambda p, **kw:
        SimpleNamespace(st_rdev=1) if str(p).startswith("/dev/")
        else original_stat(p, **kw))
    checked = []
    monkeypatch.setattr(boot, "encrypted_storage", lambda p: checked.append(p))
    monkeypatch.setattr(boot, "require_luks2", lambda p: checked.append(p))
    if same_directory:
        boot.verify_mount(str(target), str(source), "none")
        assert checked == [target, "/dev/mapper/data"]
    else:
        with pytest.raises(ValueError, match="bind source root"):
            boot.verify_mount(str(target), str(source), "none")
        assert not checked


def test_gc10_data_disk_is_one_luks_mapping_over_md_raid():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
          c = (f.nixosConfigurations.gc-10.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = f.inputs.nixpkgs.lib.mkForce "boot-luks";
          }]; }).config;
      in {
        arrays = builtins.attrNames c.disko.devices.mdadm;
        member = c.disko.devices.disk.data_raid01_disk1.content.partitions.data_part.content.type;
        array = c.disko.devices.mdadm.application.content.type;
        crypttab = c.environment.etc.crypttab.text;
        app = c.fileSystems."/var/lib/lx-annotate".device;
      }
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["arrays"] == ["application"]
    assert config["member"] == "mdraid" and config["array"] == "luks"
    assert "/etc/luks-keys/luxnix-app-storage.key" in config["crypttab"]
    assert config["app"] != "/var/lib/luxnix-app-storage/application"


def test_boot_luks_can_defer_guarded_service_startup():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
          c = (f.nixosConfigurations.gc-09.extendModules { modules = [{
            luxnix.storage.operatorUnlocked = {
              layout = f.inputs.nixpkgs.lib.mkForce "boot-luks";
              autoStartProtectedServices = false;
            };
          }]; }).config;
      in builtins.mapAttrs (name: _: c.systemd.services.${name}.wantedBy)
        c.luxnix.storage.operatorUnlocked.guardedServices
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    wanted = json.loads(result.stdout)
    assert "lx-annotate" in wanted and "postgresql" in wanted
    assert all(not targets for targets in wanted.values()), wanted


@pytest.mark.parametrize('mountpoint,name', [
    ('/var/lib/lx-annotate', 'luxnix-app-storage'),
    ('/var/lib/luxnix-app-storage', 'luxnix-app-storage'),
    ('/var/lib/luxnix-secrets', 'luxnix-secrets'),
    ('/etc/secrets', 'luxnix-secrets'),
    ('/', 'cryptroot'),
])
def test_mapper_names_survive_hardware_renaming_and_reject_collisions(mountpoint, name):
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
          lib = f.inputs.nixpkgs.lib;
          policy = import ./systems/x86_64-linux/encrypted-layout.nix {
            inherit lib;
            config.luxnix.storage.operatorUnlocked = { enable = true; layout = "boot-luks"; };
          };
          payload = { label = "existing-label"; content = {
            type = "filesystem"; format = "ext4"; mountpoint = "/var/lib/lx-annotate";
          }; };
          inspect = disk: part: duplicate: let
            c = (lib.evalModules { modules = [{ options = {
              disko = lib.mkOption { type = lib.types.raw; };
              assertions = lib.mkOption { type = lib.types.listOf lib.types.raw; };
            }; } (policy { disko.devices.disk.${disk}.content.partitions =
              { ${part} = payload; } // lib.optionalAttrs duplicate { second = payload; };
            })]; }).config;
          in {
            name = c.disko.devices.disk.${disk}.content.partitions.${part}.content.name;
            label = c.disko.devices.disk.${disk}.content.partitions.${part}.label;
            valid = builtins.all (a: a.assertion) c.assertions;
          };
      in { first = inspect "nvme_system" "data" false;
           renamed = inspect "replacement_controller" "other_partition" false;
           collision = inspect "disk" "data" true; }
    '''
    expression = expression.replace('mountpoint = "/var/lib/lx-annotate"',
                                    "mountpoint = " + json.dumps(mountpoint))
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["first"] == state["renamed"] == {
        "name": name, "label": "existing-label", "valid": True,
    }
    assert state["collision"]["valid"] is False


@pytest.mark.parametrize(
    "override",
    [
        'boot.initrd.luks.devices.cryptroot.keyFile = "/dev/disk/by-uuid/retired-key";',
        'boot.initrd.luks.devices.cryptroot.crypttabExtraOpts = [ "fido2-device=auto" ];',
        "luxnix.boot-decryption-stick.enable = true;",
    ],
)
def test_boot_luks_rejects_reintroduced_automatic_unlock(override):
    expression = r"""
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
          c = (f.nixosConfigurations.gc-02.extendModules {
            modules = [{ OVERRIDE }];
          }).config;
      in map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions)
    """.replace("OVERRIDE", override)
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert any(
        "Root unlock must prompt" in message or "enrollment is retired" in message
        for message in json.loads(result.stdout)
    )


def test_password_setup_runs_only_for_persistent_activation(tmp_path):
    expression = r"""
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      in f.nixosConfigurations.gc-02.config.system.preSwitchChecks.encryptedStorage
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--raw", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    import re

    script = re.sub(
        r"/nix/store/[^\s;]+/bin/luxnix-verify-boot-storage",
        'test "$VERIFY" = pass',
        result.stdout,
    )
    script = re.sub(
        r"/nix/store/[^\s;]+/bin/luxnix-setup-boot-password", 'touch "$MARKER"', script
    )
    marker = tmp_path / "prompted"
    for action in ["build", "dry-activate", "test", "boot", "switch"]:
        marker.unlink(missing_ok=True)
        result = subprocess.run(
            ["bash", "-ec", script, "check", "/nix/store/target", action],
            env={**os.environ, "VERIFY": "pass", "MARKER": str(marker)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert marker.exists() == (action in {"boot", "switch"})
    marker.unlink(missing_ok=True)
    result = subprocess.run(
        ["bash", "-ec", script, "check", "/nix/store/target", "boot"],
        env={**os.environ, "VERIFY": "fail", "MARKER": str(marker)},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and not marker.exists()


def test_gc02_authentication_retries_before_queueing_application():
    expression = r'''
      let f = builtins.getFlake ("git+file://" + toString ./.);
          c = f.nixosConfigurations.gc-02.config;
      in {
        offline = c.luxnix.vault.client.allowOffline;
        defer = c.luxnix.vault.client.auth.deferUntilProvisioned;
        auth = c.systemd.services.vault-auth-setup.serviceConfig;
      }
    '''
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["offline"] is value["defer"] is False
    assert value["auth"]["Restart"] == "on-failure"
    assert value["auth"]["RestartSec"] == "30s"
    assert value["auth"]["TimeoutStartSec"] == "45s"
    assert value["auth"]["ExecStartPost"].endswith("/bin/systemctl --no-block start lx-annotate.service")
