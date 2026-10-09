"""Evaluate the worker constructor independently of host and application state."""

from __future__ import annotations

import json

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json, eval_result


def expression(override: str = "", result: str = "worker") -> str:
    constructor = REPO_ROOT / "modules/nixos/services/lx-annotate-local/worker.nix"
    return f"""
      let
        lib = (builtins.getFlake "__LUXNIX_FLAKE_URI__").inputs.nixpkgs.lib;
        mkWorker = import {json.dumps(str(constructor))} {{ inherit lib; }};
        pool = {{
          concurrency = 1; maxTasksPerChild = 2;
          memoryHigh = "1G"; memoryMax = "2G"; cpuQuota = "35%";
          cpuWeight = 100; ioWeight = 100; nice = 15; oomScoreAdjust = 750;
        }};
        base = {{
          unitName = "lx-annotate-celery-pipeline-worker";
          hostname = "pipeline"; queues = [ "pipeline" ]; inherit pool;
        }};
        worker = mkWorker (base // {{ {override} }});
      in {result}
    """


def test_defaults_and_resource_mapping() -> None:
    assert eval_json(expression()) == {
        "unitName": "lx-annotate-celery-pipeline-worker",
        "hostname": "pipeline",
        "queues": ["pipeline"],
        "mode": "always",
        "environment": {},
        "after": [],
        "wants": [],
        "requires": [],
        "concurrency": 1,
        "maxTasksPerChild": 2,
        "serviceConfig": {
            "MemoryHigh": "1G",
            "MemoryMax": "2G",
            "CPUQuota": "35%",
            "CPUWeight": 100,
            "IOWeight": 100,
            "Nice": 15,
            "OOMScoreAdjust": 750,
        },
    }


@pytest.mark.parametrize("field", ["unitName", "hostname", "queues", "pool"])
def test_required_fields_cannot_be_omitted(field: str) -> None:
    result = eval_result(
        expression(
            result=f'''
      (mkWorker (builtins.removeAttrs base [ "{field}" ])).hostname
    '''
        )
    )
    assert result.returncode != 0
    assert field in result.stderr


@pytest.mark.parametrize("mode", ["always", "manual", "timer"])
def test_optional_policy_is_preserved(mode: str) -> None:
    worker = eval_json(
        expression(f'''
      mode = "{mode}";
      onCalendar = "*-*-* 22:00:00"; randomizedDelaySec = "5m";
      persistentTimer = false; runtimeMaxSec = "7h"; timeoutStopSec = "6h15min";
      cudaVisibleDevices = "0";
      taskSoftTimeLimitSeconds = 60; taskHardTimeLimitSeconds = 90;
      environment = {{ OMP_NUM_THREADS = "1"; }};
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ]; requires = [ "gate.service" ];
    ''')
    )
    assert worker["mode"] == mode
    assert worker["persistentTimer"] is False
    assert worker["runtimeMaxSec"] == "7h"
    assert worker["timeoutStopSec"] == "6h15min"
    assert worker["cudaVisibleDevices"] == "0"
    assert worker["taskSoftTimeLimitSeconds"] == 60
    assert worker["taskHardTimeLimitSeconds"] == 90
    assert worker["environment"] == {"OMP_NUM_THREADS": "1"}
    assert worker["after"] == worker["wants"] == ["network-online.target"]
    assert worker["requires"] == ["gate.service"]


@pytest.mark.parametrize(
    "override, diagnostic",
    [
        ("queues = [];", "queues must not be empty"),
        ('queues = [ "pipeline" "pipeline" ];', "queues must be unique"),
        ('queues = [ "pipeline,default" ];', "queues"),
        ('mode = "sometimes";', "mode"),
        ('mode = "timer";', "timer mode requires"),
        (
            'mode = "timer"; onCalendar = "daily"; randomizedDelaySec = "5m";',
            "timer mode requires",
        ),
        (
            "taskSoftTimeLimitSeconds = 90; taskHardTimeLimitSeconds = 90;",
            "soft task limit",
        ),
        (
            "taskSoftTimeLimitSeconds = 91; taskHardTimeLimitSeconds = 90;",
            "soft task limit",
        ),
        ("taskHardTimeLimitSeconds = 0;", "taskHardTimeLimitSeconds"),
        ("unitName = null;", "unitName"),
        ('unitName = "worker.service";', "unitName"),
        ('hostname = "";', "hostname"),
        ("environment = { INVALID = 1; };", "environment.INVALID"),
        ("pool = pool // { concurrency = 0; };", "concurrency"),
        ("pool = pool // { nice = 20; };", "nice"),
        ("pool = pool // { oomScoreAdjust = -1001; };", "oomScoreAdjust"),
        ("pool = pool // { cpuWeight = 10001; };", "cpuWeight"),
        ('pool = builtins.removeAttrs pool [ "memoryMax" ];', "memoryMax"),
        ("pool = pool // { typo = 1; };", "typo"),
        ("typo = true;", "typo"),
    ],
)
def test_malformed_records_fail_even_when_only_hostname_is_read(
    override: str,
    diagnostic: str,
) -> None:
    result = eval_result(expression(override, "worker.hostname"))
    assert result.returncode != 0
    assert diagnostic in result.stderr
