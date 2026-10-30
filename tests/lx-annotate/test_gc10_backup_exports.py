"""Host-only export routing and fail-closed device checks without real mounts."""

from functools import lru_cache
import shlex
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


@lru_cache(maxsize=1)
def _configuration():
    return eval_json(
        f"""
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = import {REPO_ROOT}/systems/x86_64-linux/gc-10/backup-exports.nix {{
            config.user.endoreg-service-user = {{
              name = "export-user"; group = "export-group";
            }};
            pkgs = {{ util-linux = "/test-tools"; coreutils = "/test-tools"; }};
          }};
        in cfg
        """
    )


def test_gc10_export_mount_is_lazy_scoped_and_nonwritable_when_unmounted():
    cfg = _configuration()
    backup = "/run/media/admin/Backup-24-11"
    target = "/var/lib/lx-annotate/data/storage/frame_annotation_exports"
    disk = cfg["fileSystems"][backup]
    assert disk["device"] == "/dev/disk/by-uuid/37bc8106-47d1-4963-ba25-9fd14b33db16"
    assert disk["fsType"] == "ext4"
    assert {"noauto", "nofail", "x-systemd.device-timeout=10s"} <= set(disk["options"])
    (mount,) = cfg["systemd"]["mounts"]
    (auto,) = cfg["systemd"]["automounts"]
    assert mount["what"] == f"{backup}/lx-annotate-exports"
    assert mount["where"] == auto["where"] == target
    assert mount["options"] == "bind,nodev,nosuid,noexec"
    assert (
        mount["mountConfig"]["DirectoryMode"]
        == auto["automountConfig"]["DirectoryMode"]
        == "0500"
    )
    assert (
        mount["unitConfig"]["RequiresMountsFor"]
        == auto["unitConfig"]["RequiresMountsFor"]
        == ["/var/lib/lx-annotate"]
    )
    assert "gc10-backup-exports-prepare.service" in mount["requires"]
    assert mount["bindsTo"] == ["run-media-admin-Backup\\x2d24\\x2d11.mount"]
    for unit in (mount, auto):
        assert unit["unitConfig"]["DefaultDependencies"] is False
        assert "local-fs.target" in unit["after"]
        assert unit["before"] == unit["conflicts"] == ["umount.target"]
    for name in ("lx-annotate", "lx-annotate-celery-ffmpeg-worker"):
        service = cfg["systemd"]["services"][name]
        assert (
            service["requires"]
            == service["after"]
            == [
                "var-lib-lx\\x2dannotate-data-storage-frame_annotation_exports.automount"
            ]
        )
    assert "disko" not in cfg


def test_gc10_composes_valid_mount_units_without_enabling_other_hosts():
    units = eval_json("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        name = "var-lib-lx\\\\x2dannotate-data-storage-frame_annotation_exports";
        cfg = flake.nixosConfigurations.gc-10.config;
      in {
        mount = cfg.systemd.units."${name}.mount".text;
        auto = cfg.systemd.units."${name}.automount".text;
        otherHost = builtins.hasAttr "${name}.automount"
          flake.nixosConfigurations.gc-02.config.systemd.units;
      }
    """)
    assert "DefaultDependencies=false" in units["auto"]
    assert "RequiresMountsFor=/var/lib/lx-annotate" in units["mount"]
    assert "Options=bind,nodev,nosuid,noexec" in units["mount"]
    assert units["otherHost"] is False


def test_prepare_grants_nginx_group_read_without_world_access():
    script = _configuration()["systemd"]["services"]["gc10-backup-exports-prepare"][
        "script"
    ]
    assert "install -d -m 0750 -o 'export-user'" in script
    assert "-g 'export-group'" in script


@pytest.mark.parametrize(
    "uuid,probe_status,symlink,expected",
    [
        ("37bc8106-47d1-4963-ba25-9fd14b33db16", 0, False, 0),
        ("different-device", 0, False, 1),
        ("", 1, False, 1),
        ("37bc8106-47d1-4963-ba25-9fd14b33db16", 0, True, 1),
    ],
)
def test_prepare_never_creates_directory_before_device_validation(
    uuid, probe_status, symlink, expected
):
    script = _configuration()["systemd"]["services"]["gc10-backup-exports-prepare"][
        "script"
    ]
    probes = f"""
      findmnt() {{ printf '%s\\n' {shlex.quote(uuid)}; return {probe_status}; }}
      install() {{ printf 'CREATE_DIRECTORY\\n'; }}
      function [() {{
        if [[ "$1" == -L ]]; then return {0 if symlink else 1}; fi
        builtin [ "$@"
      }}
    """
    result = subprocess.run(
        ["bash", "-c", probes + script], capture_output=True, text=True, check=False
    )
    assert result.returncode == expected, result.stderr
    assert ("CREATE_DIRECTORY" in result.stdout) == (expected == 0)
