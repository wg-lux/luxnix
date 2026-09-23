"""Real local socket/lock contract and deterministic trailing-buffer coverage."""

import fcntl
import importlib.util
import json
import shutil
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "frontend_request_throttle", ROOT / "scripts/frontend-request-throttle.py"
)
assert spec is not None and spec.loader is not None
controller_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = controller_module
spec.loader.exec_module(controller_module)


@pytest.mark.parametrize("tail", [-1, float("nan"), float("inf")])
def test_invalid_tail(tail):
    with pytest.raises(ValueError):
        controller_module.ThrottleState(tail, lambda active: None)


def test_tail_restarts_and_active_requests_never_expire():
    profiles = []
    state = controller_module.ThrottleState(2, profiles.append)
    state.admit()
    state.reconcile(active=True, now=100)
    state.reconcile(active=False, now=101)
    state.reconcile(active=False, now=102.99)
    assert profiles == [True]
    state.admit()
    state.reconcile(active=False, now=103)
    state.reconcile(active=False, now=104.99)
    assert profiles == [True]
    state.reconcile(active=False, now=105)
    state.reconcile(active=False, now=106)
    assert profiles == [True, False]


def test_failed_profile_is_not_marked_applied():
    def fail(active):
        raise OSError("systemd unavailable")

    state = controller_module.ThrottleState(2, fail)
    with pytest.raises(OSError):
        state.admit()
    assert state.throttled is None


def test_concurrent_locks_and_controller_restart(tmp_path):
    path = tmp_path / "activity.lock"
    path.touch()
    with path.open("rb") as first, path.open("rb") as second:
        for request in [first, second]:
            fcntl.flock(request, fcntl.LOCK_SH)
        for _ in range(2):
            with path.open("rb") as probe:
                assert controller_module.has_activity(probe)
        first.close()
        with path.open("rb") as probe:
            assert controller_module.has_activity(probe)
            second.close()
            assert not controller_module.has_activity(probe)


def test_killed_request_releases_kernel_lock(tmp_path):
    path = tmp_path / "activity.lock"
    path.touch()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import fcntl, sys, time
with open(sys.argv[1], 'rb') as stream:
    fcntl.flock(stream, fcntl.LOCK_SH)
    print('ready', flush=True)
    time.sleep(30)
