"""Explicit plain root retains the existing protected-service boundary."""

import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def configuration():
    expression = r"""
      let f = builtins.getFlake ("git+file://" + toString ./.);
          lib = f.inputs.nixpkgs.lib;
          base = f.nixosConfigurations.gc-09;
          plain = base.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = lib.mkForce "unencrypted-root";
          }]; };
          encrypted = base.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.layout = lib.mkForce "boot-luks";
          }]; };
          ready = plain.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.autoStartProtectedServices = true;
          }]; };
          bao = plain.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.unlockMethod = lib.mkForce "local-openbao";
            luxnix.openbao.local = { enable = true; seal = "passphrase"; };
          }]; };
          bad = plain.extendModules { modules = [{
            luxnix.storage.operatorUnlocked.remoteUnlock.enable = true;
          }]; };
          summarize = host: let c = host.config; in {
            root = c.fileSystems."/".device;
            autoStart = c.luxnix.storage.operatorUnlocked.autoStartProtectedServices;
            startup = c.luxnix.storage.operatorUnlocked.startupServices;
            unlocks = builtins.attrNames c.boot.initrd.luks.devices;
            prechecks = builtins.attrNames c.system.preSwitchChecks;
            guards = builtins.mapAttrs (name: paths: {
              inherit paths;
              binds = c.systemd.services.${name}.bindsTo;
              requires = c.systemd.services.${name}.requires;
              wantedBy = c.systemd.services.${name}.wantedBy;
            }) c.luxnix.storage.operatorUnlocked.guardedServices;
            mounts = builtins.mapAttrs (_: fs: fs.options) c.fileSystems;
            failures = map (a: a.message)
              (builtins.filter (a: !a.assertion) c.assertions);
            accounts = c.system.activationScripts.luxnixPrepareBootAccountHashes.text
              or null;
          };
          root = {
            type = "luks"; name = "original-root";
            content = { type = "filesystem"; format = "ext4"; mountpoint = "/"; };
          };
          data = {
            type = "luks"; name = "existing-data"; initrdUnlock = false;
            content = { type = "filesystem"; format = "ext4";
              mountpoint = "/srv/existing"; };
          };
          raw.disko.devices.disk.test = {
            type = "disk"; device = "/dev/disk/by-id/test";
            content = { type = "gpt"; partitions = {
              root.content = root; data.content = data;
            }; };
          };
          transform = enable: mode: lib.evalModules { modules = [
            { options.disko = lib.mkOption { type = lib.types.attrs; }; }
            (import ../systems/x86_64-linux/encrypted-layout.nix {
              inherit lib;
              config.luxnix.storage.operatorUnlocked = {
                inherit enable; layout = mode; };
            } raw)
          ]; };
      in {
        plain = summarize plain; encrypted = summarize encrypted;
        ready = summarize ready;
        baoPrechecks = builtins.attrNames bao.config.system.preSwitchChecks;
        baoStartup = bao.config.systemd.services.openbao-local.wantedBy;
        bad = map (a: a.message)
          (builtins.filter (a: !a.assertion) bad.config.assertions);
        transformed = (transform true "unencrypted-root").config.disko;
        disabled = (transform false "unencrypted-root").config.disko;
        legacy = (transform true "legacy-containers").config.disko;
        fleetModes = builtins.mapAttrs (_: h:
          h.config.luxnix.storage.operatorUnlocked.layout) f.nixosConfigurations;
      }
    """.replace("import ../systems/", "import ./systems/")
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_plain_root_is_explicit_and_does_not_change_fleet(configuration):
    plain = configuration["plain"]
    assert plain["failures"] == []
    assert not plain["autoStart"] and plain["startup"] == []
    assert plain["root"] != "/dev/mapper/cryptroot"
    assert "cryptroot" not in plain["unlocks"]
    assert "encryptedStorage" not in plain["prechecks"]
    assert "unencrypted-root" not in configuration["fleetModes"].values()
    encrypted = configuration["encrypted"]
    assert encrypted["failures"] == []
    assert encrypted["autoStart"]
    assert encrypted["root"] == "/dev/mapper/cryptroot"
    assert "encryptedStorage" in encrypted["prechecks"]


def test_plain_root_keeps_guarded_mounts_and_staged_accounts(configuration):
    plain = configuration["plain"]
    assert plain["guards"] and plain["accounts"]
    for name, guard in plain["guards"].items():
        assert f"luxnix-storage-check-{name}.service" in guard["requires"]
        assert guard["binds"]
        assert guard["wantedBy"] == []
        for path in guard["paths"]:
            assert "noauto" in plain["mounts"][path]


def test_unwrap_only_explicit_root_preserve_secondary_and_legacy(configuration):
    partitions = configuration["transformed"]["devices"]["disk"]["test"]["content"][
        "partitions"
    ]
    assert partitions["root"]["content"]["type"] == "filesystem"
    assert partitions["data"]["content"]["type"] == "luks"
    assert partitions["data"]["content"]["name"] == "existing-data"
    for mode in ("disabled", "legacy"):
        root = configuration[mode]["devices"]["disk"]["test"]["content"]["partitions"][
            "root"
        ]
        assert root["content"]["type"] == "luks"
        assert root["content"]["name"] == "original-root"


def test_plain_root_rejects_early_unlock(configuration):
    assert any(
        "no early disk-unlock prompt" in message for message in configuration["bad"]
    )


def test_explicit_ready_selection_restores_automatic_consumers(configuration):
    ready = configuration["ready"]
    assert ready["failures"] == [] and ready["autoStart"]
    assert ready["startup"]
    for name in ready["startup"]:
        guard = ready["guards"][name]
        assert "multi-user.target" in guard["wantedBy"]
        assert f"luxnix-storage-check-{name}.service" in guard["requires"]


def test_unprovisioned_local_openbao_does_not_block_os_activation(configuration):
    assert "openbaoLocalPreflight" not in configuration["baoPrechecks"]
    assert configuration["baoStartup"] == []
