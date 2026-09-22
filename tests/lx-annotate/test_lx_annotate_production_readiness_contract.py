from __future__ import annotations

import gzip
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from nix_eval_helpers import FLAKE_URI_PLACEHOLDER, REPO_FLAKE_URI, eval_json


REPO_ROOT = Path(__file__).resolve().parents[2]


def _eval_gc02(expression: str) -> dict[str, Any]:
    return eval_json(
        f'let cfg = (builtins.getFlake "{FLAKE_URI_PLACEHOLDER}")'
        f".nixosConfigurations.gc-02.config; in {expression}"
    )


def test_diagnostic_preflight_does_not_block_web_and_always_on_workers() -> None:
    evaluated = _eval_gc02(
        """
        {
          preflight = {
            inherit (cfg.systemd.services.lx-annotate-preflight) before requires wantedBy;
          };
          web = {
            inherit (cfg.systemd.services.lx-annotate) requires;
          };
          workers = builtins.map
            (name: { inherit (cfg.systemd.services.${name}) requires; })
            [
              "lx-annotate-celery-worker"
              "lx-annotate-celery-pipeline-worker"
              "lx-annotate-celery-frame-extraction-worker"
              "lx-annotate-celery-ffmpeg-worker"
              "lx-annotate-celery-inference-worker"
            ];
        }
        """
    )

    preflight = evaluated["preflight"]
    assert preflight["before"] == []
    assert preflight["wantedBy"] == []
    assert "lx-annotate-master-key-check.service" in preflight["requires"]
    assert "lx-annotate-load-base-data.service" in preflight["requires"]
    for service in [evaluated["web"], *evaluated["workers"]]:
        assert "lx-annotate-preflight.service" not in service["requires"]
        assert "lx-annotate-data-recovery.service" not in service["requires"]
        assert "lx-annotate-master-key-check.service" in service["requires"]
        assert "lx-annotate-load-base-data.service" in service["requires"]


def test_live_acceptance_requires_preflight_web_nginx_and_workers() -> None:
    acceptance = _eval_gc02(
        "{ inherit (cfg.systemd.services.lx-annotate-acceptance) requires; }"
    )
    required = set(acceptance["requires"])

    assert {
        "lx-annotate-preflight.service",
        "lx-annotate.service",
        "nginx.service",
        "lx-annotate-celery-worker.service",
        "lx-annotate-celery-pipeline-worker.service",
    } <= required


def test_fleet_boot_does_not_pull_diagnostics_or_legacy_recovery() -> None:
    fleet = eval_json(
        '''
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          lib = flake.inputs.nixpkgs.lib;
        in builtins.mapAttrs (_: host:
          lib.mapAttrs (_: service: {
            inherit (service) after before wants requires wantedBy;
          }) host.config.systemd.services
        ) { inherit (flake.nixosConfigurations) gc-02 gc-10 gs-02; }
        '''
    )
    for host, units in fleet.items():
        pending = [name for name, unit in units.items() if unit["wantedBy"]]
        reached = set()
        while pending:
            name = pending.pop()
            if name in reached or name not in units:
                continue
            reached.add(name)
            pending.extend(
                dependency.removesuffix(".service")
                for edge in ("wants", "requires")
                for dependency in units[name][edge]
                if dependency.endswith(".service")
            )
        assert "lx-annotate" in reached, host
        assert "lx-annotate-migrate" in reached, host
        assert "lx-annotate-master-key-check" in reached, host
        assert "lx-annotate-data-recovery" not in reached, host
        assert "lx-annotate-preflight" not in reached, host


def test_reviewed_legacy_recovery_can_be_explicitly_required() -> None:
    units = eval_json(
        '''
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          host = flake.nixosConfigurations.gc-02.extendModules {
            modules = [{
              services.luxnix.lxAnnotateLocal.dataRecovery.runBeforeStartup = true;
            }];
          };
        in {
          web = host.config.systemd.services.lx-annotate.requires;
          recovery = host.config.systemd.services.lx-annotate-data-recovery.before;
        }
        '''
    )
    assert "lx-annotate-data-recovery.service" in units["web"]
    assert "lx-annotate-migrate.service" in units["recovery"]


