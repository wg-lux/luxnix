"""Standalone authenticated archive transport for controller or host-local snapshots."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import socket
import subprocess
import time

def validate_snapshot(host, identifier, item):
    if host not in {'gc-09', 'gc-10'} or not re.fullmatch(r'[a-z0-9][a-z0-9-]{5,60}', identifier):
        raise ValueError('Invalid backup target')
    name = item['name']
    source = item['source']
    allowed = {'root': '/', 'home': '/home', 'nix': '/nix', 'persist': '/persist',
               'var-log': '/var/log'}
    if host == 'gc-10':
        allowed['data-raid01'] = '/data/raid01'
    if allowed.get(name) != source:
        raise ValueError('Unexpected snapshot source')
    parent = (f'/data/raid01/.luxnix-migration-snapshots/{identifier}'
              if source == '/data/raid01' else f'/var/lib/luxnix-migration-snapshots/{identifier}')
    if item['snapshot'] != f'{parent}/{name}':
        raise ValueError('Unexpected snapshot path')


def verify_archive(path, identity, digest, *, pass_fds=()):
    process = subprocess.Popen(['age', '-d', '-i', str(identity), str(path)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=pass_fds)
    actual = hashlib.sha256()
    try:
        while chunk := process.stdout.read(4 * 1024 * 1024):
            actual.update(chunk)
        if process.wait() != 0 or actual.hexdigest() != digest:
            raise ValueError('Encrypted archive authentication or stream checksum failed')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def transfer(remote, command, target, recipient, identity):
    partial = target.with_suffix(target.suffix + '.partial')
    if target.exists() or partial.exists() or target.with_suffix(target.suffix + ".unverified").exists():
        raise ValueError('Existing archive requires review; refusing replacement')
    source = (remote.open_stream(command, privileged=True) if remote else
              subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL))
    encryption = None
    digest = hashlib.sha256()
    count = 0
    last_report = time.monotonic()
    try:
        source.stdin.close()
        with partial.open('xb') as output:
            recipients = recipient if isinstance(recipient, list) else [recipient]
            encryption = subprocess.Popen(['age', *[arg for value in recipients for arg in ['-r', value]]], stdin=subprocess.PIPE,
                                           stdout=output, stderr=subprocess.DEVNULL)
            while chunk := source.stdout.read(4 * 1024 * 1024):
                digest.update(chunk)
                encryption.stdin.write(chunk)
                count += len(chunk)
                if time.monotonic() - last_report > 60:
                    print(json.dumps({'component': target.name, 'compressed_bytes': count}), flush=True)
                    last_report = time.monotonic()
            encryption.stdin.close()
            source_code, encryption_code = source.wait(), encryption.wait()
            if source_code or encryption_code:
                raise ValueError(f'Backup transfer failed (source={source_code}, encryption={encryption_code}); partial retained')
            output.flush()
            os.fsync(output.fileno())
        if identity is not None:
            print(f'Authenticating complete archive {target.name}', flush=True)
            for key in identity if isinstance(identity, list) else [identity]:
                verify_archive(partial, key, digest.hexdigest())
        else:
            # No private identity is persisted on the unmigrated host. A separate
            # authenticated verification must publish this completed ciphertext.
            target = target.with_suffix(target.suffix + '.unverified')
        # Publish without overwriting an existing backup.
        os.link(partial, target)
        partial.unlink()
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return {'compressed_bytes': count, 'sha256_compressed_stream': digest.hexdigest(),
                'authenticated': identity is not None, 'artifact': target.name,
                'application_restore_tested': False}
    finally:
        source.stdout.close()
        for process in [source, encryption]:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


def save_receipt(path, value):
    temporary = path.with_suffix('.pending')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def local_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-id', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--destination-uuid', required=True)
    parser.add_argument('--recipient', required=True)
    parser.add_argument('--custodian-recipient')
    parser.add_argument('--legacy-ssh-identity', action='store_true',
                        help='Verify an existing SSH-encrypted archive only; never create a new one')
    parser.add_argument('--verify', choices=['root', 'home', 'nix', 'persist', 'var-log'])
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if socket.gethostname() != 'gc-09' or not re.fullmatch(r'[a-z0-9][a-z0-9-]{5,60}', args.snapshot_id):
        parser.error('Host-local backup is limited to the reviewed gc-09 snapshots')
    if args.destination.resolve() != args.destination or not args.destination.is_mount():
        parser.error('Backup destination is not an exact existing mount')
    mounted = json.loads(subprocess.check_output(['findmnt', '--json', '--mountpoint',
                         str(args.destination), '--output', 'UUID'], text=True))['filesystems'][0]
    if mounted['uuid'] != args.destination_uuid:
        parser.error('Wrong backup filesystem identity')
    plan = json.loads(Path(f'/var/lib/luxnix-migration-snapshots/{args.snapshot_id}/plan.json').read_text())
    if not plan['complete'] or plan['host'] != 'gc-09' or plan['identifier'] != args.snapshot_id:
        parser.error('Snapshot plan incomplete or mismatched')
    if mounted['uuid'] in {fs['uuid'] for fs in plan['mounts'].values()}:
        parser.error('Backup must use a filesystem independent of all source snapshots')
    if {i['name'] for i in plan['snapshots']} != {'root', 'home', 'nix', 'persist', 'var-log'}:
        parser.error('Incomplete snapshot coverage')
    for item in plan['snapshots']:
        validate_snapshot('gc-09', args.snapshot_id, item)
    root = args.destination / 'luxnix-storage-migration' / f'gc-09-{args.snapshot_id}'
    if root.resolve() != root:
        parser.error('Symlink in backup destination')
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock = (root / '.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    receipt_path = root / 'receipt.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {
        'host': 'gc-09', 'snapshot_id': args.snapshot_id, 'components': {},
        'recipients': [args.recipient, args.custodian_recipient],
        'complete': False, 'application_restore_tested': False}
    if args.verify:
        import sys
        item = receipt['components'][args.verify]
        target = root / f'{args.verify}.btrfs.gz.age'
        unverified = target.with_suffix(target.suffix + '.unverified')
        # Recovery identity exists only in an anonymous RAM descriptor, never in
        # an unencrypted host file, process argument, journal or Nix derivation.
        swaps = subprocess.check_output(['swapon', '--show=NAME,TYPE', '--noheadings', '--raw'], text=True)
        for line in swaps.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[1] != 'partition' or not re.fullmatch(r'/dev/zram[0-9]+', fields[0]):
                parser.error('Recovery identity requires disabled disk swap')
            if Path('/sys/block/' + Path(fields[0]).name + '/backing_dev').read_text().strip() != 'none':
                parser.error('Recovery identity forbids zram writeback')
        fd = os.memfd_create('backup-recovery-identity', flags=0)
        try:
            key = sys.stdin.buffer.read(8193)
            if len(key) > 8192 or not (b'AGE-SECRET-KEY-1' in key or
                    (args.legacy_ssh_identity and key.startswith(b'-----BEGIN OPENSSH PRIVATE KEY-----'))):
                parser.error('Expected dedicated age recovery identity on stdin; existing SSH archives require explicit legacy verification')
            os.write(fd, key)
            del key
            os.lseek(fd, 0, os.SEEK_SET)
            if receipt.get('recipients'):
                identity_recipient = subprocess.check_output(
                    ['age-keygen', '-y', f'/proc/self/fd/{fd}'],
                    stderr=subprocess.DEVNULL, text=True, pass_fds=(fd,)).strip()
                if identity_recipient not in receipt['recipients']:
                    parser.error('Recovery identity is not one of the recorded archive recipients')
                os.lseek(fd, 0, os.SEEK_SET)
            elif not args.legacy_ssh_identity:
                parser.error('Legacy archive verification requires the explicit legacy option')
            verify_archive(target if item['authenticated'] else unverified,
                           Path(f'/proc/self/fd/{fd}'), item['sha256_compressed_stream'], pass_fds=(fd,))
            verified = set(item.get('verified_recipients', []))
            if receipt.get('recipients'):
                verified.add(identity_recipient)
            authenticated = not receipt.get('recipients') or verified == set(receipt['recipients'])
            if authenticated and not item['authenticated']:
                os.link(unverified, target)
                unverified.unlink()
            item['authenticated'] = authenticated
            item['verified_recipients'] = sorted(verified)
            item['artifact'] = target.name if authenticated else unverified.name
        finally:
            os.close(fd)
        receipt['complete'] = len(receipt['components']) == 5 and all(i['authenticated'] for i in receipt['components'].values())
        save_receipt(receipt_path, receipt)
        print('Archive recovery check: ' + args.verify +
              ('; all recorded recipients verified' if item['authenticated'] else
               '; verify the other independent recipient before acceptance'), flush=True)
        return
    if (args.legacy_ssh_identity or not re.fullmatch(r'age1[0-9a-z]{58}', args.recipient)
            or not args.custodian_recipient or not re.fullmatch(r'age1[0-9a-z]{58}', args.custodian_recipient)
            or args.recipient == args.custodian_recipient):
        parser.error('New archives require distinct controller and independent custodian age recipients')
    if receipt.get('recipients') != [args.recipient, args.custodian_recipient]:
        parser.error('Existing archive recipient selection differs; retain it and use a new backup identifier')
    for item in plan['snapshots']:
        name = item['name']
        if name in receipt['components']:
            continue
        prop = subprocess.check_output(['btrfs', 'property', 'get', '-ts', item['snapshot'], 'ro'])
        if prop.strip() != b'ro=true':
            parser.error('Source snapshot is not read-only')
        pipeline = shlex.join(['btrfs', 'send', item['snapshot']]) + ' | gzip -1'
        print('Encrypting host-local snapshot ' + name, flush=True)
        receipt['components'][name] = transfer(None, ['bash', '-o', 'pipefail', '-c', pipeline],
                                               root / f'{name}.btrfs.gz.age', [args.recipient, args.custodian_recipient], None)
        save_receipt(receipt_path, receipt)
    print('Ciphertext creation complete; authenticate each component before restore', flush=True)


if __name__ == '__main__':
    local_main()
