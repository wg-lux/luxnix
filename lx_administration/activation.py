"""Detached, acknowledged activation with compatibility-bound automatic rollback.

No test activation, database restore, reboot or key changes. Run from a retained
root-owned copy so both worker and watchdog survive the controller disconnecting.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

BASE = Path('/var/lib/luxnix-activation')
PUBLIC = Path('/run/luxnix-activation-status')
PROFILE = Path('/nix/var/nix/profiles/system')
CURRENT = Path('/run/current-system')
CLOSURE = re.compile(r'/nix/store/[a-z0-9]{32}-nixos-system-[^/]+')


def run(*args, timeout=120):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f'{Path(args[0]).name} failed ({result.returncode}); command output withheld to protect secrets; inspect the retained operation status and service journal')
    return result.stdout.strip()


def private(path):
    info = path.lstat()
    if path.resolve() != path or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('Activation state must be root-private without symlinks')
    return info


def save(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        PUBLIC.mkdir(mode=0o755, exist_ok=True)
        info = PUBLIC.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError('Unsafe public activation status directory')
        public = PUBLIC / (value['id'] + '.json')
        fd, name = tempfile.mkstemp(dir=PUBLIC)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'id': value['id'], 'status': value['status']}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, public)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(wait=False):
    if os.geteuid() != 0:
        raise ValueError('Activation requires root on the selected host')
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    private(BASE)
    fd = os.open(BASE / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        private(BASE / '.lock')
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        yield
    finally:
        os.close(fd)


def compatibility(previous, target, receipt=None):
    name = 'etc/luxnix/activation-compatibility.json'
    left, right = Path(previous) / name, Path(target) / name
    if left.is_file() and right.is_file():
        a, b = json.loads(left.read_text()), json.loads(right.read_text())
        if a == b and set(a) == {'version', 'activation', 'units', 'etc', 'filesystems'} and a['version'] == 1:
            return 'identical-stateful-footprint'
    if receipt is None:
        raise ValueError('Stateful footprints differ or are absent; provide a reviewed exact-closure compatibility receipt before enabling automatic rollback')
    private(receipt)
    record = json.loads(receipt.read_text())
    if (set(record) != {'version', 'previous', 'target', 'assessor', 'safe_without_data_restore', 'evidence', 'sha256'}
            or record['version'] != 1 or record['previous'] != previous or record['target'] != target
            or not isinstance(record['assessor'], str) or not record['assessor'].strip()
            or record['safe_without_data_restore'] is not True):
        raise ValueError('Compatibility receipt must bind a reviewed application/database pair to these exact closures')
    evidence = Path(record['evidence'])
    private(evidence)
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Compatibility evidence changed')
    return 'named-compatibility-assessment'


def load(identifier):
    if not re.fullmatch('[a-f0-9]{24}', identifier):
        raise ValueError('Invalid activation identifier')
    path = BASE / (identifier + '.json')
    private(path)
    value = json.loads(path.read_text())
    if value['id'] != identifier:
        raise ValueError('Wrong activation record')
    return path, value


def retained_helper():
    script = Path(__file__).resolve()
    if script.stat().st_uid != 0 or script.stat().st_mode & 0o022 or str(script).startswith('/tmp/'):
        raise ValueError('Use the retained root-owned activation helper')
    return script


def start(target, action, receipt=None):
    if not CLOSURE.fullmatch(target) or action not in {'boot', 'switch'}:
        raise ValueError('Select a built system closure and boot or switch')
    script = retained_helper()
    previous = str(CURRENT.resolve(strict=True))
    identifier = hashlib.sha256((previous + target + action).encode()).hexdigest()[:24]
    with locked():
        path = BASE / (identifier + '.json')
        for other in BASE.glob('*.json'):
            prior = json.loads(other.read_text())
            if prior.get('status') == 'accepted' and prior.get('target') == target and prior.get('action') == action and str(PROFILE.resolve()) == target and previous == target:
                return prior['id']
        if path.exists():
            _, existing = load(identifier)
            if existing['status'] in {'pending', 'running', 'awaiting-ack', 'accepted'}:
                return identifier
            if existing['status'] != 'preparing':
                raise ValueError('This activation was rolled back or interrupted; inspect its retained record before creating another release')
        for other in BASE.glob('*.json'):
            if json.loads(other.read_text()).get('status') in {'pending', 'running', 'awaiting-ack'}:
                raise ValueError('Another activation is pending acknowledgement')
        mode = compatibility(previous, target, receipt)
        record = {'id': identifier, 'previous': previous, 'target': target, 'action': action,
                  'status': 'preparing', 'compatibility': mode, 'created': time.time()}
        save(path, record)
        for label, closure in [('previous', previous), ('target', target)]:
            run('nix-store', '--add-root', str(BASE / (identifier + '-' + label)), '--indirect', '--realise', closure)
        # Arm recovery before launching the worker; its process is independent of SSH.
        timer = 'luxnix-rollback-' + identifier
        active = subprocess.run(['systemctl', 'is-active', '--quiet', timer + '.timer'], capture_output=True).returncode == 0
        if not active:
            run('systemd-run', '--unit=' + timer, '--on-active=35m',
                '--timer-property=AccuracySec=1s', '--property=Type=oneshot', '--property=TimeoutStartSec=35m',
                sys.executable, str(script), 'recover', '--id', identifier)
        record['status'] = 'pending'
        save(path, record)
        run('systemd-run', '--unit=luxnix-activate-' + identifier, '--property=Type=exec',
            '--property=KillMode=control-group', '--property=RuntimeMaxSec=32m',
            sys.executable, str(script), 'worker', '--id', identifier)
    return identifier


def worker(identifier):
    with locked(wait=True):
        path, value = load(identifier)
        if value['status'] != 'pending':
            return
        value['status'] = 'running'
        save(path, value)
    try:
        run('nix-env', '--profile', str(PROFILE), '--set', value['target'])
        run(value['target'] + '/bin/switch-to-configuration', value['action'], timeout=1800)
        if str(PROFILE.resolve()) != value['target'] or (value['action'] == 'switch' and str(CURRENT.resolve()) != value['target']):
            raise ValueError('Activation closure mismatch')
        with locked(wait=True):
            path, value = load(identifier)
            value['status'] = 'awaiting-ack'
            save(path, value)
    except BaseException:
        recover(identifier, stop_worker=False)
        raise


def acknowledge(identifier):
    with locked(wait=True):
        path, value = load(identifier)
        if value['status'] == 'accepted':
            return
        if value['status'] != 'awaiting-ack' or str(PROFILE.resolve()) != value['target'] or (value['action'] == 'switch' and str(CURRENT.resolve()) != value['target']):
            raise ValueError('The reviewed activation has not completed')
        value['status'] = 'accepted'
        save(path, value)
    run('systemctl', 'stop', 'luxnix-rollback-' + identifier + '.timer')


def recover(identifier, stop_worker=True):
    # The watchdog stops a stuck worker before restoring an approved compatible closure.
    if stop_worker:
        run('systemctl', 'stop', 'luxnix-activate-' + identifier + '.service')
    with locked(wait=True):
        path, value = load(identifier)
        if value['status'] in {'accepted', 'rolled-back'}:
            return
        value['status'] = 'recovering'
        save(path, value)
        run('nix-env', '--profile', str(PROFILE), '--set', value['previous'])
        run(value['previous'] + '/bin/switch-to-configuration', value['action'], timeout=1800)
        if str(PROFILE.resolve()) != value['previous'] or (value['action'] == 'switch' and str(CURRENT.resolve()) != value['previous']):
            raise ValueError('Rollback did not restore the approved closure; inspect its retained record')
        value['status'] = 'rolled-back'
        save(path, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'worker', 'ack', 'recover', 'status'])
    parser.add_argument('--system')
    parser.add_argument('--action', choices=['boot', 'switch'])
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--id')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'start':
            print(start(args.system or '', args.action or '', args.receipt))
        elif args.command == 'worker':
            worker(args.id)
        elif args.command == 'ack':
            acknowledge(args.id)
        elif args.command == 'recover':
            recover(args.id)
        else:
            if not re.fullmatch('[a-f0-9]{24}', args.id or ''):
                raise ValueError('Invalid activation identifier')
            print((PUBLIC / (args.id + '.json')).read_text())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Activation recovery: {error}\n')

if __name__ == '__main__':
    main()
