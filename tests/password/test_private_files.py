import stat

import pytest

from lx_administration.password.files import write_private_text


def test_write_private_text_restricts_new_and_existing_files(tmp_path):
    private_file = tmp_path / "secret"
    private_file.write_text("old", encoding="utf-8")
    private_file.chmod(0o644)

    write_private_text(private_file, "new")

    assert private_file.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(private_file.stat().st_mode) == 0o600


def test_write_private_text_refuses_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("unchanged", encoding="utf-8")
    link = tmp_path / "secret"
    link.symlink_to(target)

    with pytest.raises(OSError):
        write_private_text(link, "replacement")

    assert target.read_text(encoding="utf-8") == "unchanged"


def test_write_private_text_preserves_last_good_file_when_replace_fails(
    tmp_path, monkeypatch
):
    private_file = tmp_path / "secret"
    private_file.write_text("last-good", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr("lx_administration.permissions.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_private_text(private_file, "replacement")

    assert private_file.read_text(encoding="utf-8") == "last-good"
    assert not list(tmp_path.glob(".secret.*"))
