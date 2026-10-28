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
import secrets
import shlex
import subprocess
import uuid

from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.models.vault import Vault
from lx_administration.models.vault.secret import (
    MASTER_VAULT_ID, _encrypt_bytes, _publish_ciphertext, decrypt_secret,
)
from lx_administration.permissions import ensure_private_directory
from lx_administration.secret_storage import encrypted_storage


class ProvisionError(RuntimeError):
    """An operator-safe diagnostic without credential values."""


# No secret values are interpolated into this code or its arguments.
EXPORT = r'''
import fcntl, os, sys, tempfile
from pathlib import Path
machine, identifier = sys.argv[1:]
import re
assert re.fullmatch(r'[0-9a-f]{32}', machine)
assert re.fullmatch(r'[0-9a-f-]{36}', identifier)
data = sys.stdin.buffer.read()
assert data.startswith(b'$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n')
root = Path.home() / '.luxnix-recovery'
for directory in [root, root / machine]:
    directory.mkdir(mode=0o700, exist_ok=True)
    assert not directory.is_symlink()
    info = directory.stat()
    assert info.st_uid == os.geteuid() and info.st_mode & 0o777 == 0o700
with (root / '.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    target = root / machine / (identifier + '.vault')
    assert not target.is_symlink()
    if target.exists():
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.read_bytes() == data, 'Conflicting recovery export'
    else:
        fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.recovery-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target)
        finally: os.unlink(temporary)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    sys.stdout.buffer.write(target.read_bytes())
'''


class Remote:
    def __init__(self, address, sudo_password_file=None):
        self.ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30',
                    '-o', 'ServerAliveCountMax=2', 'admin@' + address]
        self.password_file = sudo_password_file
        self.password_required = None

    def call(self, args, data=b'', privileged=False, relay_error=False):
        if privileged:
            if self.password_required is None:
                probe = subprocess.run(self.ssh + ['sudo -n true'], capture_output=True, timeout=30)
                self.password_required = probe.returncode != 0
            if self.password_required:
                if self.password_file is None:
                    raise ProvisionError('A private sudo-password file is required for this target')
                encrypted_storage(self.password_file, allow_runtime=True)
                if self.password_file.is_symlink() or self.password_file.stat().st_mode & 0o077:
                    raise ProvisionError('Sudo-password file must be private and not a symlink')
                data = self.password_file.read_bytes().rstrip(b'\r\n') + b'\n' + data
                args = ['sudo', '-k', '-S', '-p', '', *args]
            else:
                args = ['sudo', '-n', *args]
        result = subprocess.run(self.ssh + [shlex.join(args)], input=data, capture_output=True, timeout=600)
        if result.returncode:
            # Remote diagnostics may contain credential-bearing input. Relay only the
            # single ERROR line of a LuxNix tool that builds it without secret values.
            lines = result.stderr.decode(errors='replace').strip().splitlines()
            if relay_error and lines and re.fullmatch(r'ERROR: [A-Za-z0-9 ,.:;/_()-]{1,200}', lines[-1]):
                raise ProvisionError(f'Remote operation failed: {lines[-1][7:]}')
            raise ProvisionError(f'Remote operation failed (exit {result.returncode})')
        return result.stdout

    def machine_id(self):
        value = self.call(['cat', '/etc/machine-id']).decode().strip()
        if not re.fullmatch('[0-9a-f]{32}', value):
            raise ProvisionError('Invalid machine identity')
        return value


