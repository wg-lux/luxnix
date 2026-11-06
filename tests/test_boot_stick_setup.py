"""Reserved-partition enrollment never writes keys into a mounted filesystem."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('boot_stick_setup',
    ROOT / 'modules/nixos/luxnix/boot-decryption-stick/setup.py')
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
IDENTIFIER = '12345678-1234-1234-1234-123456789abc'


@pytest.fixture
def partition(monkeypatch):
    part = dict(type='part', parttype=setup.RESERVED, partlabel='luxnix-boot-key',
                partuuid=IDENTIFIER, fstype=None, size=65536, mountpoints=[None])
    monkeypatch.setattr(Path, 'resolve', lambda self, **kw: Path('/dev/synthetic-key'))
    monkeypatch.setattr(Path, 'stat', lambda _: SimpleNamespace(st_mode=0o060000))
    monkeypatch.setattr(Path, 'iterdir', lambda _: iter([]))
    def probe(*args):
        return {'blockdevices': [part]} if args[0] == 'lsblk' else {'signatures': []}
    monkeypatch.setattr(setup, 'probe', probe)
    return part


@pytest.mark.parametrize('field,value', [
    ('fstype', 'ext4'), ('type', 'disk'), ('parttype', 'filesystem-data'),
    ('partlabel', 'ordinary-data'), ('partuuid', 'wrong'),
    ('mountpoints', ['/mounted']), ('children', [{'name': 'active'}]), ('size', 2)])
def test_invalid_or_mounted_layout_is_rejected_before_writes(partition, field, value):
    partition[field] = value
    with pytest.raises(ValueError, match='reserved'):
        setup.key_partition(Path('/dev/disk/by-partuuid') / IDENTIFIER, 0, 4096)


def test_reserved_layout_uses_exact_byte_offset_without_block_rounding(partition):
    device, identifier = setup.key_partition(Path('/dev/disk/by-partuuid') / IDENTIFIER, 7, 8192)
    assert str(device) == '/dev/synthetic-key' and identifier == IDENTIFIER


def test_filesystem_signature_and_holders_are_rejected(partition, monkeypatch):
    monkeypatch.setattr(Path, 'iterdir', lambda _: iter([Path('holder')]))
    with pytest.raises(ValueError, match='holders'):
        setup.key_partition(Path('/dev/disk/by-partuuid') / IDENTIFIER, 0, 4096)
    monkeypatch.setattr(Path, 'iterdir', lambda _: iter([]))
    original = setup.probe
    monkeypatch.setattr(setup, 'probe', lambda *a: {'signatures': [{'type': 'ext4'}]}
                        if a[0] == 'wipefs' else original(*a))
    with pytest.raises(ValueError, match='signature'):
        setup.key_partition(Path('/dev/disk/by-partuuid') / IDENTIFIER, 0, 4096)


def test_non_default_block_size_is_enrolled_and_rendered_consistently(tmp_path, monkeypatch):
    disk = tmp_path / 'synthetic-reserved-partition'
    disk.write_bytes(b'\0' * 65536)
    luks = tmp_path / 'synthetic-luks'
    luks.touch()
    monkeypatch.setattr(setup, 'key_partition', lambda *a: (disk, IDENTIFIER))
    monkeypatch.setattr(setup.stat, 'S_ISBLK', lambda _: True)
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **kw: '')
    monkeypatch.setattr('builtins.input', lambda _: IDENTIFIER)
    calls = []
    def command(args, **kw):
        calls.append(args)
        if args[0] == 'cryptsetup' and args[1] != 'isLuks':
            key = Path(next(value for value in args if value.startswith('/proc/self/fd/'))).read_bytes()
            assert len(key) == 8192
            assert key == disk.read_bytes()[7:8199]
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(setup.subprocess, 'run', command)
    setup.enroll(disk, 7, 2 * 4096, [('cryptroot', luks)], 'renderer', tmp_path / 'output.nix')
    assert calls[-1][calls[-1].index('--keyfile-size') + 1] == '8192'
    assert calls[-1][calls[-1].index('--offset-bytes') + 1] == '7'
    assert '--key-partuuid' in calls[-1]
    assert not (tmp_path / 'keyfile.bin').exists()
    with pytest.raises(ValueError, match='not empty'):
        setup.enroll(disk, 7, 8192, [('cryptroot', luks)], 'renderer', tmp_path / 'output.nix')


def test_disk_swap_refuses_key_handling(tmp_path, monkeypatch):
    disk = tmp_path / 'reserved'
    disk.touch()
    monkeypatch.setattr(setup, 'key_partition', lambda *a: (disk, IDENTIFIER))
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **kw: '/dev/swap')
    with pytest.raises(ValueError, match='swap'):
        setup.enroll(disk, 0, 4096, [], 'renderer', tmp_path / 'output.nix')
    assert disk.read_bytes() == b''
