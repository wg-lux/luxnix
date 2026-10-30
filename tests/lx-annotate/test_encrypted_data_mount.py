"""Execute the rendered guard without touching host mounts, devices or secrets."""

from functools import lru_cache
import shlex
import subprocess

import pytest

from nix_eval_helpers import eval_json


@lru_cache(maxsize=1)
def _mount_script() -> str:
    result = eval_json("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        modulePath = "/modules/nixos/services/lx-annotate-local/scripts/"
          + "encrypted-data.nix";
        scripts = import (flake.outPath + modulePath) {
          lib = flake.inputs.nixpkgs.lib;
          pkgs = {
            writeShellScriptBin = name: text: text; util-linux = "/test-tools";
          };
          cfg.runtime.managedEncryptedData = {
            mapperName = "test-data"; luksUuid = "expected-uuid";
            luksUuidFile = null; keyFile = "/test-key";
            fsType = "ext4"; owner = "test"; group = "test"; dirMode = "0750";
          };
          lxAnnotateRuntime = {
            paths.envDataDir = "/test-mount";
            runtime.encryptedDataMountOptions = "";
          };
        };
      in scripts.lxAnnotateEncryptedDataMountScript
    """)
    assert isinstance(result, str)
    return result


@pytest.mark.parametrize(
    "source,filesystem,mapping_type,uuid,status,expected",
    [
        ("/dev/dm-0", "ext4", "LUKS2", "expected-uuid", 0, 0),
        ("/dev/mapper/test-data", "ext4", "LUKS1", "expected-uuid", 0, 0),
        ("/dev/sda1", "ext4", "LUKS2", "expected-uuid", 0, 1),
        ("/dev/dm-0", "xfs", "LUKS2", "expected-uuid", 0, 1),
        ("/dev/dm-0", "ext4", "PLAIN", "expected-uuid", 0, 1),
        ("/dev/dm-0", "ext4", "LUKS2", "wrong-uuid", 0, 1),
        ("/dev/dm-0", "ext4", "LUKS2", "expected-uuid", 1, 1),
        ("/dev/dm-0", "", "LUKS2", "expected-uuid", 0, 1),
        ("", "ext4", "LUKS2", "expected-uuid", 0, 1),
        ("/unresolvable", "ext4", "LUKS2", "expected-uuid", 0, 1),
    ],
)
def test_existing_mount_requires_exact_encrypted_identity(
    source: str,
    filesystem: str,
    mapping_type: str,
    uuid: str,
    status: int,
    expected: int,
) -> None:
    probes = f"""
      function [() {{
        if [[ "$1" == '!' && "$2" == '-f' ]]; then return 1; fi
        builtin [ "$@"
      }}
      mountpoint() {{ return 0; }}
      cryptsetup() {{
        case "$1" in
          status)
            printf '  type: %s\\n  device: /dev/test-backing\\n' \\
              {shlex.quote(mapping_type)}
            return {status} ;;
          luksUUID) printf '%s\\n' {shlex.quote(uuid)} ;;
          *) echo UNEXPECTED_MUTATION; return 99 ;;
        esac
      }}
      findmnt() {{
        if [[ "${{!#}}" == SOURCE ]]; then printf '%s\\n' {shlex.quote(source)};
        else printf '%s\\n' {shlex.quote(filesystem)}; fi
      }}
      readlink() {{
        if [[ "$2" == /unresolvable ]]; then return 1; fi
        if [[ "$2" == /dev/mapper/test-data ]]; then echo /dev/dm-0;
        else printf '%s\\n' "$2"; fi
      }}
      install() {{ echo UNEXPECTED_MUTATION; return 99; }}
      chown() {{ echo UNEXPECTED_MUTATION; return 99; }}
      chmod() {{ echo UNEXPECTED_MUTATION; return 99; }}
    """
    result = subprocess.run(
        ["bash", "-c", probes + _mount_script()],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert "UNEXPECTED_MUTATION" not in result.stdout
    assert ("Verified encrypted data" in result.stdout) == (expected == 0)