def escrow_record(vault, vault_key, record, export):
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
    # Equality to authenticated ciphertext is also checked after remote durable publication.
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['escrow', 'provision'])
    parser.add_argument('--host', required=True)
    parser.add_argument('--volume', required=True)
    parser.add_argument('--recovery-host')
    parser.add_argument('--controller-only-custody', action='store_true',
                        help='escrow only: explicitly defer the independent recovery copy')
    parser.add_argument('--backend', choices=['tpm2', 'local-openbao'],
                        help='Explicit deploy-time backend; does not change the boot unlock policy')
    parser.add_argument('--vault-dir', type=Path, default=Path.home() / '.lxv')
    parser.add_argument('--vault-key', type=Path, default=Path.home() / '.lxv.key')
    parser.add_argument('--existing-key-file', type=Path)
    parser.add_argument('--sudo-password-file', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if args.controller_only_custody:
        if args.action != 'escrow' or args.recovery_host:
            parser.error('--controller-only-custody requires escrow without --recovery-host')
    elif not args.recovery_host:
        parser.error('--recovery-host is required unless explicitly escrowing on the controller only')
    for value in [args.host, args.volume, args.recovery_host or 'x']:
        if not re.fullmatch('[a-z0-9][a-z0-9-]*', value):
            parser.error('Host and volume names must be canonical inventory identifiers')
    config = AutoconfConfig.load(DEFAULT_CONFIG_PATH)
    inventory = AnsibleInventory.load_from_hosts_ini(
        config.ansible_root / 'inventory/hosts.ini', config.inventory_subnet)
    def remote(host, password=None):
        entry = inventory.get_host_by_name(host)
        if entry is None:
            raise ProvisionError('Host is not in the inventory')
        return Remote(str(entry.ansible_host), password)
    target = remote(args.host, args.sudo_password_file)
    recovery = None if args.controller_only_custody else remote(args.recovery_host)
    machine_id = target.machine_id()
    if recovery is not None and recovery.machine_id() in {machine_id, Path('/etc/machine-id').read_text().strip()}:
        raise ProvisionError('Emergency export must be on a separate host from both target and admin vault')
    expression = f'.#nixosConfigurations.{args.host}.config.luxnix.storage.operatorUnlocked.volumes.{args.volume}'
    result = subprocess.run(['nix', 'eval', '--json', expression], capture_output=True, check=True)
    volume = json.loads(result.stdout)
    container = volume['container']
    if not container:
        raise ProvisionError('Provisioning requires a declared container path')
    exists = target.call(['sh', '-c', 'if test -e "$1"; then echo yes; else echo no; fi', 'probe', container]).strip() == b'yes'
    native_uuid = target.call(['cryptsetup', 'luksUUID', container], privileged=True).decode().strip() if exists else None
    if native_uuid is not None:
        native_uuid = str(uuid.UUID(native_uuid))
    if args.action == 'escrow' and not exists:
        raise ProvisionError('Existing-volume escrow requires a LUKS container')
    summary = {'host': args.host, 'machine_id': machine_id, 'volume': args.volume,
               'container': container, 'exists': exists, 'luks_uuid': native_uuid,
               'recovery_host': args.recovery_host, 'action': args.action}
    if not args.apply:
        print(json.dumps(summary, sort_keys=True))
        return
    if not args.vault_dir.is_dir():
        raise ProvisionError('Existing admin vault directory is required')
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
                    raise ProvisionError('Existing containers require their current recovery credential')
                encrypted_storage(args.existing_key_file, allow_runtime=True)
                if args.existing_key_file.is_symlink() or args.existing_key_file.stat().st_mode & 0o077:
                    raise ProvisionError('Existing recovery credential file must be private')
                key = args.existing_key_file.read_bytes().rstrip(b'\r\n').decode('ascii')
            else:
                key = secrets.token_hex(32)
            record = dict(summary, schema_version=1, luks_uuid=native_uuid or volume.get('luksUUID') or str(uuid.uuid4()),
                          recovery_passphrase=key, origin='existing' if exists else 'new')
            record.pop('exists')
            record.pop('action')
        if exists:
            target.call(['cryptsetup', 'open', '--test-passphrase', '--key-file=-', container],
                        record['recovery_passphrase'].encode(), privileged=True)
        destination = (f'{args.recovery_host}:~/.luxnix-recovery/{machine_id}/{record["luks_uuid"]}.vault'
                       if recovery is not None else None)
        primary = escrow_record(args.vault_dir, args.vault_key, record,
            (lambda ciphertext: recovery.call(['python3', '-c', EXPORT, machine_id, record['luks_uuid']], ciphertext))
            if recovery is not None else None)
        if args.action == 'provision':
            request = dict(record, primary_escrow=str(primary), emergency_export=destination)
            backend = args.backend
            if backend is None:
                mode = subprocess.run(['nix', 'eval', '--json',
                    f'.#nixosConfigurations.{args.host}.config.luxnix.storage.operatorUnlocked.unlockMethod'],
                    capture_output=True, check=True)
                backend = json.loads(mode.stdout)
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
        detail = str(exc) if isinstance(exc, ProvisionError) else type(exc).__name__
        print(f'ERROR: storage provisioning blocked: {detail}; no startup migration requested',
              file=__import__('sys').stderr)
        raise SystemExit(1) from None
