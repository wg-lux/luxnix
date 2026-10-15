"""Persistent disk identity must cross the host configuration boundary."""

import json
import shlex
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


def test_host_disk_identity_reaches_mount_and_relief() -> None:
    result = eval_json(
        """
        let
          f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = (f.nixosConfigurations.gc-05.extendModules {
            modules = [{ roles.endoreg-client.paths = {
              storagePersistingDeviceId = f.inputs.nixpkgs.lib.mkForce "test-device";
              storagePersistingDevicePart = f.inputs.nixpkgs.lib.mkForce "part3";
            }; }];
          }).config;
        in {
          env = cfg.systemd.services.endoreg-mount-persisting-storage.serviceConfig.Environment;
          device = cfg.services.luxnix.lxAnnotateLocal.storageRelief.expectedDeviceId;
          partition = cfg.services.luxnix.lxAnnotateLocal.storageRelief.expectedDevicePart;
        }
        """
    )
    assert "STORAGE_PERSISTING_HDD_ID=test-device" in result["env"]
    assert "STORAGE_PERSISTING_HDD_PART=part3" in result["env"]
    assert result["device"] == "test-device"
    assert result["partition"] == "part3"


def test_gc05_mount_uses_the_verified_archive_identity() -> None:
    result = eval_json(
        """
        let
          f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = f.nixosConfigurations.gc-05.config;
        in {
          env = cfg.systemd.services.endoreg-mount-persisting-storage.serviceConfig.Environment;
          device = cfg.roles.endoreg-client.paths.storagePersistingDeviceId;
          partition = cfg.roles.endoreg-client.paths.storagePersistingDevicePart;
          reliefDevice = cfg.services.luxnix.lxAnnotateLocal.storageRelief.expectedDeviceId;
          reliefEnabled = cfg.services.luxnix.lxAnnotateLocal.storageRelief.enable;
        }
        """
    )
    device = "usb-Seagate_Expansion_HDD_00000000NT197WLC-0:0"
    assert result["device"] == result["reliefDevice"] == device
    assert result["partition"] == "part3"
    assert f"STORAGE_PERSISTING_HDD_ID={device}" in result["env"]
    assert "STORAGE_PERSISTING_HDD_PART=part3" in result["env"]
    assert result["reliefEnabled"] is False


