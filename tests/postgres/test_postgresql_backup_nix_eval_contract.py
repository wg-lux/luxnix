from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TypedDict, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BACKUP_LOCATION = "/var/backup/postgresql"


class PostgreSQLBackupContract(TypedDict):
    backup_location: str
    backup_script: str
    tmpfiles: list[str]


def test_gc_10_postgresql_backup_uses_system_backup_directory() -> None:
    expression = """
      let
        flake = builtins.getFlake "git+file:///home/admin/luxnix";
        lib = flake.inputs.nixpkgs.lib;
        cfg = flake.nixosConfigurations.gc-10.config;
      in {
        backup_location = cfg.services.luxnix.postgresql.backupLocation;
        backup_script = builtins.readFile (
          lib.removeSuffix " "
            cfg.systemd.services.postgresqlBackup.serviceConfig.ExecStart
        );
        tmpfiles = cfg.systemd.tmpfiles.rules;
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    contract = cast(PostgreSQLBackupContract, json.loads(result.stdout))

    assert contract["backup_location"] == EXPECTED_BACKUP_LOCATION
    assert EXPECTED_BACKUP_LOCATION in contract["backup_script"]
    assert any(
        rule.startswith(f"d {EXPECTED_BACKUP_LOCATION} 0700 postgres postgres ")
        for rule in contract["tmpfiles"]
    )
    assert "/home/admin/postgresql-backup" not in contract["backup_script"]
