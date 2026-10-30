"""Root-only login/remote lifecycle for an already enrolled local OpenBao store.

No password is accepted in argv or the environment. PAM invokes this only from
open_session after authentication; logout deliberately does not lock storage.
"""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import hmac
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

import openbao_local as bao
from secret_storage import encrypted_storage

STATE = Path('/var/lib/openbao-bootstrap/login')
RUNTIME = Path('/run/luxnix-storage-access')
GATE = RUNTIME / 'unlocked'


def run(*args):
    try:
        return subprocess.run(args, check=True, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Only fixed commands and declared unit/device names, never their output.
        print("Storage command failed: " + " ".join(args), file=sys.stderr)
        raise


@contextmanager
def serialized():
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(RUNTIME / 'operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def account_record(config, user):
    if user not in config['users'] or not user or '/' in user or user in ('.', '..'):
        raise ValueError('Account is not authorized for storage unlock')
    return STATE / (user + '.json')


def unlock_key(config, user, password, enroll=False):
    path = account_record(config, user)
    canonical = json.loads(bao.read_private(bao.SEAL_WRAP))
    bao.validate_seal_record(canonical)
    if path.exists():
        key = bao.unwrap_seal_key(json.loads(bao.read_private(path)), password)
    elif enroll and config['autoEnroll']:
        # Never invent a new seal or trust an unauthenticated staged key.
        bao.verify_staged_seal()
        key = bao.read_private(bao.SEAL_RUNTIME)
        STATE.mkdir(mode=0o700, exist_ok=True)
        bao.write_private(path, json.dumps(bao.wrap_seal_key(key, password)).encode())
    else:
        raise ValueError('Login credential missing: bootstrap with the recovery passphrase first')
    if not hmac.compare_digest(bao.key_check(key), canonical['key_check']):
        raise ValueError('Login credential belongs to another OpenBao seal')
    bao.stage_verified_seal(canonical, key)


def unlock(config, user, password, enroll=False):
    unlock_key(config, user, password, enroll)
    # All automatic mount/unseal attempts are gated by this root-only marker.
    bao.write_private(GATE, b'authorized\n')
    try:
        run('systemctl', 'start', 'openbao-local.service')
        run('systemctl', 'start', *config['mounts'])
        run('systemctl', 'start', *config['startup'])
        if config['startupTriggers']:
            run('systemctl', 'start', *config['startupTriggers'])
    except (OSError, subprocess.SubprocessError):
        # Preserve the original failure; cleanup must never hide partial state.
        try:
            lock(config)
        except (OSError, subprocess.SubprocessError, ValueError):
            raise ValueError('Unlock failed and cleanup is incomplete; inspect storage status') from None
        raise ValueError('Storage startup failed; storage was locked again') from None


def lock(config):
    # Block new jobs before stopping timers, services and mounts. Never force or
    # lazily unmount: a remaining consumer must make this operation fail.
    GATE.unlink(missing_ok=True)
    if config['triggers']:
        run('systemctl', 'stop', *config['triggers'])
    run('systemctl', 'stop', *config['consumers'])
    for mount in config['mountsReverse']:
        run('systemctl', 'stop', mount)
    for volume in config['volumes']:
        if Path(volume['device']).exists():
            run('cryptsetup', 'close', volume['device'])
    run('systemctl', 'stop', 'openbao-local.service', 'openbao-local-seal-key.service')
    bao.SEAL_RUNTIME.unlink(missing_ok=True)
    bao.SEAL_RUNTIME.with_suffix('.receipt').unlink(missing_ok=True)


def status(config):
    opened = [v['device'] for v in config['volumes'] if Path(v['device']).exists()]
    print(json.dumps({'authorized': GATE.exists(), 'openMappings': opened,
                      'sealStaged': bao.SEAL_RUNTIME.exists()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('command', choices=['unlock', 'lock', 'status', 'bootstrap', 'forget'])
    parser.add_argument('--user')
    parser.add_argument('--pam', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root through sudo')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    config = json.loads(Path(args.config).read_text())
    try:
        with serialized():
            if args.command == 'status':
                status(config)
            elif args.command == 'lock':
                lock(config)
            elif args.command == 'forget':
                account_record(config, args.user).unlink(missing_ok=True)
            else:
                encrypted_storage(Path('/run'), allow_runtime=True)
                if args.command == 'bootstrap':
                    if args.pam:
                        raise ValueError('Bootstrap requires an operator terminal')
                    password = getpass.getpass('Existing OpenBao recovery boot passphrase: ').encode()
                    record = json.loads(bao.read_private(bao.SEAL_WRAP))
                    bao.stage_verified_seal(record, bao.unwrap_seal_key(record, password))
                    bao.write_private(GATE, b'authorized\n')
                    run('systemctl', 'start', 'openbao-local.service')
                else:
                    account_record(config, args.user)
                    if args.pam:
                        password = sys.stdin.buffer.read(4097)
                        if not password or len(password) > 4096:
                            raise ValueError('Missing or oversized login token')
                    else:
                        password = getpass.getpass('Account login password: ').encode()
                    unlock(config, args.user, password, enroll=args.pam)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        # Never include command output, secret values or decrypted records.
        print('Storage access failed; inspect service state and enrollment.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
