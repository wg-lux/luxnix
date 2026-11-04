"""Escrow recovery credentials before explicit, inventory-scoped LUKS provisioning.

Only ciphertext is exported to the recovery host. Existing containers are never
formatted, and this controller is never invoked by application startup.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import selectors
import secrets
import shlex
import socket
import stat
import subprocess
import time
import uuid

from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.models.vault import Vault
from lx_administration.models.vault.secret import (
    MASTER_VAULT_ID, _encrypt_bytes, _publish_ciphertext, decrypt_secret,
)
from lx_administration.permissions import ensure_private_directory
from lx_administration.secret_storage import encrypted_storage
from lx_administration.storage.recovery_export import export_script
from lx_administration.storage.password_custody import CustodyError


class ProvisionError(RuntimeError):
    """An operator-safe diagnostic without credential values."""


# No secret values are interpolated into this code or its arguments.
EXPORT = export_script('volume')

READY = b'LUXNIX-PRIVILEGE-READY\n'
# sudo sees only its password pipe. The elevated process independently opens an
# anonymous payload pipe owned by its supervisor; no sudo timestamp is reused.
PRIVILEGED_STDIN = r'''
import json, os, sys
fd = os.open(sys.argv[1], os.O_RDONLY)
os.dup2(fd, 0)
os.close(fd)
os.write(1, b'LUXNIX-PRIVILEGE-READY\n')
argv = json.loads(sys.argv[2])
os.execvp(argv[0], argv)
'''
SUDO_SUPERVISOR = r'''
import json, os, subprocess, sys, threading
password = sys.stdin.buffer.readline(4097)
if not password.endswith(b'\n') or len(password) > 4096:
    sys.exit(2)
read_fd, write_fd = os.pipe()
bootstrap = __BOOTSTRAP__
command = ['python3', '-c', bootstrap, f'/proc/{os.getpid()}/fd/{read_fd}', sys.argv[2]]
prefix = ['sudo', '-k', '-S', '-p', ''] if sys.argv[1] == 'password' else ['sudo', '-n']
child = subprocess.Popen(prefix + command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
try:
    child.stdin.write(password if sys.argv[1] == 'password' else b'')
    child.stdin.close()
    password = None
    ready = b'LUXNIX-PRIVILEGE-READY\n'
    if child.stdout.read(len(ready)) != ready:
        sys.exit(child.wait() or 1)
    sys.stdout.buffer.write(ready)
    sys.stdout.buffer.flush()
    def send():
        try:
            with os.fdopen(write_fd, 'wb', buffering=0) as output:
                while data := sys.stdin.buffer.read(65536):
                    output.write(data)
        except BrokenPipeError:
            pass
    threading.Thread(target=send, daemon=True).start()
    while data := child.stdout.read(65536):
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    sys.exit(child.wait())
finally:
    os.close(read_fd)
    if child.poll() is None:
        child.kill()
        child.wait()
'''.replace('__BOOTSTRAP__', repr(PRIVILEGED_STDIN))


class Remote:
    operation = 'Remote operation'

    def __init__(self, address, sudo_password_file=None):
        self.ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30',
                    '-o', 'ServerAliveCountMax=2', 'admin@' + address]
        self.password_file = sudo_password_file
        self.password_required = None

    def _run(self, args, data=b'', timeout=600):
        return subprocess.run(self.ssh + [shlex.join(args)], input=data,
                              capture_output=True, timeout=timeout)

    def _popen(self, args):
        return subprocess.Popen(self.ssh + [shlex.join(args)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def open_stream(self, args, privileged=True, timeout=30):
        """Return a payload-only stream after successful privilege authentication."""
        if not privileged:
            return self._popen(args)
        if self.password_required is None:
            self.password_required = self._run(['sudo', '-n', 'true'], timeout=30).returncode != 0
        password = b''
        if self.password_required:
            if self.password_file is None:
                raise ProvisionError('A private sudo-password file is required for this target')
            encrypted_storage(self.password_file, allow_runtime=True)
            info = self.password_file.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > 4096):
                raise ProvisionError('Sudo-password file must be private, owned by the operator and not a symlink')
            password = self.password_file.read_bytes().rstrip(b'\r\n')
            if not password or b'\n' in password or b'\r' in password or len(password) > 4095:
                raise ProvisionError('Sudo-password file must contain exactly one nonempty password line')
        process = self._popen(['python3', '-c', SUDO_SUPERVISOR,
                               'password' if self.password_required else 'noninteractive', json.dumps(args)])
        try:
            process.stdin.write(password + b'\n')
            process.stdin.flush()
            deadline, received = time.monotonic() + timeout, b''
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while len(received) < len(READY):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ProvisionError('Sudo authentication timed out; no operation payload was sent')
                    chunk = os.read(process.stdout.fileno(), len(READY) - len(received))
                    if not chunk:
                        raise ProvisionError('Sudo authentication failed; no operation payload was sent. Correct the password before retrying')
                    received += chunk
            if received != READY:
                raise ProvisionError('Unexpected privilege response; no operation payload was sent')
            return process
        except BaseException:
            process.kill()
            process.communicate()
            raise

    def call(self, args, data=b'', privileged=False, relay_error=False):
        if privileged:
            process = self.open_stream(args)
            try:
                stdout, stderr = process.communicate(data, timeout=600)
            except BaseException:
                process.kill()
                process.communicate()
                raise
            result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        else:
            result = self._run(args, data=data)
        if result.returncode:
            # Remote diagnostics may contain credential-bearing input. Relay only the
            # single ERROR line of a LuxNix tool that builds it without secret values.
            lines = result.stderr.decode(errors='replace').strip().splitlines()
            if relay_error and lines and re.fullmatch(r'ERROR: [A-Za-z0-9 ,.:;/_()-]{1,200}', lines[-1]):
                raise ProvisionError(f'{self.operation} failed: {lines[-1][7:]}')
            raise ProvisionError(f'{self.operation} failed (exit {result.returncode})')
        return result.stdout

    def machine_id(self):
        value = self.call(['cat', '/etc/machine-id']).decode().strip()
        if not re.fullmatch('[0-9a-f]{32}', value):
            raise ProvisionError('Invalid machine identity')
        return value


class Local(Remote):
    """Reuse target privilege and stdin handling without an SSH connection."""

    operation = 'Local operation'

    def __init__(self, host, sudo_password_file=None):
        if socket.gethostname() != host:
            raise ProvisionError(
                '--local-target requires the local hostname to match --host'
            )
        self.password_file = sudo_password_file
        self.password_required = None

    def _run(self, args, data=b'', timeout=600):
        return subprocess.run(args, input=data, capture_output=True,
                              timeout=timeout)

    def _popen(self, args):
        return subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)


def require_independent_custody(vault):
    if not (vault / 'storage-recovery/custody.json').is_file():
        raise ProvisionError('Prepare independent age custody with storage-recovery-custody prepare --vault-dir and --export-directory before provisioning; existing vault copies remain usable')
    return True


def escrow_record(vault, vault_key, record, export, *, independent_required=False):
    """Publish once, authenticate selected custody, never replace recovery material."""
    root = ensure_private_directory(vault / 'storage-recovery' / record['machine_id'])
    target = root / (record['volume'] + '.vault')
    expected = json.dumps(record, sort_keys=True).encode()
    if target.exists():
        if decrypt_secret(target, vault_key) != expected:
            raise ProvisionError('Recovery identity or credential conflicts with the existing vault record')
    else:
        _publish_ciphertext(_encrypt_bytes(expected, vault_key, MASTER_VAULT_ID), target, replace=False)
    if decrypt_secret(target, vault_key) != expected:
        raise ProvisionError('Primary recovery record failed authentication')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    ciphertext = target.read_bytes()
    if export is not None and export(ciphertext) != ciphertext:
        raise ProvisionError('Independent recovery export did not return the stored ciphertext')
    if independent_required or (vault / 'storage-recovery/custody.json').exists():
        from lx_administration.storage.recovery_custody import export_configured
        export_configured(vault, vault_key, target)
    # Equality to authenticated ciphertext is also checked after remote durable publication.
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'escrow', 'provision'])
    parser.add_argument('--host', required=True)
    parser.add_argument('--volume', required=True)
    parser.add_argument('--recovery-host')
    parser.add_argument('--controller-only-custody', action='store_true',
                        help='escrow only: explicitly defer the independent recovery copy')
    parser.add_argument('--backend', choices=['passphrase', 'tpm2', 'local-openbao'],
                        help='Explicit deploy-time backend; does not change the boot unlock policy')
    parser.add_argument('--local-target', action='store_true',
                        help='Run target commands locally; --host must match the local hostname')
    parser.add_argument('--vault-dir', type=Path, default=Path.home() / '.lxv')
    parser.add_argument('--vault-key', type=Path, default=Path.home() / '.lxv.key')
    parser.add_argument('--existing-key-file', type=Path)
    parser.add_argument('--sudo-password-file', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if args.controller_only_custody:
        if args.action != 'escrow' or args.recovery_host:
            parser.error('--controller-only-custody requires escrow without --recovery-host')
    elif not args.recovery_host and args.action != 'setup':
        parser.error('--recovery-host is required unless explicitly escrowing on the controller only')
    if args.action == 'setup' and args.backend:
        parser.error('setup preserves keys and does not select an unlock backend')
    for value in [args.host, args.volume, args.recovery_host or 'x']:
        if not re.fullmatch('[a-z0-9][a-z0-9-]*', value):
            parser.error('Host and volume names must be canonical inventory identifiers')
    if args.action == 'provision':
        if (args.host not in {'gc-09', 'gc-10'}
                or args.backend not in {None, 'passphrase'}):
            raise ProvisionError(
                'New container enrollment is retired; '
                'only gc-09/gc-10 passphrase migration remains'
            )
        layout = subprocess.run(['nix', 'eval', '--json',
            f'.#nixosConfigurations.{args.host}.config.luxnix.storage.operatorUnlocked.layout'],
            capture_output=True, check=True)
        if json.loads(layout.stdout) != 'legacy-containers':
            raise ProvisionError('Container provisioning is retired for boot-luks; follow docs/boot-storage-migration.md')
    config = AutoconfConfig.load(DEFAULT_CONFIG_PATH)
    inventory = AnsibleInventory.load_from_hosts_ini(
        config.ansible_root / 'inventory/hosts.ini', config.inventory_subnet)
    def connection(host, password=None, *, local=False):
        entry = inventory.get_host_by_name(host)
        if entry is None:
            raise ProvisionError('Host is not in the inventory')
        if local:
            return Local(host, password)
        return Remote(str(entry.ansible_host), password)
    target = connection(args.host, args.sudo_password_file, local=args.local_target)
    recovery = connection(args.recovery_host) if args.recovery_host else None
    machine_id = target.machine_id()
    if recovery is not None and recovery.machine_id() in {machine_id, Path('/etc/machine-id').read_text().strip()}:
        raise ProvisionError('Emergency export must be on a separate host from both target and admin vault')
    root = args.volume == 'cryptroot' and args.action == 'setup'
    prefix = f'.#nixosConfigurations.{args.host}.config.'
    expression = prefix + (
        'boot.initrd.luks.devices.cryptroot.device' if root else
        f'luxnix.storage.operatorUnlocked.volumes.{args.volume}'
    )
    result = subprocess.run(['nix', 'eval', '--json', expression], capture_output=True, check=True)
    value = json.loads(result.stdout)
    volume = {'container': value} if root else value
    container = volume['container']
    if not container:
        raise ProvisionError('Provisioning requires a declared container path')
    exists = target.call([
        'sh', '-c', 'if test -e "$1"; then echo yes; else echo no; fi',
        'probe', container,
    ], privileged=args.action == 'setup').strip() == b'yes'
    native_uuid = target.call(['cryptsetup', 'luksUUID', container], privileged=True).decode().strip() if exists else None
    if native_uuid is not None:
        native_uuid = str(uuid.UUID(native_uuid))
        if volume.get('luksUUID') and native_uuid != volume['luksUUID']:
            raise ProvisionError('Native LUKS UUID does not match the declared volume')
    if args.action in {'escrow', 'setup'} and not exists:
        raise ProvisionError(
            'Password custody requires an existing LUKS volume; '
            'install the reviewed Disko layout first'
        )
    backend = None
    if args.action == 'provision':
        mode_expression = (
            f'.#nixosConfigurations.{args.host}'
            '.config.luxnix.storage.operatorUnlocked.unlockMethod'
        )
        mode = subprocess.run(['nix', 'eval', '--json',
            mode_expression],
            capture_output=True, check=True)
        configured_method = json.loads(mode.stdout)
        backend = args.backend or configured_method
        if backend not in ('passphrase', 'tpm2', 'local-openbao'):
            raise ProvisionError('Unsupported storage provisioning backend')
        if backend == 'passphrase' and configured_method != 'passphrase':
            raise ProvisionError(
                'Passphrase provisioning requires the configured passphrase unlock policy'
            )
    summary = {'host': args.host, 'machine_id': machine_id, 'volume': args.volume,
               'container': container, 'exists': exists, 'luks_uuid': native_uuid,
               'recovery_host': args.recovery_host, 'action': args.action}
    if backend is not None:
        summary['backend'] = backend
    if args.local_target:
        summary['local_target'] = True
    if not args.apply:
        print(json.dumps(summary, sort_keys=True))
        return
    if not args.vault_dir.is_dir():
        raise ProvisionError('Existing admin vault directory is required')
    independent_required = (
        args.action in {'provision', 'setup'}
        and require_independent_custody(args.vault_dir)
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    encrypted_storage(args.vault_key, allow_runtime=True)
    Vault.load_dir(str(args.vault_dir), str(args.vault_key)).validate_local_key()
    lock_dir = ensure_private_directory(args.vault_dir / 'storage-recovery')
    with (lock_dir / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        primary = lock_dir / machine_id / (args.volume + '.vault')
        if primary.exists():
            record = json.loads(decrypt_secret(primary, args.vault_key))
            if (record['machine_id'] != machine_id or record['volume'] != args.volume
                    or record['container'] != container or record['host'] != args.host
                    or (native_uuid is not None and record['luks_uuid'] != native_uuid)):
                raise ProvisionError('Existing recovery record does not match the selected volume')
            if not exists and record.get('origin') != 'new':
                raise ProvisionError('An existing-volume recovery record cannot authorize replacement storage')
        else:
            if exists:
                if args.existing_key_file is None:
                    if args.action != 'setup':
                        raise ProvisionError(
                            'Existing containers require their recovery credential'
                        )
                    from .password_custody import ask
                    key = ask(args.host, args.volume)
                else:
                    encrypted_storage(args.existing_key_file, allow_runtime=True)
                    from .boot_password import private
                    private(args.existing_key_file)
                    raw = args.existing_key_file.read_bytes()
                    # setup uses exact file bytes, including a deliberate newline.
                    key = (
                        raw if args.action == 'setup' else raw.rstrip(b'\r\n')
                    ).decode('utf-8')
                if not key or len(key.encode()) > 512 or '\0' in key:
                    raise ProvisionError(
                        'Use a recovery passphrase of 1 to 512 UTF-8 bytes without NUL'
                    )
            else:
                key = secrets.token_hex(32)
            record = dict(summary, schema_version=1, luks_uuid=native_uuid or volume.get('luksUUID') or str(uuid.uuid4()),
                          recovery_passphrase=key, origin='existing' if exists else 'new')
            record.pop('exists')
            record.pop('action')
            record.pop('backend', None)
            record.pop('local_target', None)
        if exists:
            target.call(['cryptsetup', 'open', '--test-passphrase', '--key-file=-', container],
                        record['recovery_passphrase'].encode(), privileged=True)
        destination = (f'{args.recovery_host}:~/.luxnix-recovery/{machine_id}/{record["luks_uuid"]}.vault'
                       if recovery is not None else None)
        primary = escrow_record(args.vault_dir, args.vault_key, record,
            (lambda ciphertext: recovery.call(['python3', '-c', EXPORT, machine_id, record['luks_uuid']], ciphertext))
            if recovery is not None else None, independent_required=independent_required)
        if args.action == 'setup':
            from .password_custody import acknowledge
            acknowledge(primary, record)
        if args.action == 'provision':
            request = dict(record, primary_escrow=str(primary), emergency_export=destination)
            request['backend'] = backend
            if backend == 'local-openbao':
                from lx_administration.storage.local_enrollment import load_escrow
                enrollment = load_escrow(args.vault_dir, args.vault_key, args.host, 'enrollment')
                if enrollment is None or enrollment['machine_id'] != machine_id:
                    raise ProvisionError('Local OpenBao enrollment escrow is missing or belongs to another machine')
                request['provisioner'] = enrollment['provisioner']
            target.call(['luxnix-storage-provision', args.volume], json.dumps(request).encode(), privileged=True)
        print(json.dumps(dict(summary, luks_uuid=record['luks_uuid'], primary_escrow=str(primary),
                              emergency_export=destination, escrow_verified=True), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Do not print subprocess output, decrypted records, or validation payloads.
        detail = (
            str(exc) if isinstance(exc, (ProvisionError, CustodyError))
            else type(exc).__name__
        )
        print(f'ERROR: storage provisioning blocked: {detail}; no startup migration requested',
              file=__import__('sys').stderr)
        raise SystemExit(1) from None
