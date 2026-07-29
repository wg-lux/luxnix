from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _eval_gc02(expression: str) -> object:
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--impure",
            "--json",
            "--expr",
            (
                'let cfg = (builtins.getFlake "git+file://'
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
          preflight = cfg.systemd.services.lx-annotate-preflight;
          web = cfg.systemd.services.lx-annotate;
          workers = builtins.map
            (name: cfg.systemd.services.${name})
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
    acceptance = _eval_gc02("cfg.systemd.services.lx-annotate-acceptance")
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
    assert "exit 1" in source
    assert "sha256sum --check" in source
    assert 'mv "$pending_snapshot" "$completed_snapshot"' in source
    assert 'mv -Tf "$pending_latest" "$latest_link"' in source
    assert source.index("sha256sum --check") < source.index(
        'mv "$pending_snapshot" "$completed_snapshot"'
    )
    assert source.index('mv "$pending_manifest" "$manifest_file"') < source.index(
        'mv -Tf "$pending_latest" "$latest_link"'
    )
