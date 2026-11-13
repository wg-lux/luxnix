"""Enroll a key from a dedicated reserved GPT partition; never format or mount it."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import uuid

RESERVED = '8da63339-0007-60c0-c436-083ac8230908'


def probe(*args):
    return json.loads(subprocess.check_output(args, stderr=subprocess.DEVNULL))


def key_partition(path, offset, size):
    """Require an independently prepared, unused Linux-reserved key partition."""
    if not re.fullmatch(r'/dev/disk/by-partuuid/[0-9a-f-]{36}', str(path)):
        raise ValueError('Select an exact /dev/disk/by-partuuid path')
    identifier = str(uuid.UUID(path.name))
    target = path.resolve(strict=True)
    if not stat.S_ISBLK(target.stat().st_mode):
        raise ValueError('Key target must be a block partition')
    records = probe('lsblk', '--json', '--bytes', '--paths', '--output',
                    'NAME,TYPE,PARTTYPE,PARTLABEL,PARTUUID,FSTYPE,SIZE,MOUNTPOINTS', str(target))['blockdevices']
    if len(records) != 1:
        raise ValueError('Ambiguous key partition')
    part = records[0]
    if (part['type'] != 'part' or part['parttype'].lower() != RESERVED
            or part['partlabel'] != 'luxnix-boot-key' or part['partuuid'].lower() != identifier
            or part.get('fstype') or part.get('children') or any(part.get('mountpoints') or [])
            or offset < 0 or size <= 0 or offset + size > int(part['size'])):
        raise ValueError('Expected unused Linux-reserved luxnix-boot-key partition with sufficient capacity')
    if list((Path('/sys/class/block') / target.name / 'holders').iterdir()):
        raise ValueError('Key partition has active holders')
    if probe('wipefs', '--json', '--no-act', str(target))['signatures']:
        raise ValueError('Key partition contains a filesystem or other signature')
    return target, identifier


def enroll(path, offset, size, devices, renderer, output):
    target, identifier = key_partition(path, offset, size)
    expected_device = target.stat().st_rdev
    if (output.exists() or output.is_symlink() or not output.is_absolute()
            or not output.parent.is_dir() or output.parent.resolve() != output.parent):
        raise ValueError('Select a new absolute configuration path without symlinks')
    # Admit every LUKS target before writing; publish only after all key tests.
    for name, device in devices:
        if not re.fullmatch(r'[A-Za-z0-9._-]+', name) or not stat.S_ISBLK(device.stat().st_mode):
            raise ValueError('Invalid LUKS target')
        subprocess.run(['cryptsetup', 'isLuks', str(device)], check=True)
    # Anonymous memory avoids plaintext key files. Refuse all disk swap to keep
    # this portable helper independent of the installed system's encryption state.
    if subprocess.check_output(['swapon', '--show=NAME', '--noheadings'], text=True).strip():
        raise ValueError('Disable swap before handling the enrollment key')
    print('Reserved key partition: ' + str(path), flush=True)
    if input('Type the complete PARTUUID to enroll a new key: ') != identifier:
        raise ValueError('Key enrollment not confirmed')
    fd = os.open(target, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
    key = os.memfd_create('luxnix-boot-key', flags=0)
    try:
        if os.fstat(fd).st_rdev != expected_device:
            raise ValueError('Key partition identity changed')
        if any(os.pread(fd, size, offset)):
            raise ValueError('Key region is not empty; never replace an existing key')
        material = os.urandom(size)
        os.write(key, material)
        written = os.pwrite(fd, material, offset)
        os.fsync(fd)
        if written != size or os.pread(fd, size, offset) != material:
            raise ValueError('Key partition readback failed; retain it for recovery')
        del material
        for name, device in devices:
            subprocess.run(['cryptsetup', 'luksAddKey', str(device), f'/proc/self/fd/{key}'],
                           check=True, pass_fds=(key,))
            subprocess.run(['cryptsetup', 'open', '--test-passphrase', '--key-file',
                            f'/proc/self/fd/{key}', str(device)], check=True, pass_fds=(key,))
        command = [renderer, '--output', str(output), '--key-partuuid', identifier,
                   '--offset-bytes', str(offset), '--keyfile-size', str(size)]
        for name, _ in devices:
            command += ['--luks-device', name]
        subprocess.run(command, check=True)
    finally:
        os.close(key)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-partition', required=True, type=Path)
    parser.add_argument('--offset-bytes', required=True, type=int)
    parser.add_argument('--block-size', required=True, type=int)
    parser.add_argument('--count', required=True, type=int)
    parser.add_argument('--renderer', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--luks-device', action='append', nargs=2, required=True, metavar=('NAME', 'PATH'))
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    size = args.block_size * args.count
    if os.geteuid() != 0 or args.block_size <= 0 or args.count <= 0 or not 1 <= size <= 1024 * 1024:
        parser.error('Run as root; key size must be between 1 byte and 1 MiB')
    try:
        enroll(args.key_partition, args.offset_bytes, size,
               [(name, Path(path)) for name, path in args.luks_device], args.renderer, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Boot key enrollment failed: {type(error).__name__}; retain partition and existing recovery credentials.\n')


if __name__ == '__main__':
    main()
