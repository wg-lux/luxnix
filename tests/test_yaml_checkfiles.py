from pathlib import Path

import pytest
import yaml

from lx_administration.yaml import CheckFile, load_check_files


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_check_definitions_load_yml_and_legacy_yaml_in_filename_order(tmp_path):
    (tmp_path / "z-last.yaml").write_text("- path: z-last\n", encoding="utf-8")
    (tmp_path / "a-first.yml").write_text("- path: a-first\n", encoding="utf-8")

    assert [check.path for check in load_check_files(tmp_path)] == [
        "a-first",
        "z-last",
    ]


def test_check_definitions_reject_duplicate_keys(tmp_path):
    (tmp_path / "duplicate.yml").write_text(
        "- path: first\n  path: shadowed\n", encoding="utf-8"
    )

    with pytest.raises(yaml.YAMLError, match="duplicate key 'path'"):
        load_check_files(tmp_path)


def test_symlink_requirement_fails_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "plain-file").touch()

    with pytest.raises(ValueError, match="not a symbolic link"):
        CheckFile(path="plain-file", symlink=True).check_and_fix()


def test_repository_check_definitions_are_portable_and_current(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    definitions = load_check_files(REPO_ROOT / "conf/check_files")

    assert definitions
    assert not (REPO_ROOT / "conf/check_files/conf.yaml").exists()
    assert all(check.owner is None and check.group is None for check in definitions)
    for check in definitions:
        check.check_and_fix()
