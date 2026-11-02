"""Explicit migration snapshots with retained sources and operator-driven recovery."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

BASE = Path('/var/lib/luxnix-migration-snapshots')
INNER = ('/var/lib/luxnix-app-storage', '/var/lib/luxnix-secrets')
LOCK_FD = None


def run(*args, timeout=1200):
    # A child retains the operation lock if its supervisor is killed mid-command.
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            pass_fds=() if LOCK_FD is None else (LOCK_FD,),
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}); sources retained')
    return result.stdout


def writer(unit):
    return (unit.endswith(('.service', '.timer')) and
            (unit.startswith(('postgresql', 'lx-annotate', 'redis-lx-annotate')) or
             unit in {'nginx.service', 'openbao-local.service', 'vault.service'}))


def private(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if path.resolve() != path or not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('Unsafe snapshot journal; use the original root-private state')


def save(path, report):
    fd, name = tempfile.mkstemp(prefix='.plan-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load(path):
    private(path.parent, directory=True)
    private(path)
    report = json.loads(path.read_text())
    if report.get('schema_version') != 1:
        raise ValueError('Old or unknown snapshot journal: operator review required; do not replace it')
    paths = {'/', '/home', '/nix', '/persist', '/var/log'}
    if report.get('host') == 'gc-10':
        paths.add('/data/raid01')
    if (set(report['mounts']) != paths or set(report['source_subvolumes']) != paths
            or not set(report['inner_mounts']).issubset(INNER)
            or not set(report['pending_freezes']).issubset(report['inner_mounts'])
            or not set(report['pending_restart']).issubset(report['previously_active'])
            or not all(writer(u) for u in report['pending_masks'] + report['previously_active'])
            or report['state'] not in {'in_progress', 'recovery_required', 'recovered', 'complete'}):
        raise ValueError('Invalid snapshot recovery journal')
    for item in report['snapshots']:
        source = item['source']
        name = 'root' if source == '/' else source.strip('/').replace('/', '-')
        parent = path.parent if source != '/data/raid01' else Path(source) / '.luxnix-migration-snapshots' / report['identifier']
        if source not in paths or item['name'] != name or item['snapshot'] != str(parent / name):
            raise ValueError('Invalid retained snapshot path')
    return report


@contextmanager
def operation(action):
    global LOCK_FD
    if action == 'snapshot':
        BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    private(BASE, directory=True)
    flags = os.O_NOFOLLOW | (os.O_RDONLY if action == 'status' else os.O_RDWR | os.O_CREAT)
    fd = os.open(BASE / '.lock', flags, 0o600)
    try:
        private(BASE / '.lock')
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if action == 'status' else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another snapshot operation is running; wait for it to finish') from error
        LOCK_FD = fd
        yield
    finally:
        LOCK_FD = None
        os.close(fd)


def mount_identity(path, optional=False):
    result = subprocess.run(['findmnt', '--json', '--mountpoint', path,
                             '--output', 'SOURCE,FSTYPE,UUID,FSROOT'],
                            capture_output=True, text=True, timeout=30)
    if optional and result.returncode == 1:
        return None
    if result.returncode:
        raise ValueError(f'Cannot identify mounted source {path}')
    records = json.loads(result.stdout)['filesystems']
    if len(records) != 1 or not all(records[0].get(k) for k in ('source', 'fstype', 'uuid', 'fsroot')):
        raise ValueError(f'Missing or ambiguous source identity at {path}')
    return {k: records[0][k] for k in ('source', 'fstype', 'uuid', 'fsroot')}


def subvolume(path):
    fields = {}
    for line in run('btrfs', 'subvolume', 'show', str(path), timeout=30).splitlines():
        if ':' in line:
            key, value = line.strip().split(':', 1)
            fields[key] = value.strip()
    if not fields.get('UUID') or not fields.get('Parent UUID'):
        raise ValueError('Cannot identify Btrfs subvolume')
    return {'uuid': fields['UUID'], 'parent_uuid': fields['Parent UUID']}


def check_sources(report):
    for path, expected in report['mounts'].items():
        if mount_identity(path) != expected or subvolume(path) != report['source_subvolumes'][path]:
            raise ValueError(f'Source changed at {path}; operator review required')


def check_snapshots(report):
    for item in report['snapshots']:
        target = Path(item['snapshot'])
        if target.resolve() != target or subvolume(target) != item['identity']:
            raise ValueError('Retained snapshot identity changed; refuse reuse')
        if item['identity']['parent_uuid'] != report['source_subvolumes'][item['source']]['uuid']:
            raise ValueError('Retained snapshot belongs to another source')
        if run('btrfs', 'property', 'get', '-ts', str(target), 'ro', timeout=30).strip() != 'ro=true':
            raise ValueError('Retained snapshot is not read-only')


def thaw(path):
    # FITHAW returns EINVAL when an intent was journaled but freezing never ran,
    # or after a reboot. That is the only safe idempotent no-op error.
    run(sys.executable, '-c', '''import errno, fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    try:
        fcntl.ioctl(fd, 0xC0045878, 0)
    except OSError as error:
        if error.errno != errno.EINVAL:
            raise
finally:
    os.close(fd)
''', path, timeout=30)


def openbao_ready():
    # Reuse the service's actual initialized, unsealed and active API contract.
    if __package__:
        from .openbao_local import wait_unsealed
    else:
        from openbao_local import wait_unsealed
    wait_unsealed(30)


def restore(plan, report):
    """Restore recorded state only; leave every snapshot and source untouched."""
    check_sources(report)
    errors = []
    for path in list(reversed(report['pending_freezes'])):
        try:
            if mount_identity(path) != report['inner_mounts'][path]:
                raise ValueError('Frozen filesystem identity changed')
            thaw(path)
            report['pending_freezes'].remove(path)
            save(plan, report)
        except Exception:
            errors.append('unfreeze ' + path)
    # OpenBao must be usable before dependent writers are unmasked. An active
    # process may still be sealed; no credential generation or unseal is attempted.
    bao = 'openbao-local.service'
    if not errors and bao in report['pending_restart']:
        try:
            if bao in report['pending_masks']:
                run('systemctl', 'unmask', '--runtime', bao, timeout=30)
                report['pending_masks'].remove(bao)
                save(plan, report)
            run('systemctl', 'start', bao, timeout=120)
            openbao_ready()
            report['pending_restart'].remove(bao)
            save(plan, report)
        except Exception:
            errors.append('restore unsealed active local OpenBao')
    # Keep other writers masked if thaw or OpenBao readiness could not be verified.
    if not errors:
        for unit in list(report['pending_masks']):
            try:
                run('systemctl', 'unmask', '--runtime', unit, timeout=30)
                report['pending_masks'].remove(unit)
                save(plan, report)
            except Exception:
                errors.append('unmask ' + unit)
        if not errors:
            for unit in list(report['pending_restart']):
                try:
                    run('systemctl', 'start', unit, timeout=120)
                    if run('systemctl', 'show', unit, '-p', 'ActiveState', '--value', timeout=30).strip() != 'active':
                        raise ValueError('Previously active writer failed to start')
                    report['pending_restart'].remove(unit)
                    save(plan, report)
                except Exception:
                    errors.append('restart ' + unit)
    report['recovery_errors'] = errors
    report['state'] = 'recovery_required' if errors else 'recovered'
    save(plan, report)
    if errors:
        raise RuntimeError('Operator recovery required: ' + ', '.join(errors))


def automatic_recovery(host, identifier):
    """ExecStopPost recovery: bounded retries after the worker cgroup has stopped."""
    if host not in {'gc-09', 'gc-10'} or socket.gethostname() != host:
        raise ValueError('Target identity mismatch')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{5,60}', identifier):
        raise ValueError('Invalid snapshot identifier')
    if not (BASE / identifier / 'plan.json').exists():
        # The first durable journal precedes every mask, stop and freeze.
        return {'changed': False, 'state': 'not_started'}
    for attempt in range(3):
        try:
            return snapshot(host, identifier, 'recover')
        except (OSError, ValueError, RuntimeError):
            if attempt == 2:
                raise
            time.sleep(5)


def snapshot(host, identifier, action='snapshot'):
    if host not in {'gc-09', 'gc-10'} or socket.gethostname() != host:
        raise ValueError('Target identity mismatch')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{5,60}', identifier) or action not in {'snapshot', 'recover', 'status'}:
        raise ValueError('Invalid snapshot identifier or action')
    root = BASE / identifier
    plan = root / 'plan.json'
    with operation(action):
        if root.exists() or root.is_symlink():
            report = load(plan)
            if report['host'] != host or report['identifier'] != identifier:
                raise ValueError('Journal target mismatch')
            if action == 'status':
                return report | {'changed': False}
            check_sources(report)
            if report['state'] == 'complete' and report['complete']:
                check_snapshots(report)
                return report | {'changed': False}
            if action == 'recover':
                if report['state'] == 'recovered':
                    return report | {'changed': False}
                restore(plan, report)
                return report | {'changed': True}
            raise ValueError('Incomplete run retained: use recover, then a new snapshot identifier')
        if action != 'snapshot':
            raise ValueError('No existing snapshot journal for this identifier')
        # No new operation may obscure another interrupted run on this host.
        for candidate in BASE.iterdir():
            if candidate.name.startswith('.'):
                continue
            prior = load(candidate / 'plan.json')
            if prior['state'] not in {'complete', 'recovered'}:
                raise ValueError(f'Interrupted run {candidate.name}: recover it before taking new snapshots')
        paths = ['/', '/home', '/nix', '/persist', '/var/log']
        if host == 'gc-10':
            paths.append('/data/raid01')
        mounts = {path: mount_identity(path) for path in paths}
        if any(fs['fstype'] != 'btrfs' for fs in mounts.values()):
            raise ValueError('Expected existing Btrfs filesystem')
        identities = {path: subvolume(path) for path in paths}
        inner = {path: fs for path in INNER if (fs := mount_identity(path, optional=True)) is not None}
        units = [line.split()[0] for line in run('systemctl', 'list-units', '--all',
                 '--type=service,timer', '--no-legend', '--no-pager', timeout=30).splitlines()
                 if line.strip() and writer(line.split()[0])]
        active, to_mask = [], []
        for unit in units:
            state = run('systemctl', 'show', unit, '-p', 'ActiveState', '--value', timeout=30).strip()
            if state not in {'active', 'inactive', 'failed'}:
                raise ValueError('A writer is changing state; wait before snapshotting')
            if state == 'active':
                active.append(unit)
            masked = run('systemctl', 'show', unit, '-p', 'LoadState', '--value', timeout=30).strip() == 'masked'
            if masked and state == 'active':
                raise ValueError('An active writer was already masked; operator review is required before stopping it')
            if not masked:
                to_mask.append(unit)
        root.mkdir(mode=0o700)
        report = {'schema_version': 1, 'host': host, 'identifier': identifier, 'mounts': mounts,
                  'source_subvolumes': identities, 'inner_mounts': inner,
                  'previously_active': active, 'snapshots': [], 'complete': False,
                  'pending_masks': [], 'pending_freezes': [], 'pending_restart': [],
                  'state': 'in_progress', 'recovery_errors': []}
        save(plan, report)
        try:
            for unit in to_mask:
                report['pending_masks'].append(unit)
                save(plan, report)
                run('systemctl', 'mask', '--runtime', unit, timeout=30)
            report['pending_restart'] = list(active)
            save(plan, report)
            if active:
                run('systemctl', 'stop', *active)
            for unit in units:
                if run('systemctl', 'show', unit, '-p', 'ActiveState', '--value', timeout=30).strip() not in {'inactive', 'failed'}:
                    raise ValueError('An application writer did not stop')
            for path in inner:
                if mount_identity(path) != inner[path]:
                    raise ValueError('Inner filesystem changed before freeze')
                report['pending_freezes'].append(path)
                save(plan, report)
                run('fsfreeze', '--freeze', path, timeout=30)
            for path in paths:
                name = 'root' if path == '/' else path.strip('/').replace('/', '-')
                parent = root if path != '/data/raid01' else Path(path) / '.luxnix-migration-snapshots' / identifier
                parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                private(parent, directory=True)
                target = parent / name
                if target.exists() or target.is_symlink():
                    raise ValueError('Snapshot destination exists; never replace it')
                report['pending_snapshot'] = {'source': path, 'snapshot': str(target), 'name': name}
                save(plan, report)
                run('btrfs', 'subvolume', 'snapshot', '-r', path, str(target))
                report['snapshots'].append(report.pop('pending_snapshot') | {'identity': subvolume(target)})
                save(plan, report)
            check_snapshots(report)
        finally:
            restore(plan, report)
        report['complete'] = True
        report['state'] = 'complete'
        save(plan, report)
        return report | {'changed': True}


def interrupted(signum, frame):
    raise RuntimeError(f'Snapshot interrupted by signal {signum}; retained journal requires inspection')


if __name__ == '__main__':
    try:
        if os.geteuid() != 0:
            raise ValueError('Run through the operator snapshot workflow with root privileges')
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(signum, interrupted)
        if len(sys.argv) == 4 and sys.argv[3] == 'recover-auto':
            automatic_recovery(sys.argv[1], sys.argv[2])
        else:
            result = snapshot(*sys.argv[1:])
            print(json.dumps(result))
    except Exception as error:
        sys.exit(f'Snapshot failed: {error}; use status/recover on the same host and identifier; never delete source storage')
