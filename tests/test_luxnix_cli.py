"""Fresh preparation is the default; preservation needs an explicit command."""

from pathlib import Path

import pytest

from lx_administration import cli
from lx_administration.storage import boot_migration as migration
from lx_administration.storage import boot_setup as setup
from lx_administration.storage import fresh_install as fresh

CONFIG = Path("/reviewed/autoconf/config.yml")


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["status", "--host", "gc-09"], ["status", "--host", "gc-09"]),
        (["migrate", "--device", "/dev/sdb1"], ["guide", "--device", "/dev/sdb1"]),
        (["retire-containers", "--apply"], ["retire-containers", "--apply"]),
        (["storage", "next"], ["next"]),
    ],
)
def test_each_command_is_one_boot_setup_action(monkeypatch, argv, expected):
    seen = []
    monkeypatch.setattr(setup, "main", seen.append)
    cli.main(argv)
    assert seen == [expected]


def test_unknown_commands_show_the_usage(monkeypatch, capsys):
    monkeypatch.setattr(setup, "main", lambda argv: pytest.fail("must not run"))
    with pytest.raises(SystemExit) as error:
        cli.main(["encrypt"])
    assert "Unknown command: encrypt" in str(error.value.code)
    assert "migrate" in str(error.value.code)
    cli.main(["--help"])
    assert "status" in capsys.readouterr().out


def test_a_stop_names_what_is_kept_and_the_next_command():
    text = migration.explain_stop(migration.MigrationError("Disk busy", fix="unmount"))
    assert "STOPPED: Disk busy" in text
    assert "Kept: nothing was deleted" in text
    assert text.rstrip().endswith("Next: unmount")
    plain = migration.explain_stop(ValueError("Unexpected"))
    assert f"Next: {migration.STATUS_COMMAND}" in plain


def test_the_command_prints_the_explained_stop(monkeypatch, capsys):
    def unknown(config):
        raise migration.MigrationError("Not recognised", fix="rerun with --host gc-09")

    monkeypatch.setattr(setup, "current_host", unknown)
    with pytest.raises(SystemExit) as error:
        setup.main(["next"])
    assert error.value.code == 1
    err = capsys.readouterr().err
    assert "STOPPED: Not recognised" in err
    assert "Next: rerun with --host gc-09" in err


@pytest.mark.parametrize("argv", [[], ["install"]])
def test_default_is_non_mutating_fresh_guidance(monkeypatch, capsys, argv):
    monkeypatch.setattr(setup, "main", lambda *a: pytest.fail("no migration"))
    monkeypatch.setattr(fresh, "prepare", lambda *a: pytest.fail("no profile"))
    monkeypatch.setattr(fresh, "install", lambda *a, **k: pytest.fail("no erase"))
    cli.main(argv)
    output = capsys.readouterr().out
    assert "Fresh encrypted installation (default)" in output
    assert "--profile" in output and "No disks changed" in output


def test_default_profile_prepares_without_entering_migration(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(setup, "main", lambda *a: pytest.fail("no migration"))
    monkeypatch.setattr(fresh, "prepare", lambda p: seen.append(p) or "/bundle")
    cli.main(["--profile", "/host.yml"])
    assert seen == [Path("/host.yml")]
    assert capsys.readouterr().out.strip() == "/bundle/bin/luxnix-install"


@pytest.mark.parametrize("argv", [["--apply"], ["--profile", "/host.yml", "--apply"]])
def test_default_cannot_turn_apply_into_erasure(monkeypatch, argv):
    monkeypatch.setattr(fresh, "prepare", lambda *a: pytest.fail("no preparation"))
    monkeypatch.setattr(fresh, "install", lambda *a, **k: pytest.fail("no erasure"))
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2


def test_migration_status_does_not_refresh_or_create_a_plan(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(setup, "current_host", lambda c: "gc-09")
    monkeypatch.setattr(setup, "target_spec", lambda *a: ({}, tmp_path))
    monkeypatch.setattr(setup, "configured_target", lambda *a: pytest.fail("read-only"))
    monkeypatch.setattr(migration, "status", lambda s: {"install": "pending"})
    cli.main(["status"])
    assert '"install": "pending"' in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