def test_backup_stages_and_verifies_before_latest_publication() -> None:
    source = (
        REPO_ROOT
        / "modules/nixos/services/lx-annotate-local/scripts/hub-backup.nix"
    ).read_text(encoding="utf-8")

    assert "runtime root is missing" in source
    assert "PostgreSQL backup credential is missing or unreadable" in source
    assert "free space is below the configured reserve before staging" in source
    assert "staging would consume the configured free-space reserve" in source
    assert "exit 1" in source
    assert 'gzip --test "$database_dump_source"' in source
    assert '"$pending_snapshot/$database_dump_relative"' in source
    assert "postgresql-pg_dumpall-sql-gzip" in source
    assert "sha256sum --check" in source
    assert 'mv "$pending_snapshot" "$completed_snapshot"' in source
    assert 'mv -Tf "$pending_latest" "$latest_link"' in source
    assert source.index("sha256sum --check") < source.index(
        'mv "$pending_snapshot" "$completed_snapshot"'
    )
    assert source.index('"$pending_snapshot/$database_dump_relative"') < source.index(
        "sha256sum --check"
    )
    assert source.index('mv "$pending_manifest" "$manifest_file"') < source.index(
        'mv -Tf "$pending_latest" "$latest_link"'
    )


def test_hub_backup_publishes_database_and_media_as_one_restore_point(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    incoming_root = tmp_path / "incoming"
    snapshot_root = tmp_path / "snapshots"
    manifest_root = tmp_path / "manifests"
    credential_root = tmp_path / "credentials"
    runtime_root.mkdir()
    credential_root.mkdir()
    (runtime_root / "processed-media.bin").write_bytes(b"anonymized-media")
    database_dump = credential_root / "hub-postgresql.sql.gz"
    with gzip.open(database_dump, "wb") as compressed:
        compressed.write(b"CREATE DATABASE hub_test;\n")

    def nix_string(value: Path) -> str:
        return json.dumps(str(value))

    expression = f"""
      let
        flake = builtins.getFlake "{REPO_FLAKE_URI}";
        pkgs = flake.inputs.nixpkgs.legacyPackages.x86_64-linux;
        generated = import {REPO_ROOT}/modules/nixos/services/lx-annotate-local/scripts/hub-backup.nix {{
          config.networking.hostName = "hub-backup-test";
          inherit (pkgs) lib;
          inherit pkgs;
          cfg.hub.backup = {{
            sourceRuntimeDir = {nix_string(runtime_root)};
            incomingDir = {nix_string(incoming_root)};
            snapshotDir = {nix_string(snapshot_root)};
            manifestDir = {nix_string(manifest_root)};
            retainCount = 2;
            minimumFreeBytes = 1;
            exclude = [];
          }};
        }};
      in generated.runLocalHubBackupScript
    """
    built = subprocess.run(
        [
            "nix",
            "build",
            "--impure",
            "--no-link",
            "--print-out-paths",
            "--expr",
            expression,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    backup_command = Path(built.stdout.strip()) / "bin/runLxAnnotateHubBackup"
    environment = os.environ | {"CREDENTIALS_DIRECTORY": str(credential_root)}
    environment.pop("LD_LIBRARY_PATH", None)

    completed = subprocess.run(
        [str(backup_command)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    latest_snapshot = (snapshot_root / "latest").resolve(strict=True)
    copied_dump = latest_snapshot / "database/all.sql.gz"
    assert copied_dump.read_bytes() == database_dump.read_bytes()
    assert (latest_snapshot / "processed-media.bin").read_bytes() == b"anonymized-media"
    manifest = json.loads(next(manifest_root.glob("*.json")).read_text())
    assert manifest["database_dump"]["relative_path"] == "database/all.sql.gz"
    assert manifest["database_dump"]["format"] == "postgresql-pg_dumpall-sql-gzip"
    checksums = next(manifest_root.glob("*.sha256")).read_text()
    assert "database/all.sql.gz" in checksums
    assert "processed-media.bin" in checksums

    database_dump.write_bytes(b"not-a-gzip-dump")
    rejected = subprocess.run(
        [str(backup_command)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert (snapshot_root / "latest").resolve(strict=True) == latest_snapshot
    assert not tuple(snapshot_root.glob(".pending-*"))