@pytest.mark.parametrize(
    "available,mounted,mounted_number,mount_status,expected",
    [(True, True, "8:19", 0, 0), (True, True, "8:3", 0, 1),
     (False, True, "8:3", 0, 1), (True, False, "8:19", 32, 32),
     (True, False, "8:19", 0, 0), (False, False, "", 0, 0)],
)
def test_mount_script_rejects_missing_stale_and_failed_devices(
    available: bool, mounted: bool, mounted_number: str, mount_status: int, expected: int
) -> None:
    source = (REPO_ROOT / "modules/nixos/roles/endoreg-client/persisting-storage.nix").read_text()
    script = source.split('"mount-persisting-storage-service" \'\'\n', 1)[1].split("\n                '';", 1)[0]
    script = script.replace("''${", "${")
    # Stub operating-system probes; never mount or mutate a real device.
    probes = f"""
    function [() {{
      if [[ "$1" == '!' && "$2" == '-b' ]]; then return {1 if available else 0}; fi
      builtin [ "$@"
    }}
    mountpoint() {{ return {0 if mounted else 1}; }}
    lsblk() {{
      if [[ "$1" == '--json' ]]; then printf '%s\n' '{{"blockdevices": []}}';
      else echo '8:19'; fi
    }}
    findmnt() {{ echo '{mounted_number}'; }}
    mount() {{ echo MOUNT_ATTEMPT; return {mount_status}; }}
    export STORAGE_PERSISTING_EXTERNAL_DRIVE=true
    export STORAGE_PERSISTING_MOUNT_POINT=/test-mount
    export STORAGE_PERSISTING_HDD_ID=test-device
    export STORAGE_PERSISTING_HDD_PART=part3
    """
    result = subprocess.run(["bash", "-c", probes + script], check=False, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr
    if mounted or not available:
        assert "MOUNT_ATTEMPT" not in result.stdout


def _discovery_script() -> str:
    source = (REPO_ROOT / "modules/nixos/roles/endoreg-client/persisting-storage.nix").read_text()
    return source.split('"mount-persisting-storage-service" \'\'\n', 1)[1].split("\n                '';", 1)[0].replace("''${", "${")


@pytest.mark.parametrize(
    "devices,expected_names",
    [
        ([], []),
        ([{"name": "/dev/nvme0n1", "type": "disk", "tran": "nvme", "rm": False, "hotplug": False}], []),
        ([{"name": "/dev/sda", "type": "disk", "tran": "usb", "rm": False, "hotplug": True,
           "children": [{"name": "/dev/sda1", "type": "part", "rm": False, "hotplug": True}]}], ["/dev/sda"]),
        ([{"name": "/dev/mmcblk1", "type": "disk", "tran": None, "rm": True, "hotplug": False}], ["/dev/mmcblk1"]),
        ([{"name": "/dev/nvme1n1", "type": "disk", "tran": "nvme", "rm": False, "hotplug": True}], ["/dev/nvme1n1"]),
        ([{"name": "/dev/sdb", "type": "disk", "tran": "usb", "rm": 0, "hotplug": 1},
          {"name": "/dev/sda", "type": "disk", "tran": "usb", "rm": 0, "hotplug": 1}], ["/dev/sda", "/dev/sdb"]),
    ],
)
def test_unenrolled_discovery_never_mounts_arbitrary_disks(devices, expected_names):
    inventory = shlex.quote(json.dumps({"blockdevices": devices}))
    probes = f"""
    lsblk() {{ printf '%s\\n' {inventory}; }}
    mountpoint() {{ return 1; }}
    mount() {{ echo UNEXPECTED_MOUNT; return 99; }}
    export STORAGE_PERSISTING_EXTERNAL_DRIVE=true
    export STORAGE_PERSISTING_MOUNT_POINT=/test-mount
    export STORAGE_PERSISTING_HDD_ID=''
    """
    result = subprocess.run(["bash", "-c", probes + _discovery_script()], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    event = json.loads(result.stdout)
    assert event["state"] == ("enrollment_required" if expected_names else "absent")
    assert [device["name"] for device in event["devices"]] == expected_names
    assert result.stderr == ""


def test_unenrolled_existing_mount_fails_without_mutation():
    probes = """
    lsblk() { printf '%s\\n' '{"blockdevices": []}'; }
    mountpoint() { return 0; }
    mount() { echo UNEXPECTED_MOUNT; return 99; }
    umount() { echo UNEXPECTED_UNMOUNT; return 99; }
    export STORAGE_PERSISTING_EXTERNAL_DRIVE=true
    export STORAGE_PERSISTING_MOUNT_POINT=/test-mount
    export STORAGE_PERSISTING_HDD_ID=''
    """
    result = subprocess.run(["bash", "-c", probes + _discovery_script()], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["state"] == "unverified_existing_mount"


@pytest.mark.parametrize("inventory,probe_status", [("not-json", 0), ('{"blockdevices": null}', 0), ('{"blockdevices": []}', 1)])
def test_inventory_probe_failure_is_not_reported_as_absent(inventory, probe_status):
    probes = f"""
    lsblk() {{ printf '%s\\n' {shlex.quote(inventory)}; return {probe_status}; }}
    mount() {{ echo UNEXPECTED_MOUNT; return 99; }}
    export STORAGE_PERSISTING_EXTERNAL_DRIVE=true
    export STORAGE_PERSISTING_MOUNT_POINT=/test-mount
    export STORAGE_PERSISTING_HDD_ID=''
    """
    result = subprocess.run(["bash", "-c", probes + _discovery_script()], capture_output=True, text=True)
    assert result.returncode != 0
    assert result.stdout == ""


def test_reconnect_during_mount_fails_closed():
    probes = """
    function [() {
      if [[ "$1" == '!' && "$2" == '-b' ]]; then return 1; fi
      builtin [ "$@"
    }
    lsblk() {
      if [[ "$1" == '--json' ]]; then printf '%s\\n' '{"blockdevices": []}';
      elif [[ -n "${expected_device_number:-}" ]]; then echo '8:35';
      else echo '8:19'; fi
    }
    mountpoint() { return 1; }
    mount() { return 0; }
    findmnt() { echo '8:19'; }
    umount() { echo UNEXPECTED_UNMOUNT; return 99; }
    export STORAGE_PERSISTING_EXTERNAL_DRIVE=true
    export STORAGE_PERSISTING_MOUNT_POINT=/test-mount
    export STORAGE_PERSISTING_HDD_ID=test-device
    """
    result = subprocess.run(["bash", "-c", probes + _discovery_script()], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["state"] == "mounting"
    assert json.loads(result.stderr)["state"] == "lost"


def test_gc10_discovery_timer_is_bounded_and_has_no_implicit_device():
    result = eval_json(
        """
        let
          f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = f.nixosConfigurations.gc-10.config;
        in {
          device = cfg.roles.endoreg-client.paths.storagePersistingDeviceId;
          timer = cfg.systemd.timers.endoreg-mount-persisting-storage.timerConfig;
          timeout = cfg.systemd.services.endoreg-mount-persisting-storage.serviceConfig.TimeoutStartSec;
        }
        """
    )
    assert result["device"] is None
    assert result["timer"]["OnUnitInactiveSec"] == "30s"
    assert result["timer"]["AccuracySec"] == "1s"
    assert result["timeout"] == "30s"
