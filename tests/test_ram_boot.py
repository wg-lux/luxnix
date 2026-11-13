"""Hash-free RAM staging preserves host, source, artifact and apply boundaries."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

import pytest

from lx_administration import cli
from lx_administration.storage import migration_boot as boot
from lx_administration.storage import ram_boot as ram


def test_luxnix_dispatches_ram_without_entering_installation(monkeypatch):
    calls = []
    monkeypatch.setattr(ram, "main", calls.append)
    cli.main(["ram", "push", "gc-09"])
    assert calls == [["push", "gc-09"]]


@pytest.mark.parametrize("host", ["../gc-09", "-oProxyCommand=nope", "gc-09;touch-x"])
def test_invalid_host_never_reaches_inventory_or_ssh(monkeypatch, host):
    monkeypatch.setattr(ram.sb, "run", lambda *a: pytest.fail("no inventory"))
    with pytest.raises(ValueError, match="one inventory host"):
        ram.target(host, Path("/release"))


def test_push_cannot_start_the_host(monkeypatch):
    monkeypatch.setattr(ram, "push", lambda *a: pytest.fail("no operation"))
    with pytest.raises(SystemExit) as error:
        ram.main(["push", "gc-09", "--apply"])
    assert error.value.code == 2


@pytest.mark.parametrize("apply", [False, True])
def test_remote_start_preserves_explicit_apply_and_quoted_paths(
    tmp_path, monkeypatch, apply
):
    monkeypatch.setattr(ram.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ram.socket, "gethostname", lambda: "controller")
    root = "/durable/release with spaces"
    receipt = {
        "host": "gc-09",
        "checkout": root,
        "receiver": "/state/receiver.py",
        "receiver_sha256": "a" * 64,
        "revision": "a" * 40,
    }
    ram.save(ram.state_dir("gc-09") / "prepared.yml", receipt)
    monkeypatch.setattr(
        ram,
        "target",
        lambda *a: (["-o", "StrictHostKeyChecking=yes", "admin@target"], root),
    )
    calls = []
    monkeypatch.setattr(ram.subprocess, "call", lambda argv: calls.append(argv) or 0)
    args = argparse.Namespace(host="gc-09", flake=Path("/controller"), apply=apply)
    assert ram.start(args) == 0
    assert calls[0][:2] == ["ssh", "-tt"]
    command = calls[0][-1]
    words = shlex.split(command)
    assert words[:4] == ["cd", root, "&&", "exec"]
    assert json.loads(words[-1])["apply"] is apply
    assert "StrictHostKeyChecking=yes" in calls[0]
    assert "--no-check-sigs" not in command


def test_receiver_hash_is_checked_even_with_python_optimization(tmp_path):
    # Exercise the exact bootstrap sent over SSH, with altered receiver bytes.
    receiver = tmp_path / "receiver.py"
    receiver.write_text("raise RuntimeError('must never execute')")
    receipt = {
        "receiver": str(receiver),
        "receiver_sha256": "0" * 64,
        "revision": "a" * 40,
    }
    # Obtain the production bootstrap from the command rather than duplicating it.
    from unittest.mock import patch

    with (
        patch.object(
            ram, "load", return_value=receipt | {"host": "gc-09", "checkout": "/root"}
        ),
        patch.object(ram, "target", return_value=(["admin@target"], "/root")),
        patch.object(ram.socket, "gethostname", return_value="controller"),
        patch.object(ram.subprocess, "call", return_value=0) as call,
    ):
        ram.start(argparse.Namespace(host="gc-09", flake=Path("/root"), apply=True))
    words = shlex.split(call.call_args.args[0][-1])
    code = words[words.index("-c") + 1]
    result = subprocess.run(
        ["python", "-O", "-c", code, json.dumps(receipt)],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "RAM helper changed" in result.stderr
    assert "must never execute" not in result.stderr


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(ram.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ram.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(ram.sb, "reviewed_source", lambda *a: "a" * 40)
    monkeypatch.setattr(boot, "validate_spec", lambda *a: None)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in ["kernel", "initrd", "cmdline"]:
        (bundle / name).write_text("verified-" + name)
    spec = {"host": "gc-09", "revision": "a" * 40, "boot_trust": "host-kexec"}
    (bundle / "manifest.json").write_text(json.dumps(spec))

    def test_hashes(path):
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
        }

    monkeypatch.setattr(ram, "hashes", test_hashes)
    ram.save(
        ram.state_dir("gc-09") / "prepared.yml",
        {
            "host": "gc-09",
            "revision": "a" * 40,
            "checkout": "/release",
            "bundle": str(bundle),
            "hashes": test_hashes(bundle),
        },
    )
    calls = []
    monkeypatch.setattr(
        ram.subprocess, "call", lambda *a, **k: calls.append((a, k)) or 0
    )
    return bundle, calls


@pytest.mark.parametrize("apply", [False, True])
def test_local_start_delegates_to_existing_kexec_guards(prepared, apply):
    bundle, calls = prepared
    assert ram.start_local("gc-09", "/release", apply) == 0
    command = calls[0][0][0]
    assert command[:3] == ["nix", "shell", "--impure"]
    assert "/devenv/scripts.nix" in command[4]
    assert command[5:10] == [
        "--command",
        "migration-boot",
        "kexec",
        "gc-09",
        "--bundle",
    ]
    assert command[10] == str(bundle)
    assert ("--apply" in command) is apply


def test_changed_artifacts_never_reach_kexec(prepared):
    bundle, calls = prepared
    (bundle / "initrd").write_text("changed")
    with pytest.raises(ValueError, match="artifacts changed"):
        ram.start_local("gc-09", "/release", True)
    assert not calls


def test_wrong_host_never_prepares_or_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(ram.socket, "gethostname", lambda: "other")
    monkeypatch.setattr(
        ram.sb, "reviewed_source", lambda *a: pytest.fail("no source access")
    )
    with pytest.raises(ValueError, match="another host"):
        ram.prepare_local({"host": "gc-09", "checkout": str(tmp_path)}, "")


def test_build_failure_never_publishes_a_prepared_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(ram.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ram.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(ram.sb, "reviewed_source", lambda *a: "a" * 40)
    monkeypatch.setattr(boot, "reviewed_spec", lambda *a: {})

    def fail(*a):
        raise ValueError("build failed")

    monkeypatch.setattr(boot, "build_attribute", fail)
    with pytest.raises(ValueError, match="build failed"):
        ram.prepare_local(
            {
                "host": "gc-09",
                "checkout": "/release",
                "revision": "a" * 40,
                "settings": {},
            },
            "code",
        )
    assert not (ram.state_dir("gc-09") / "prepared.yml").exists()


def test_store_path_traversal_is_not_an_immutable_bundle():
    with pytest.raises(ValueError, match="immutable Nix store"):
        ram.hashes(Path("/nix/store/../../tmp/operator-bundle"))


def test_changed_source_never_reaches_kexec(prepared, monkeypatch):
    _, calls = prepared
    monkeypatch.setattr(ram.sb, "reviewed_source", lambda *a: "b" * 40)
    with pytest.raises(ValueError, match="source changed"):
        ram.start_local("gc-09", "/release", True)
    assert not calls


def test_prepare_publishes_a_host_and_artifact_bound_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(ram.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ram.socket, "gethostname", lambda: "gc-09")
    monkeypatch.setattr(ram.sb, "reviewed_source", lambda *a: "a" * 40)
    bundle = tmp_path / "native-bundle"
    bundle.mkdir()
    spec = {"host": "gc-09", "revision": "a" * 40}
    (bundle / "manifest.json").write_text(json.dumps(spec))
    monkeypatch.setattr(boot, "reviewed_spec", lambda *a: spec)
    monkeypatch.setattr(boot, "build_attribute", lambda *a: bundle)
    monkeypatch.setattr(ram, "hashes", lambda *a: {"kernel": "verified"})
    record = ram.prepare_local(
        {
            "host": "gc-09",
            "checkout": "/release",
            "revision": "a" * 40,
            "settings": {"host": "gc-09"},
        },
        "operator helper",
    )
    directory = ram.state_dir("gc-09")
    assert ram.load(directory / "prepared.yml") == record
    assert record["receiver_sha256"] == hashlib.sha256(b"operator helper").hexdigest()
    assert record["hashes"] == {"kernel": "verified"}
    assert (directory / "receiver.py").read_text() == "operator helper"
    assert (directory / "receiver.py").stat().st_mode & 0o777 == 0o600


def test_push_sends_helper_and_remembers_reviewed_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(ram.Path, "home", lambda: tmp_path)
    settings = tmp_path / "settings.yml"
    ram.save(settings, {"host": "gc-09", "interface": "wired0"})
    monkeypatch.setattr(
        ram,
        "target",
        lambda *a: (["-o", "StrictHostKeyChecking=yes", "admin@target"], "/release"),
    )
    monkeypatch.setattr(ram.sb, "run", lambda *a: "a" * 40)
    calls = []

    def remote(argv, **kwargs):
        from types import SimpleNamespace

        calls.append((argv, kwargs))
        return SimpleNamespace(
            stdout=json.dumps({"host": "gc-09", "revision": "a" * 40})
        )

    monkeypatch.setattr(ram.subprocess, "run", remote)
    args = argparse.Namespace(
        host="gc-09", flake=Path("/controller"), settings=settings
    )
    ram.push(args)
    args.settings = None
    ram.push(args)
    assert len(calls) == 2
    for argv, kwargs in calls:
        assert argv[:3] == ["ssh", "-o", "BatchMode=yes"]
        assert "StrictHostKeyChecking=yes" in argv
        data = json.loads(kwargs["input"])
        assert data["data"]["settings"] == {"host": "gc-09", "interface": "wired0"}
        assert "def prepare_local" in data["source"]
        assert "--no-check-sigs" not in data["source"]
        assert "kexec --load" not in argv[-1]
