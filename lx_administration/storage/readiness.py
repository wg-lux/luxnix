"""Read-only storage observations with explicit, fail-closed baseline admission.

Admission is a current-host baseline, never backup, restore or deployment approval.
This stdlib-only collector can run from controller-supplied stdin on old hosts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

GENERATIONS = ('/run/current-system', '/run/booted-system', '/nix/var/nix/profiles/system')
LEGACY_MOUNTS = ('/var/lib/luxnix-secrets', '/var/lib/luxnix-app-storage')
CORE_PROBES = ('block_devices', 'capacity', 'privilege', 'boot_entries', 'active_units', 'swap')


def probe(*argv: str) -> dict:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return {'exit': result.returncode, 'output': result.stdout.strip(),
                'error': result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'exit': None, 'error': type(error).__name__}


def link(path: str) -> str | None:
    p = Path(path)
    return str(p.resolve()) if p.exists() else None


def collect(layout: str | None) -> dict:
    firmware = Path('/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c')
    try:
        raw = firmware.read_bytes()
        secure_boot = raw[4] == 1 if len(raw) == 5 else 'invalid-variable'
    except OSError as error:
        secure_boot = type(error).__name__
    report = {
        'schema_version': 1,
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'host': socket.gethostname(),
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'generations': {p: link(p) for p in GENERATIONS},
        'secure_boot': secure_boot,
        'tpm_driver': link('/sys/class/tpm/tpm0/device/driver'),
        'virtualization': probe('systemd-detect-virt'),
        'block_devices': probe('lsblk', '--json', '--paths', '--output',
                               'NAME,TYPE,FSTYPE,UUID,SIZE,SERIAL,MOUNTPOINTS'),
        'capacity': probe('df', '-B1', '--output=source,size,used,avail,target'),
        'btrfs': probe('btrfs', 'filesystem', 'show'),
        'privilege': probe('id', '-u'),
        'boot_entries': probe('bootctl', 'list', '--no-pager'),
        'backup_sizes': probe('du', '-s', '-B1', '/etc', '/var', '/home', '/root', '/persist', '/data'),
        'active_units': probe('systemctl', 'list-units', '--state=active', '--type=service,timer', '--no-pager', '--no-legend'),
        'mounts': {path: probe('findmnt', '--json', '--mountpoint', path,
                               '--output', 'TARGET,SOURCE,FSTYPE,OPTIONS') for path in [
            '/', '/nix/store', '/etc/secrets', '/etc/secrets/vault', *LEGACY_MOUNTS,
            '/var/lib/postgresql', '/var/lib/lx-annotate']},
        'swap': probe('swapon', '--show', '--noheadings', '--output', 'NAME,TYPE'),
        'services': {unit: probe('systemctl', 'is-active', unit) for unit in [
            'sshd', 'postgresql', 'lx-annotate', 'lx-annotate-celery-worker',
            'openbao-local', 'luxnix-storage-migrate']},
    }
    # Record device aliases while still on the probed host, not on the controller.
    report['device_aliases'] = {}
    try:
        for node in nodes(json.loads(report['block_devices']['output'])['blockdevices']):
            report['device_aliases'][node['name']] = os.path.realpath(node['name'])
        for result in report['mounts'].values():
            if result['exit'] == 0:
                for fs in json.loads(result['output'])['filesystems']:
                    source = fs['source'].split('[', 1)[0]
                    report['device_aliases'][source] = os.path.realpath(source)
    except (KeyError, TypeError, ValueError):
        # The evaluator rejects malformed probes; observations remain inspectable.
        pass
    if layout == 'boot-luks':
        report['boot_storage'] = probe('/run/current-system/sw/bin/luxnix-verify-boot-storage')
    return report


def nodes(items):
    if not isinstance(items, list) or not items:
        raise ValueError('Missing block-device inventory')
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ValueError('Invalid block-device record')
        yield item
        if item.get('children'):
            yield from nodes(item['children'])


def evaluate(report: dict, expected_host: str, expected_layout: str,
             expected_serials: list[str]) -> dict:
    """Evaluate a supplied observation; callers must obtain it from a trusted host."""
    reasons = []
    def reject(code, message):
        reasons.append({'code': code, 'message': message})
    def successful(result):
        return isinstance(result, dict) and type(result.get('exit')) is int and result['exit'] == 0 and isinstance(result.get('output'), str)
    if report.get('host') != expected_host:
        reject('host_mismatch', 'The responding computer is not the selected computer.')
    if expected_layout not in ('legacy-containers', 'unencrypted-root', 'boot-luks'):
        reject('layout_unspecified', 'Select the existing storage layout explicitly.')
    if (not isinstance(expected_serials, list) or not expected_serials
            or any(not isinstance(s, str) or not s.strip() or s != s.strip() for s in expected_serials)
            or len(set(expected_serials)) != len(expected_serials)):
        reject('serials_unspecified', 'Supply the reviewed, unique serial numbers of every attached physical disk.')
    if not isinstance(report.get('boot_id'), str) or not report['boot_id']:
        reject('boot_identity_missing', 'The current boot could not be identified.')
    for name in CORE_PROBES:
        if not successful(report.get(name)):
            reject('probe_failed', f'Required check did not complete: {name}.')
    if not successful(report.get('privilege')) or report['privilege']['output'] != '0':
        reject('privilege_required', 'Admission requires administrator access to inspect all storage.')
    generations = report.get('generations', {})
    values = [generations.get(p) for p in GENERATIONS] if isinstance(generations, dict) else []
    if (len(values) != 3 or any(not isinstance(v, str) or not v.startswith('/nix/store/') for v in values)
            or len(set(values)) != 1):
        reject('generation_mismatch', 'Running, booted and selected systems must match before migration.')
    if successful(report.get('swap')) and report['swap']['output']:
        reject('swap_active', 'This migration admission requires swap to be disabled; no swap changes were made.')
    try:
        devices = list(nodes(json.loads(report['block_devices']['output'])['blockdevices']))
        disks = {d['name']: d for d in devices if d.get('type') == 'disk'}
        serials = [d.get('serial', '').strip() if isinstance(d.get('serial'), str) else '' for d in disks.values()]
        if (not serials or not all(serials) or len(set(serials)) != len(serials)
                or set(serials) != set(expected_serials)):
            reject('disk_identity_mismatch', 'Attached disks do not exactly match the reviewed serial numbers.')
        aliases = report.get('device_aliases', {})
        mounts = report['mounts']
        def mount(path):
            if not successful(mounts.get(path)):
                raise ValueError(f'Required mount is unavailable: {path}.')
            fs = json.loads(mounts[path]['output'])['filesystems']
            if len(fs) != 1 or fs[0].get('target') != path:
                raise ValueError(f'Required mount is ambiguous: {path}.')
            source = fs[0]['source'].split('[', 1)[0]
            matches = [d for d in devices if aliases.get(d['name'], d['name']) == aliases.get(source, source)]
            if not matches or any(not d.get('uuid') for d in matches):
                raise ValueError(f'Required mount lacks a recorded filesystem identity: {path}.')
            return matches
        root = mount('/')
        if expected_layout == 'boot-luks':
            if any(d.get('type') != 'crypt' for d in root):
                reject('root_not_encrypted', 'The selected installed layout requires encrypted root.')
            for path in LEGACY_MOUNTS:
                if not isinstance(mounts.get(path), dict) or mounts[path].get('exit') != 1:
                    reject('legacy_mount_present', 'Legacy mounts remain present or could not be ruled out.')
            if not successful(report.get('boot_storage')):
                reject('boot_storage_failed', 'Installed storage verification failed or is unavailable; do not install or reboot.')
        elif expected_layout in {'legacy-containers', 'unencrypted-root'}:
            for path in LEGACY_MOUNTS:
                if any(d.get('type') != 'crypt' for d in mount(path)):
                    reject('legacy_not_encrypted', f'Existing protected storage is not unlocked through encryption: {path}.')
        if any(d.get('fstype') == 'btrfs' for d in root) and not successful(report.get('btrfs')):
            reject('btrfs_probe_failed', 'Btrfs membership could not be inspected.')
    except (KeyError, TypeError, ValueError, AttributeError):
        reject('storage_evidence_invalid', 'Storage identity or required mount evidence is missing or invalid.')
    return {'admitted': not reasons, 'reasons': reasons, 'scope': 'storage-baseline-only',
            'expected_host': expected_host, 'expected_layout': expected_layout,
            'expected_serials': expected_serials,
            'notice': 'This is not permission to erase disks, proof of recoverable backups, or cold-boot acceptance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-host', required=True)
    parser.add_argument('--mode', choices=['observe', 'admit'], default='observe')
    parser.add_argument('--expected-layout', choices=['legacy-containers', 'unencrypted-root', 'boot-luks'])
    parser.add_argument('--expected-serials', type=json.loads, default=[])
    args = parser.parse_args()
    report = collect(args.expected_layout)
    report['report_sha256'] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if args.mode == 'admit':
        report['admission'] = evaluate(report, args.expected_host, args.expected_layout, args.expected_serials)
    print(json.dumps(report, sort_keys=True))
    return int(report['host'] != args.expected_host or
               (args.mode == 'admit' and not report['admission']['admitted']))


if __name__ == '__main__':
    sys.exit(main())
