"""Background pre-copy and short-stop cutover with real rsync on disposable trees (class unit)."""

import json
import os
from pathlib import Path
import shutil
import stat

import pytest

from lx_administration.storage import cutover

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync required")


def snapshot(root: Path) -> dict:
    tree = {}
    for path in sorted(root.rglob("*")):
        info = os.lstat(path)
        relative = str(path.relative_to(root))
        content = path.read_bytes() if stat.S_ISREG(info.st_mode) else None
        tree[relative] = (stat.S_IMODE(info.st_mode), info.st_nlink if content else None, content)
    return tree


def identity(source, destination):
    return {
        "source": str(source),
        "destination": str(destination),
        "inode": destination.stat().st_ino,
    }


@pytest.fixture
def layout(tmp_path):
    source = tmp_path / "root/var/lib/app"
    (source / "db").mkdir(parents=True)
    (source / "db/base").write_bytes(b"page-1")
    (source / "obsolete").write_text("removed before cutover")
    (source / "nested").mkdir()
    (source / "nested/other-volume").write_text("belongs to a separate bind")
    os.link(source / "db/base", source / "db/hardlink")
    volume = tmp_path / "volume"
    volume.mkdir(mode=0o700)
    item = cutover.Item(source, volume / "application", ("nested",))
    return item, volume / ".receipt.json"


def test_precopy_then_cutover_reaches_exact_copy_and_keeps_source(layout):
    item, receipt = layout
    assert cutover.precopy(item) is False
    assert (item.payload / "db/base").read_bytes() == b"page-1"

    # Writers keep changing data during the background phase.
    (item.source / "db/base").write_bytes(b"page-2")
    (item.source / "new").write_text("created after pre-copy")
    (item.source / "obsolete").unlink()
    assert cutover.precopy(item) is False
    (item.source / "late").write_text("written just before the stop")

    before = snapshot(item.source)
    cutover.cutover(item, receipt, identity)

    assert snapshot(item.source) == before
    copied = snapshot(item.destination)
    expected = {path: value for path, value in before.items() if not path.startswith("nested")}
    assert copied == expected
    assert not (item.destination / "obsolete").exists()
    assert (
        os.stat(item.destination / "db/base").st_ino
        == os.stat(item.destination / "db/hardlink").st_ino
    )
    assert not item.stage.exists()
    assert json.loads(receipt.read_text())["destination"] == str(item.destination)
    assert cutover.precopy(item) is True


def test_interrupted_precopy_resumes_from_its_own_stage(layout):
    item, receipt = layout
    cutover.precopy(item)
    (item.payload / "db/base").write_bytes(b"torn write from an interrupted copy")
    cutover.cutover(item, receipt, identity)
    assert (item.destination / "db/base").read_bytes() == b"page-1"


def test_identical_destination_is_adopted_and_different_one_is_never_overwritten(layout, tmp_path):
    item, receipt = layout
    shutil.copytree(
        item.source, item.destination, symlinks=True, ignore=shutil.ignore_patterns("nested")
    )
    os.unlink(item.destination / "db/hardlink")
    os.link(item.destination / "db/base", item.destination / "db/hardlink")
    cutover.cutover(item, receipt, identity)
    assert receipt.exists()

    receipt.unlink()
    (item.destination / "db/base").write_bytes(b"divergent encrypted data")
    with pytest.raises(cutover.CutoverError, match="differs"):
        cutover.cutover(item, receipt, identity)
    assert (item.destination / "db/base").read_bytes() == b"divergent encrypted data"
    assert not receipt.exists()


def test_foreign_or_unsafe_stage_is_refused(layout, tmp_path):
    item, receipt = layout
    item.stage.mkdir(mode=0o700)
    (item.stage / "plan.json").write_text(json.dumps({"source": "/elsewhere", "destination": "x"}))
    with pytest.raises(cutover.CutoverError, match="another migration"):
        cutover.precopy(item)
    shutil.rmtree(item.stage)
    item.stage.mkdir(mode=0o755)
    with pytest.raises(cutover.CutoverError, match="Untrusted"):
        cutover.cutover(item, receipt, identity)
    assert not item.destination.exists()


def test_failed_verification_never_renames(layout, monkeypatch):
    item, receipt = layout
    real = cutover.rsync

    def diverging(entry, target, *, dry):
        result = real(entry, target, dry=dry)
        return b">f+++++++++ changed-during-copy\n" if dry else result

    monkeypatch.setattr(cutover, "rsync", diverging)
    with pytest.raises(cutover.CutoverError, match="verification failed"):
        cutover.cutover(item, receipt, identity)
    assert not item.destination.exists() and not receipt.exists()


def test_missing_or_symlinked_source_is_refused(layout, tmp_path):
    item, receipt = layout
    link = tmp_path / "link"
    link.symlink_to(item.source)
    for source in (tmp_path / "absent", link):
        with pytest.raises(cutover.CutoverError, match="real directory"):
            cutover.precopy(cutover.Item(source, item.destination))


def test_writers_stop_only_when_active_and_restart_after_failure(tmp_path, monkeypatch):
    calls = []
    states = {"postgresql.service": b"active\n", "lx-annotate.service": b"inactive\n"}

    def run(*args):
        calls.append(args)
        if args[:2] == ("systemctl", "show"):
            return states[args[-1]]
        return b""

    monkeypatch.setattr(cutover, "run", run)
    stopped = cutover.stop_writers(["postgresql", "lx-annotate"])
    assert stopped == ["postgresql"]
    assert ("systemctl", "stop", "postgresql.service") in calls
    cutover.restart_writers(stopped)
    assert calls[-1] == ("systemctl", "start", "postgresql.service")
