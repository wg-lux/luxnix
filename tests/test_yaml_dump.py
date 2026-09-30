from datetime import datetime, timedelta
from pathlib import Path
import stat
import subprocess

import pytest
import yaml

from lx_administration.yaml import (
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    ansible_lint,
    dump_yaml,
    format_yaml,
)
from lx_administration.yaml import dump as dump_module


def test_dump_yaml_creates_parent_and_runs_hooks_in_order(tmp_path):
    output = tmp_path / "nested/config.yml"
    calls: list[tuple[str, Path]] = []

    dump_yaml(
        {"name": "luxnix", "values": ["one", "two"]},
        output,
        format_func=lambda path: calls.append(("format", path)),
        lint_func=lambda path: calls.append(("lint", path)),
    )

    assert yaml.safe_load(output.read_text(encoding="utf-8")) == {
        "name": "luxnix",
        "values": ["one", "two"],
    }
    assert [hook for hook, _ in calls] == ["format", "lint"]
    assert all(path.parent == output.parent for _, path in calls)
    assert all(path.suffix == output.suffix for _, path in calls)
    assert all(path != output for _, path in calls)
    assert all(not path.exists() for _, path in calls)


def test_format_yaml_preserves_quotes_and_normalizes_whitespace(tmp_path):
    output = tmp_path / "quoted.yml"
    output.write_text('identifier: "001"  \n', encoding="utf-8")

    format_yaml(output)

    assert output.read_text(encoding="utf-8") == 'identifier: "001"\n'


def test_dump_yaml_can_make_existing_output_private(tmp_path):
    output = tmp_path / "generated/merged.yml"
    output.parent.mkdir()
    output.write_text("old: value\n", encoding="utf-8")
    output.parent.chmod(0o755)
    output.chmod(0o644)

    dump_yaml(
        {"new": "value"},
        output,
        directory_mode=PRIVATE_DIRECTORY_MODE,
        file_mode=PRIVATE_FILE_MODE,
    )

    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert yaml.safe_load(output.read_text(encoding="utf-8")) == {"new": "value"}


def test_dump_yaml_preserves_last_good_output_when_hook_fails(tmp_path):
    output = tmp_path / "config.yml"
    output.write_text("last_good: true\n", encoding="utf-8")

    def fail_format(temporary_path):
        temporary_path.write_text("partial: true\n", encoding="utf-8")
        raise ValueError("format failed")

    with pytest.raises(ValueError, match="format failed"):
        dump_yaml({"new": "value"}, output, format_func=fail_format)

    assert output.read_text(encoding="utf-8") == "last_good: true\n"
    assert not list(tmp_path.glob(".config.*.yml"))


def test_dump_yaml_replaces_symlink_without_following_it(tmp_path):
    symlink_target = tmp_path / "outside.yml"
    symlink_target.write_text("untouched: true\n", encoding="utf-8")
    output = tmp_path / "config.yml"
    output.symlink_to(symlink_target)

    dump_yaml({"generated": True}, output, format_func=None)

    assert not output.is_symlink()
    assert yaml.safe_load(output.read_text(encoding="utf-8")) == {"generated": True}
    assert symlink_target.read_text(encoding="utf-8") == "untouched: true\n"


def test_dump_yaml_serializes_time_values_without_import_side_effects(tmp_path):
    output = tmp_path / "time-values.yml"

    dump_yaml(
        {
            "created": datetime(2026, 8, 4, 12, 30),
            "validity": timedelta(days=30),
        },
        output,
        format_func=None,
    )

    assert output.read_text(encoding="utf-8") == (
        "created: '2026-08-04T12:30:00'\nvalidity: P30D\n"
    )


def test_ansible_lint_propagates_nonzero_exit(monkeypatch, tmp_path):
    output = tmp_path / "invalid.yml"

    def fail(command, *, check):
        assert command == ["ansible-lint", str(output)]
        assert check is True
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(dump_module.subprocess, "run", fail)

    with pytest.raises(subprocess.CalledProcessError):
        ansible_lint(output)


def test_obsolete_duplicate_lint_helper_is_removed():
    assert not hasattr(dump_module, "ansible_lint_and_format")
