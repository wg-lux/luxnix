"""Persistent disk identity must cross the host configuration boundary."""

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
     (True, False, "8:19", 0, 0)],
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
    lsblk() {{ echo '8:19'; }}
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
