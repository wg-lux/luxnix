"""HLS reconciliation must not hold web startup or crypto preflight hostage."""

import re
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


def test_hls_reconciliation_runs_after_web_and_queue_prerequisites() -> None:
    units = eval_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = flake.nixosConfigurations.gc-05.config;
          select = service: {
            inherit (service) before after wants requires wantedBy;
          };
        in {
          web = select cfg.systemd.services.lx-annotate;
          preflight = select cfg.systemd.services.lx-annotate-preflight;
          backfill = select cfg.systemd.services.lx-annotate-hls-backfill;
          worker = select cfg.systemd.services.lx-annotate-celery-ffmpeg-worker;
          timer = cfg.systemd.timers.lx-annotate-hls-backfill.timerConfig;
        }
        """
    )

    backfill_name = "lx-annotate-hls-backfill.service"
    for name in ("web", "preflight", "worker"):
        for edge in ("after", "wants", "requires"):
            assert backfill_name not in units[name][edge], (name, edge)
    for name in ("web", "preflight", "backfill"):
        assert "lx-annotate-master-key-check.service" in units[name]["requires"]
    backfill = units["backfill"]
    assert "lx-annotate.service" in backfill["after"]
    assert "lx-annotate.service" not in backfill["before"]
    for prerequisite in (
        "lx-annotate-preflight.service",
        "lx-annotate-celery-ffmpeg-worker.service",
        "redis-lx-annotate.service",
    ):
        assert prerequisite in backfill["after"]
        assert prerequisite in backfill["requires"]
    assert "multi-user.target" in backfill["wantedBy"]
    assert units["timer"]["Unit"] == backfill_name
    assert units["timer"]["OnUnitInactiveSec"] == "1h"


@pytest.mark.parametrize("command_status, expected", [(0, 0), (75, 1), (1, 255), (127, 255)])
def test_backfill_condition_preserves_runtime_failures(command_status: int, expected: int) -> None:
    source = (
        REPO_ROOT
        / "modules/nixos/services/lx-annotate-local/subservices/lx-annotate-hls-backfill.nix"
    ).read_text()
    # Exercise the real shell status mapping with only the Django command
    # replaced; no runtime package or database is required for this boundary.
    shell = source.split('"lx-annotate-hls-backfill-allowed" \'\'\n', 1)[1].split("\n  '';", 1)[0]
    shell = re.sub(r"if \$\{lib.escapeShellArg.*?''}; then", f"if (exit {command_status}); then", shell, count=1, flags=re.S)
    assert "${" not in shell
    result = subprocess.run(["bash", "-c", shell], check=False, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ([], ["--artifact-kind", "both", "--apply", "--json"]),
        (["--video-id", "54"], ["--artifact-kind", "both", "--apply", "--json", "--video-id", "54"]),
        (["--artifact-kind", "processed"], ["--apply", "--json", "--artifact-kind", "processed"]),
        (["--artifact-kind=raw"], ["--apply", "--json", "--artifact-kind=raw"]),
    ],
)
def test_hls_dispatch_preserves_application_priority(arguments: list[str], expected: list[str]) -> None:
    source = (REPO_ROOT / "modules/nixos/services/lx-annotate-local/scripts.nix").read_text()
    script = source.split('explicit_artifact_kind="false"', 1)[1].split("\n  '';", 1)[0]
    script = 'explicit_artifact_kind="false"' + script
    # Execute the real argument handling and dispatch, excluding runtime setup.
    start = script.index('    if [ "${if useWheelRuntime')
    end = script.index("    run_hls_materialization()", start)
    script = script[:start] + script[end:]
    script = script.replace('${effectiveRuntimePackage}/bin/lx-annotate-manage', 'dispatch')
    # A shell function models the command boundary; explicit exec has identical argv.
    script = script.replace('exec dispatch materialize_video_hls --apply --json "$@"',
                            'dispatch materialize_video_hls --apply --json "$@"; exit $?')
    probes = 'set -euo pipefail\nlog() { :; }\ndie() { exit 1; }\ndispatch() { printf "%s\\n" "$@"; }\n'
    result = subprocess.run(["bash", "-c", probes + script, "dispatch-test", *arguments], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["materialize_video_hls", *expected]