""",
            str(path),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with path.open("rb") as probe:
            assert controller_module.has_activity(probe)
            process.kill()
            process.wait(timeout=5)
            assert not controller_module.has_activity(probe)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.parametrize(
    "authorized,payload", [(True, b"+"), (False, b"+"), (True, b"x")]
)
def test_real_socket_admission(tmp_path, authorized, payload):
    path = tmp_path / "activity.lock"
    path.touch()
    profiles = []
    with socket.socket(socket.AF_UNIX) as listener, path.open("rb") as probe:
        listener.bind(str(tmp_path / "control.sock"))
        listener.listen()
        state = controller_module.ThrottleState(2, profiles.append)
        controller = controller_module.Controller(
            listener=listener,
            activity_file=probe,
            allowed_uid=os.getuid() if authorized else os.getuid() + 1,
            state=state,
        )
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(1)
                client.connect(str(tmp_path / "control.sock"))
                client.sendall(payload)
                controller.step()
                if authorized:
                    controller.step()
                try:
                    reply = client.recv(1)
                except ConnectionResetError:
                    reply = b""
                assert reply == (b"+" if authorized and payload == b"+" else b"")
                if reply:
                    assert profiles == [True]
        finally:
            controller.close()


def test_profile_only_changes_fixed_background_slice(monkeypatch):
    calls = []
    monkeypatch.setattr(
        controller_module.subprocess, "run", lambda args, **kw: calls.append(args)
    )
    for active in [True, False]:
        controller_module.apply_profile(
            active,
            systemctl="/bin/systemctl",
            cpu_quota="50%",
            cpu_weight=10,
            io_weight=10,
        )
    assert calls[0][1:] == [
        "set-property",
        "--runtime",
        "lx-annotate-background.slice",
        "CPUQuota=50%",
        "CPUWeight=10",
        "IOWeight=10",
    ]
    assert calls[1][-3:] == ["CPUQuota=", "CPUWeight=100", "IOWeight=100"]


def evaluate(body: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("nix") is None:
        pytest.skip("Nix required for module evaluation")
    expression = (
        "let flake = builtins.getFlake "
        + json.dumps(f"git+file://{ROOT}")
        + "; in "
        + body
    )
    return subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_nixos_worker_scope_and_runtime_contract():
    result = evaluate("""
      let c = flake.nixosConfigurations.gc-10.config;
          s = c.systemd.services;
          runtime = c.services.luxnix.lxAnnotateLocal.runtime;
      in {
        enabled = runtime.frontendRequestThrottle.enable;
        tail = runtime.frontendRequestThrottle.tailSeconds;
        legacy = runtime.ffmpegStreamThrottle.enable;
        workers = builtins.map (name: s.${name}.serviceConfig.Slice or "system.slice") [
          "lx-annotate-celery-ffmpeg-worker" "lx-annotate-celery-pipeline-worker"
          "lx-annotate-celery-frame-extraction-worker"
          "lx-annotate-celery-inference-worker"
          "lx-annotate-celery-training-worker" "lx-annotate-celery-llm-inference-worker"
        ];
        foreground = builtins.map
          (name: s.${name}.serviceConfig.Slice or "system.slice") [
          "lx-annotate" "postgresql" "lx-annotate-celery-worker"
        ];
        directory = s.lx-annotate.environment.LX_ANNOTATE_REQUEST_THROTTLE_DIRECTORY;
        controller = s.lx-annotate-request-throttle.serviceConfig.ExecStart;
        socket = c.systemd.sockets.lx-annotate-request-throttle.socketConfig.SocketMode;
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      }
    """)
    assert result.returncode == 0, result.stderr

    value = json.loads(result.stdout)
    assert value["enabled"] and value["tail"] == 2 and not value["legacy"]
    assert value["workers"] == ["lx-annotate-background.slice"] * 6
    assert value["foreground"] == ["system.slice"] * 3
    assert value["directory"] == "/run/lx-annotate-request-throttle"
    assert "--tail-seconds" in value["controller"]
    assert value["socket"] == "0660"
    assert value["failures"] == []


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ("frontendRequestThrottle.enable = false;", None),
        ("ffmpegStreamThrottle.enable = true;", "never both"),
        ('frontendRequestThrottle.cpuQuota = "0.00%";', "must be positive"),
    ],
)
def test_nixos_disabled_and_invalid_configurations(overrides, expected):
    result = evaluate(
        """
      let
        c = (flake.nixosConfigurations.gc-10.extendModules {
          modules = [{ services.luxnix.lxAnnotateLocal.runtime = {
            __OVERRIDES__
          }; }];
        }).config;
      in {
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
        directory = c.systemd.services.lx-annotate.environment
          .LX_ANNOTATE_REQUEST_THROTTLE_DIRECTORY;
        controller = builtins.hasAttr "lx-annotate-request-throttle" c.systemd.services;
      }
    """.replace("__OVERRIDES__", overrides)
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    if expected is None:
        assert value == {"failures": [], "directory": "", "controller": False}
    else:
        assert any(expected in message for message in value["failures"])


def test_packaged_runtime_gate_python_is_valid():
    import shlex

    result = evaluate("""
      let
        c = flake.nixosConfigurations.gc-10.config;
      in map (script: script.text)
        c.systemd.services.lx-annotate.serviceConfig.ExecStartPre
    """)
    assert result.returncode == 0, result.stderr
    scripts = json.loads(result.stdout)
    gate = next(s for s in scripts if "Request throttle middleware missing" in s)
    tokens = shlex.split(gate, comments=True)
    source = tokens[tokens.index("-c") + 1]
    compile(source, "<runtime gate>", "exec")
    assert "LX_ANNOTATE_REQUEST_THROTTLE_DIRECTORY" in source
