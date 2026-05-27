from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path("/home/admin/luxnix")
CONFIG_PATH = REPO_ROOT / "modules/nixos/services/lx-annotate-local/config.nix"


def _nix_eval_expr_json(expr: str) -> Any:
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expr, "--show-trace"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _gc_10_ffmpeg_stream_throttle_contract() -> dict[str, Any]:
    return _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "git+file:///home/admin/luxnix";
          cfg = flake.nixosConfigurations.gc-10.config;
          lxCfg = cfg.services.luxnix.lxAnnotateLocal;
          ffmpegWorker = cfg.systemd.services."lx-annotate-celery-ffmpeg-worker";
          throttleService = cfg.systemd.services."lx-annotate-ffmpeg-stream-throttle";
          throttleTimer = cfg.systemd.timers."lx-annotate-ffmpeg-stream-throttle";
        in {
          ffmpegWorker = {
            MemoryHigh = ffmpegWorker.serviceConfig.MemoryHigh;
            MemoryMax = ffmpegWorker.serviceConfig.MemoryMax;
            CPUQuota = ffmpegWorker.serviceConfig.CPUQuota;
            CPUWeight = ffmpegWorker.serviceConfig.CPUWeight;
            IOWeight = ffmpegWorker.serviceConfig.IOWeight;
            Nice = ffmpegWorker.serviceConfig.Nice;
          };
          throttle = {
            options = lxCfg.runtime.ffmpegStreamThrottle;
            serviceConfig = {
              Type = throttleService.serviceConfig.Type;
              WorkingDirectory = throttleService.serviceConfig.WorkingDirectory;
              ExecStart = throttleService.serviceConfig.ExecStart;
              EnvironmentFile = throttleService.serviceConfig.EnvironmentFile;
              ProtectSystem = throttleService.serviceConfig.ProtectSystem;
              PrivateTmp = throttleService.serviceConfig.PrivateTmp;
              NoNewPrivileges = throttleService.serviceConfig.NoNewPrivileges;
              ReadWritePaths = throttleService.serviceConfig.ReadWritePaths;
              user = throttleService.serviceConfig.User or null;
              group = throttleService.serviceConfig.Group or null;
            };
            after = throttleService.after;
            timerConfig = throttleTimer.timerConfig;
            timerWantedBy = throttleTimer.wantedBy;
          };
          streamLeaseSeconds =
            cfg.systemd.services."lx-annotate".environment.MEDIA_OPERATION_STREAM_LEASE_SECONDS
            or null;
        }
        """
    )


def _ffmpeg_throttle_script_source() -> str:
    source = CONFIG_PATH.read_text(encoding="utf-8")
    start = source.index("ffmpegStreamThrottleScript =")
    end = source.index("runtimeEnvScript =", start)
    return source[start:end]


def test_gc_10_ffmpeg_worker_uses_standard_normal_resource_profile() -> None:
    evaluated = _gc_10_ffmpeg_stream_throttle_contract()

    assert evaluated["ffmpegWorker"] == {
        "CPUQuota": "200%",
        "CPUWeight": 100,
        "IOWeight": 100,
        "MemoryHigh": "10G",
        "MemoryMax": "12G",
        "Nice": 0,
    }
    assert evaluated["streamLeaseSeconds"] == "300"


def test_gc_10_ffmpeg_stream_throttle_timer_and_root_oneshot_are_enabled() -> None:
    throttle = _gc_10_ffmpeg_stream_throttle_contract()["throttle"]

    assert throttle["options"]["enable"] is True
    assert throttle["options"]["interval"] == "10s"
    assert throttle["options"]["streaming"] == {
        "cpuQuota": "50%",
        "cpuWeight": 10,
        "ioWeight": 10,
    }
    assert throttle["serviceConfig"]["Type"] == "oneshot"
    assert throttle["serviceConfig"]["user"] is None
    assert throttle["serviceConfig"]["group"] is None
    assert throttle["serviceConfig"]["ProtectSystem"] == "full"
    assert "/run/lx-annotate" in throttle["serviceConfig"]["ReadWritePaths"]
    assert "lx-annotate-celery-ffmpeg-worker.service" in throttle["after"]
    assert throttle["timerWantedBy"] == ["timers.target"]
    assert throttle["timerConfig"]["OnBootSec"] == "10s"
    assert throttle["timerConfig"]["OnUnitActiveSec"] == "10s"
    assert (
        throttle["timerConfig"]["Unit"] == "lx-annotate-ffmpeg-stream-throttle.service"
    )


def test_ffmpeg_stream_throttle_applier_uses_only_allowlisted_runtime_profiles() -> (
    None
):
    script = _ffmpeg_throttle_script_source()

    assert "ffmpeg_stream_throttle_state --mode-only" in script
    assert 'case "$mode" in' in script
    assert "streaming)" in script
    assert "normal)" in script
    assert 'systemctl set-property --runtime "$worker_unit"' in script
    assert 'CPUQuota="$cpu_quota"' in script
    assert 'CPUWeight="$cpu_weight"' in script
    assert 'IOWeight="$io_weight"' in script
    assert "MemoryHigh" not in script
    assert "MemoryMax" not in script
