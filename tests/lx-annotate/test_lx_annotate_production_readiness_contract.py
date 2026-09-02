from __future__ import annotations

import gzip
import json
import os
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _eval_gc02(expression: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--impure",
            "--json",
            "--expr",
            (
                    'let cfg = (builtins.getFlake "path:'
                    f'{REPO_ROOT}").nixosConfigurations.gc-02.config; '
                f"in {expression}"
            ),
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_preflight_blocks_web_and_always_on_workers() -> None:
    evaluated = _eval_gc02(
        """
        {
          preflight = {
            inherit (cfg.systemd.services.lx-annotate-preflight) before requires;
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
    assert "lx-annotate.service" in preflight["before"]
    assert "lx-annotate-master-key-check.service" in preflight["requires"]
    assert "lx-annotate-load-base-data.service" in preflight["requires"]
    assert "lx-annotate-preflight.service" in evaluated["web"]["requires"]
    for worker in evaluated["workers"]:
        assert "lx-annotate-preflight.service" in worker["requires"]


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
        flake = builtins.getFlake "path:{REPO_ROOT}";
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
