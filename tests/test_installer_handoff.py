"""The RAM launcher runs only the plan's verified source and hands state back."""

import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from lx_administration.storage import boot_migration as migration
from lx_administration.storage import installer_handoff as handoff

REVISION = "e" * 40
SOURCE = {"revision": REVISION, "lock_sha256": "f" * 64}


@pytest.fixture
def ram(tmp_path, monkeypatch):
    state_root = tmp_path / "luxnix-state"
    state = state_root / "gc-09"
    state.mkdir(parents=True)
    (state / ".lock").touch(mode=0o600)
    source = state_root / "sources" / REVISION
    source.mkdir(parents=True)
    spec = tmp_path / "migration.json"
    spec.write_text(json.dumps({"host": "gc-09"}))
    monkeypatch.setattr(handoff, "SPEC", spec)
    # A developer's own SSH session must not move these tests into tmux.
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.setattr(handoff.recovery_media, "STATE_ROOT", state_root)
    monkeypatch.setattr(migration, "installer_environment", lambda: True)
    monkeypatch.setattr(migration, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(migration, "load_plan", lambda state: {"source": SOURCE})
    monkeypatch.setattr(migration, "source_identity", lambda path: SOURCE)
    calls = []
    monkeypatch.setattr(
        handoff.subprocess,
        "run",
        lambda command, **kw: calls.append((command, kw["env"]["PYTHONPATH"]))
        or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(handoff, "hand_back", lambda root: calls.append("hand back"))
    return state_root, source, calls


def test_launcher_runs_the_plans_own_source_then_hands_back(ram):
    _, source, calls = ram
    with pytest.raises(SystemExit) as done:
        handoff.main(["run", "--apply"])
    assert done.value.code == 0
    command, path = calls[0]
    assert command == [
        sys.executable,
        "-m",
        "lx_administration.storage.boot_setup",
        "run",
        "--apply",
        "--host",
        "gc-09",
    ]
    assert path == str(source)
    assert calls[-1] == "hand back"


def test_launcher_refuses_outside_the_ram_environment(ram, monkeypatch):
    _, _, calls = ram
    monkeypatch.setattr(migration, "installer_environment", lambda: False)
    with pytest.raises(SystemExit, match="only as root inside"):
        handoff.main(["run"])
    assert calls == []


def test_launcher_refuses_a_source_that_does_not_match_the_plan(ram, monkeypatch):
    _, _, calls = ram
    monkeypatch.setattr(migration, "source_identity", lambda path: {"revision": "x"})
    with pytest.raises(SystemExit, match="does not match the plan"):
        handoff.main(["run"])
    assert calls == []


def test_launcher_names_the_missing_source(ram):
    _, source, calls = ram
    source.rmdir()
    with pytest.raises(SystemExit, match="devenv shell luxnix migrate"):
        handoff.main(["run"])
    assert calls == []


def test_launcher_hands_back_after_a_failed_workflow(ram, monkeypatch):
    _, _, calls = ram
    monkeypatch.setattr(
        handoff.subprocess,
        "run",
        lambda command, **kw: calls.append("workflow") or SimpleNamespace(returncode=1),
    )
    with pytest.raises(SystemExit) as done:
        handoff.main(["run", "--apply"])
    assert done.value.code == 1
    assert calls == ["workflow", "hand back"]


def test_hand_back_returns_only_root_created_files_and_directories(
    tmp_path, monkeypatch
):
    root = tmp_path / "luxnix-state"
    (root / "gc-09").mkdir(parents=True)
    created = [root / "gc-09/provision.json", root / "gc-09/lifecycle.json"]
    for path in created:
        path.write_text("{}")
    (root / "gc-09/link").symlink_to("provision.json")
    operator = root.lstat()
    real = Path.lstat

    def lstat(path):
        info = real(path)
        if path == root:
            return info
        values = list(info)
        values[4] = 0  # created by root inside the RAM environment
        return os.stat_result(values)

    changed = []
    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        handoff.os, "lchown", lambda path, uid, gid: changed.append((path, uid, gid))
    )
    handed = handoff.hand_back(root)
    expected = {root / "gc-09", *created}
    assert set(handed) == expected
    assert {(Path(p), u, g) for p, u, g in changed} == {
        (path, operator.st_uid, operator.st_gid) for path in expected
    }


def test_hand_back_does_nothing_for_root_owned_state(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff.os, "geteuid", lambda: 0)
    real = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda p: os.stat_result([*list(real(p))[:4], 0, *list(real(p))[5:]]),
    )
    monkeypatch.setattr(
        handoff.os, "lchown", lambda *a: pytest.fail("root-owned state stays root's")
    )
    assert handoff.hand_back(tmp_path) == []
    assert stat.S_ISDIR(real(tmp_path).st_mode)


def test_ssh_sessions_continue_inside_tmux(monkeypatch):
    executed = []
    monkeypatch.setenv("SSH_CONNECTION", "192.0.2.1 50000 192.0.2.10 2222")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("PYTHONPATH", "/nix/store/runtime")
    monkeypatch.setattr(
        handoff.os, "execvp", lambda program, args: executed.append((program, args))
    )
    handoff.detach_from_ssh(["run", "--apply"])
    program, args = executed[0]
    assert program == "tmux"
    # -A reattaches to a running session instead of starting a second workflow.
    assert args[:5] == ["tmux", "new-session", "-A", "-s", "luxnix-migration"]
    assert args[5:7] == ["-e", "PYTHONPATH=/nix/store/runtime"]
    # The window stays open after the workflow, so its output can be read.
    assert args[7:11] == ["sh", "-c", handoff.HOLD_WINDOW, "sh"]
    assert args[-4:] == [
        "-m",
        "lx_administration.storage.installer_handoff",
        "run",
        "--apply",
    ]


@pytest.mark.parametrize(
    "environment",
    [{}, {"SSH_CONNECTION": "192.0.2.1 1 192.0.2.10 2222", "TMUX": "/tmp/t,1,0"}],
)
def test_console_and_existing_tmux_sessions_run_directly(monkeypatch, environment):
    for name in ("SSH_CONNECTION", "TMUX"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        handoff.os, "execvp", lambda *a: pytest.fail("must not leave this process")
    )
    handoff.detach_from_ssh(["run"])


def test_launcher_detaches_only_after_the_source_is_verified(ram, monkeypatch):
    _, _, calls = ram
    monkeypatch.setattr(migration, "source_identity", lambda path: {"revision": "x"})
    monkeypatch.setattr(
        handoff, "detach_from_ssh", lambda argv: pytest.fail("checked first")
    )
    with pytest.raises(SystemExit, match="does not match the plan"):
        handoff.main(["run"])


def test_the_window_shows_the_result_and_waits_for_enter():
    import subprocess

    result = subprocess.run(
        [
            *("sh", "-c", handoff.HOLD_WINDOW, "sh"),
            *("sh", "-c", "echo plan stopped; exit 3"),
        ],
        input="\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert "plan stopped" in result.stdout
    assert "ended with exit status 3. Press Enter" in result.stdout
