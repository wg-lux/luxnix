"""Hardware serials and mounted identity are verified before storage reuse."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lx_administration.storage import mounting


def test_similar_serial_and_regular_file_are_not_selected(tmp_path, monkeypatch):
    target = tmp_path / 'device'
    target.touch()
    aliases = tmp_path / 'by-id'
    aliases.mkdir()
    (aliases / 'usb-SERIAL12345').symlink_to(target)
    assert mounting.find_device_by_serial('SERIAL123', aliases) is None
    monkeypatch.setattr(mounting.stat, 'S_ISBLK', lambda _: True)
    monkeypatch.setattr(mounting.subprocess, 'check_output', lambda *a, **kw:
                        json.dumps({'blockdevices': [{'serial': 'SERIAL12345'}]}))
    assert mounting.find_device_by_serial('SERIAL123', aliases) is None
    assert mounting.find_device_by_serial('SERIAL12345', aliases) == target


def test_ambiguous_exact_serial_is_rejected_but_same_device_aliases_are_allowed(tmp_path, monkeypatch):
    aliases = tmp_path / 'by-id'
    aliases.mkdir()
    for name in ('a', 'b'):
        target = tmp_path / name
        target.touch()
        (aliases / name).symlink_to(target)
    monkeypatch.setattr(mounting.stat, 'S_ISBLK', lambda _: True)
    monkeypatch.setattr(mounting.subprocess, 'check_output', lambda *a, **kw:
                        json.dumps({'blockdevices': [{'serial': 'EXACT'}]}))
    with pytest.raises(ValueError, match='Multiple'):
        mounting.find_device_by_serial('EXACT', aliases)
    (aliases / 'b').unlink()
    (aliases / 'b').symlink_to(tmp_path / 'a')
    assert mounting.find_device_by_serial('EXACT', aliases) == tmp_path / 'a'


def test_already_mounted_wrong_device_never_counts_as_ready(monkeypatch):
    monkeypatch.setattr(Path, 'is_mount', lambda _: True)
    monkeypatch.setattr(mounting, 'find_device_by_serial', lambda _: Path('/dev/intended'))
    monkeypatch.setattr(mounting.subprocess, 'check_output', lambda *a, **kw:
                        '{"filesystems":[{"source":"/dev/wrong"}]}')
    monkeypatch.setattr(Path, 'stat', lambda p: SimpleNamespace(st_rdev=1 if p.name == 'intended' else 2))
    storage = SimpleNamespace(storage_persisting_external_drive=True,
        storage_persisting_mount_point=Path('/mnt/data'), storage_persisting_hdd_id='EXACT')
    with pytest.raises(ValueError, match='not the configured'):
        mounting.external_drive_requires_mount(storage)


def test_existing_correct_mount_must_pass_shared_encryption_boundary(monkeypatch):
    monkeypatch.setattr(Path, 'is_mount', lambda _: True)
    monkeypatch.setattr(mounting, 'find_device_by_serial', lambda _: Path('/dev/intended'))
    monkeypatch.setattr(mounting.subprocess, 'check_output', lambda *a, **kw:
                        '{"filesystems":[{"source":"/dev/intended"}]}')
    monkeypatch.setattr(Path, 'stat', lambda _: SimpleNamespace(st_rdev=1))
    def unencrypted(_):
        raise ValueError('shared encryption guard refused')
    monkeypatch.setattr(mounting, 'encrypted_storage', unencrypted)
    storage = SimpleNamespace(storage_persisting_external_drive=True,
        storage_persisting_mount_point=Path('/mnt/data'), storage_persisting_hdd_id='EXACT')
    with pytest.raises(ValueError, match='shared encryption'):
        mounting.external_drive_requires_mount(storage)


def test_physical_serial_selects_unlocked_filesystem_and_accepts_correct_mount(tmp_path, monkeypatch):
    disk, mapping = tmp_path / 'disk', tmp_path / 'unlocked'
    disk.touch()
    mapping.touch()
    aliases = tmp_path / 'by-id'
    aliases.mkdir()
    (aliases / 'usb-exact').symlink_to(disk)
    record = {'blockdevices': [{'name': str(disk), 'type': 'disk', 'serial': 'EXACT',
        'children': [{'name': '/dev/synthetic-partition', 'type': 'part', 'fstype': 'crypto_LUKS',
            'children': [{'name': str(mapping), 'type': 'crypt', 'fstype': 'ext4'}]}]}]}
    monkeypatch.setattr(mounting.stat, 'S_ISBLK', lambda _: True)
    def probe(args, **kw):
        return json.dumps(record if args[0] == 'lsblk' else {'filesystems': [{'source': str(mapping)}]})
    monkeypatch.setattr(mounting.subprocess, 'check_output', probe)
    selected = mounting.find_device_by_serial('EXACT', aliases)
    assert selected == mapping
    checked = []
    monkeypatch.setattr(mounting, 'encrypted_storage', lambda p: checked.append(p))
    mounting.verify_mount(selected, tmp_path / 'mounted')
    assert checked == [tmp_path / 'mounted']


def test_multiple_unlocked_filesystems_for_one_serial_are_ambiguous(tmp_path, monkeypatch):
    disk = tmp_path / 'disk'
    disk.touch()
    aliases = tmp_path / 'by-id'
    aliases.mkdir()
    (aliases / 'usb-exact').symlink_to(disk)
    children = []
    for name in ('one', 'two'):
        mapping = tmp_path / name
        mapping.touch()
        children.append({'name': str(mapping), 'type': 'crypt', 'fstype': 'btrfs'})
    monkeypatch.setattr(mounting.stat, 'S_ISBLK', lambda _: True)
    monkeypatch.setattr(mounting.subprocess, 'check_output', lambda *a, **kw: json.dumps({
        'blockdevices': [{'name': str(disk), 'type': 'disk', 'serial': 'EXACT', 'children': children}]}))
    with pytest.raises(ValueError, match='Multiple encrypted'):
        mounting.find_device_by_serial('EXACT', aliases)
