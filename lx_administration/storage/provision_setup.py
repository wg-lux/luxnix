"""Interactive, resumable guide through the `storage-provision provision` gate.

The guide asks for every choice, runs read-only prerequisite checks, shows the
preview produced by the real provisioning controller and only then, after the
operator types the host name, invokes the same controller with --apply. It
never formats, deletes or bypasses a guard: provision.py and the deployed
luxnix-storage-provision helper remain authoritative.

Re-running is safe. Non-secret answers are remembered per host and volume, and
the controller reuses existing escrow and provisioning receipts instead of
repeating work.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile

IDENTIFIER = re.compile('[a-z0-9][a-z0-9-]*')
BACKENDS = ('passphrase',)
BACKEND_HELP = {
    'passphrase': 'unlock with the escrowed passphrase (no Secure Boot needed)',
    'tpm2': 'TPM token; the host must already boot with Secure Boot',
    'local-openbao': 'host-local OpenBao key; needs Secure Boot and OpenBao enrollment',
}
STORAGE_EXPRESSION = (
    'c: { layout = c.layout; unlockMethod = c.unlockMethod; '
    'volumes = builtins.mapAttrs (n: v: { container = v.container; '
    'luksUUID = v.luksUUID; }) c.volumes; }'
)
CONTROLLER = [sys.executable, '-m', 'lx_administration.storage.provision']
DOCUMENTATION = 'docs/legacy-storage-recovery.md'


class SetupStopped(RuntimeError):
    """A plain-language reason to stop; nothing further is changed."""


@dataclass
class Choices:
    host: str
    volume: str = ''
    recovery_host: str = ''
    backend: str = ''
    local_target: bool = False
    sudo_password_file: str | None = None
    apply_started: bool = False
    completed: dict = field(default_factory=dict)

    def controller_args(self, apply=False):
        argv = ['provision', '--host', self.host, '--volume', self.volume,
                '--recovery-host', self.recovery_host, '--backend', self.backend]
        if self.local_target:
            argv.append('--local-target')
        if self.sudo_password_file:
            argv += ['--sudo-password-file', self.sudo_password_file]
        return argv + (['--apply'] if apply else [])


class Console:
    """Plain-language terminal prompts; injectable for tests."""

    def __init__(self, read=input, write=print):
        self.read = read
        self.write = write

    def say(self, text=''):
        self.write(text)

    def step(self, number, title):
        self.write(f'\n== Step {number}: {title}')

    def ok(self, text):
        self.write(f'  [ OK ] {text}')

    def warn(self, text):
        self.write(f'  [NOTE] {text}')

    def ask(self, question, default=None):
        suffix = f' [{default}]' if default else ''
        while True:
            answer = self.read(f'  {question}{suffix}: ').strip()
            if answer or default:
                return answer or default

    def yes(self, question, default=False):
        hint = 'Y/n' if default else 'y/N'
        while True:
            answer = self.read(f'  {question} ({hint}): ').strip().lower()
            if not answer:
                return default
            if answer in ('y', 'yes'):
                return True
            if answer in ('n', 'no'):
                return False
            self.write('  Please answer yes or no.')

    def choose(self, question, options, default=None, notes=None):
        if not options:
            raise SetupStopped(f'There is nothing to choose for: {question}')
        if len(options) == 1:
            self.ok(f'{question}: {options[0]} (only option)')
            return options[0]
        self.write(f'  {question}')
        for index, option in enumerate(options, 1):
            note = f' - {notes[option]}' if notes and option in notes else ''
            mark = ' (recommended)' if option == default else ''
            self.write(f'    {index}) {option}{mark}{note}')
        while True:
            answer = self.ask('Enter a number or name', default)
            if answer in options:
                return answer
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return options[int(answer) - 1]
            self.write('  That is not one of the listed options.')


class Environment:
    """Read-only facts and the controller invocation; injectable for tests."""

    def nix_json(self, attribute, apply=None):
        command = ['nix', 'eval', '--json', f'.#{attribute}']
        if apply:
            command += ['--apply', apply]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise SetupStopped(f'Nix could not evaluate {attribute}; run the command manually to see why')
        return json.loads(result.stdout)

    def inventory_hosts(self):
        from lx_administration.autoconf import AutoconfConfig, DEFAULT_CONFIG_PATH
        from lx_administration.models.ansible.inventory import AnsibleInventory
        config = AutoconfConfig.load(DEFAULT_CONFIG_PATH)
        inventory = AnsibleInventory.load_from_hosts_ini(
            config.ansible_root / 'inventory/hosts.ini', config.inventory_subnet)
        return {host.hostname: str(host.ansible_host) for host in inventory.all}

    def hostname(self):
        return socket.gethostname()

    def connectivity(self, host):
        result = subprocess.run(['bash', 'scripts/check-connectivity.sh', host],
                                capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip().splitlines()[-5:]

    def sudo_ready(self, choices, address):
        from lx_administration.storage.provision import Local, ProvisionError, Remote
        password = Path(choices.sudo_password_file) if choices.sudo_password_file else None
        target = Local(choices.host, password) if choices.local_target else Remote(address, password)
        try:
            target.call(['true'], privileged=True)
        except (ProvisionError, OSError, ValueError, subprocess.SubprocessError) as exc:
            return str(exc) if isinstance(exc, ProvisionError) else 'sudo check failed'
        return None

    def refresh_local_sudo(self):
        return subprocess.run(['sudo', '-v']).returncode == 0

    def admin_vault_problem(self, vault_dir, vault_key, host, backend):
        from lx_administration.models.vault import Vault
        from lx_administration.secret_storage import encrypted_storage
        if not vault_dir.is_dir() or not vault_key.is_file():
            return f'The admin vault ({vault_dir}) or its key ({vault_key}) is missing'
        try:
            encrypted_storage(vault_key, allow_runtime=True)
        except (OSError, ValueError, subprocess.SubprocessError):
            return 'The admin vault key is not on verified encrypted storage'
        try:
            Vault.load_dir(str(vault_dir), str(vault_key)).validate_local_key()
        except Exception:  # noqa: BLE001 - report without secret-bearing detail
            return 'The admin vault could not be opened with its key'
        if backend == 'local-openbao':
            from lx_administration.storage.local_enrollment import load_escrow
            try:
                if load_escrow(vault_dir, vault_key, host, 'enrollment') is None:
                    return 'Local OpenBao enrollment escrow is missing; run devenv shell openbao-local enroll first'
            except Exception:  # noqa: BLE001
                return 'Local OpenBao enrollment escrow could not be authenticated'
        return None

    def controller(self, argv):
        # stderr is inherited: the controller prints only credential-free diagnostics.
        result = subprocess.run(CONTROLLER + argv, stdout=subprocess.PIPE, text=True)
        if result.returncode:
            return None
        lines = result.stdout.strip().splitlines()
        return json.loads(lines[-1]) if lines else None


class State:
    """Private, non-secret answers per host and volume, plus an exclusive run lock."""

    def __init__(self, root):
        self.root = Path(root)

    def _prepare(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid != os.geteuid():
            raise SetupStopped(f'Refusing to use state directory {self.root}')
        self.root.chmod(0o700)

    def path(self, host, volume):
        return self.root / f'{host}--{volume}.json'

    def load(self, host, volume):
        target = self.path(host, volume)
        if not target.is_file() or target.is_symlink():
            return None
        data = json.loads(target.read_text())
        if data.get('host') != host or data.get('volume') != volume:
            raise SetupStopped(f'Saved answers in {target} do not match; inspect the file')
        return Choices(**data)

    def save(self, choices):
        self._prepare()
        target = self.path(choices.host, choices.volume)
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix='.answers-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(asdict(choices), stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def lock(self, host, volume):
        self._prepare()
        stream = (self.root / f'{host}--{volume}.lock').open('a')
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            stream.close()
            raise SetupStopped('Another setup for this host and volume is already running') from None
        return stream


def default_state_root():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'luxnix/storage-provision-setup'


def _identifier(value, label):
    if not IDENTIFIER.fullmatch(value or ''):
        raise SetupStopped(f'{label} must be a canonical inventory name')
    return value


def run(console, env, state, preset, vault_dir, vault_key):
    console.say('LuxNix encrypted storage setup. Nothing changes until you confirm at the end.')
    console.say('You can stop at any time with Ctrl-C and run this setup again later.')

    console.step(1, 'Choose the host')
    inventory = env.inventory_hosts()
    configured = set(env.nix_json('nixosConfigurations', 'builtins.attrNames'))
    hosts = sorted(set(inventory) & configured & {'gc-09', 'gc-10'})
    host = _identifier(preset.host or console.choose('Which host gets encrypted storage?', hosts), 'Host')
    if host not in hosts:
        raise SetupStopped(f'{host} is not both in the inventory and in the flake')
    storage = env.nix_json(f'nixosConfigurations.{host}.config.luxnix.storage.operatorUnlocked',
                           STORAGE_EXPRESSION)
    if storage['layout'] != 'legacy-containers':
        raise SetupStopped(f'{host} uses the {storage["layout"]} layout; its storage is prepared with '
                           'devenv shell boot-storage-migration (docs/boot-storage-migration.md)')
    console.ok(f'{host} uses protected containers with the {storage["unlockMethod"]} unlock policy')

    console.step(2, 'Choose the volume')
    volumes = sorted(name for name, value in storage['volumes'].items() if value['container'])
    volume = _identifier(preset.volume or console.choose('Which declared volume?', volumes), 'Volume')
    if volume not in volumes:
        raise SetupStopped(f'{volume} is not a declared container volume on {host}')
    container = storage['volumes'][volume]['container']
    console.ok(f'Volume {volume} lives in {container}')

    lock = state.lock(host, volume)
    try:
        saved = state.load(host, volume)
        if saved and console.yes('Answers from an earlier run were found. Reuse them?', True):
            choices = saved
            console.ok('Reusing earlier answers; every check still runs again')
        else:
            choices = Choices(host=host, volume=volume,
                              apply_started=bool(saved and saved.apply_started),
                              completed=saved.completed if saved else {})
            _ask_choices(console, env, preset, choices, storage['unlockMethod'], inventory)
        state.save(choices)
        return _check_and_apply(console, env, state, choices, inventory, container, vault_dir, vault_key)
    finally:
        lock.close()


def _ask_choices(console, env, preset, choices, configured_method, inventory):
    console.step(3, 'Choose how the volume is unlocked')
    allowed = [b for b in BACKENDS if b != 'passphrase' or configured_method == 'passphrase']
    choices.backend = preset.backend or console.choose(
        'Which unlock backend?', allowed, configured_method, BACKEND_HELP)
    if choices.backend not in allowed:
        raise SetupStopped(f'{choices.backend} is not allowed under the {configured_method} policy')

    local = env.hostname()
    choices.local_target = local == choices.host
    if choices.local_target:
        console.ok(f'You are on {local}; commands run locally on this machine')

    console.step(4, 'Choose the independent recovery host')
    console.say('  A second, encrypted copy of the recovery key is stored on a different machine.')
    candidates = sorted(h for h in inventory if h not in (choices.host, local))
    choices.recovery_host = _identifier(
        preset.recovery_host or console.choose('Which host keeps the recovery copy?', candidates),
        'Recovery host')
    if choices.recovery_host not in candidates:
        raise SetupStopped('The recovery host must be another inventory host than the target and this machine')
    choices.sudo_password_file = preset.sudo_password_file


def _check_and_apply(console, env, state, choices, inventory, container, vault_dir, vault_key):
    console.step(5, 'Check connections')
    remote = [h for h in (choices.host, choices.recovery_host)
              if not (h == choices.host and choices.local_target)]
    for host in remote:
        reachable, tail = env.connectivity(host)
        if not reachable:
            for line in tail:
                console.say(f'      {line}')
            raise SetupStopped(f'{host} is not reachable over SSH; run devenv shell check-connectivity {host}')
        console.ok(f'{host} is reachable')

    console.step(6, 'Check administrator rights on the target')
    if choices.local_target and env.sudo_ready(choices, None):
        console.say('  Please enter your sudo password when asked.')
        env.refresh_local_sudo()
    problem = env.sudo_ready(choices, inventory[choices.host])
    if problem and 'sudo-password file' in problem and not choices.local_target:
        console.say('  The target asks for a sudo password. Give the path of a private file')
        console.say('  (mode 600, on encrypted or runtime storage) that contains it.')
        choices.sudo_password_file = console.ask('Sudo password file')
        state.save(choices)
        problem = env.sudo_ready(choices, inventory[choices.host])
    if problem:
        raise SetupStopped(f'Administrator rights on {choices.host} could not be confirmed: {problem}')
    console.ok(f'Administrator rights on {choices.host} are available')

    console.step(7, 'Check the admin vault on this machine')
    problem = env.admin_vault_problem(vault_dir, vault_key, choices.host, choices.backend)
    if problem:
        raise SetupStopped(problem)
    console.ok('The admin vault opens and is stored on encrypted storage')

    console.step(8, 'Preview (read-only)')
    preview = env.controller(choices.controller_args())
    if preview is None:
        raise SetupStopped('The provisioning preview was refused; see the ERROR line above')
    expected = {'host': choices.host, 'volume': choices.volume, 'container': container,
                'recovery_host': choices.recovery_host, 'backend': choices.backend,
                'action': 'provision'}
    if any(preview.get(key) != value for key, value in expected.items()):
        raise SetupStopped('The preview does not match your choices; nothing was changed')
    for label, value in (('Host', choices.host), ('Machine ID', preview['machine_id']),
                         ('Volume', choices.volume), ('Container', container),
                         ('Already exists', 'yes' if preview['exists'] else 'no'),
                         ('Unlock backend', choices.backend),
                         ('Recovery copy on', choices.recovery_host)):
        console.say(f'    {label:<17} {value}')

    done = choices.completed.get('luks_uuid')
    if preview['exists'] and done and done == preview.get('luks_uuid'):
        console.ok('This volume was provisioned by an earlier run; continuing only re-verifies it')
    elif preview['exists'] and not choices.apply_started:
        console.warn('A container file already exists and this setup has no record of creating it.')
        console.say('  Its data is protected: provisioning only resumes an earlier run for the same')
        console.say('  volume and never reformats. For an existing volume with data, record its')
        console.say(f'  recovery key with "devenv shell storage-provision escrow" ({DOCUMENTATION}).')
        if not console.yes('Did you start provisioning this exact volume earlier?', False):
            raise SetupStopped('Stopped to protect the existing container; nothing was changed')

    console.say('\n  If you continue, the tool will:')
    console.say('    - store the recovery key in your admin vault and an encrypted copy on '
                f'{choices.recovery_host}, and verify both;')
    console.say(f'    - create or resume the encrypted container {container} on {choices.host};')
    console.say('    - leave the volume unlocked for the later copy. It never reboots or deletes data.')
    console.say(f'  Equivalent command: devenv shell storage-provision {shlex.join(choices.controller_args())} --apply')
    if console.read(f'  Type the host name "{choices.host}" to continue, anything else stops: ').strip() != choices.host:
        raise SetupStopped('Not confirmed; nothing was changed')

    console.step(9, 'Provision')
    if choices.local_target:
        env.refresh_local_sudo()
    choices.apply_started = True
    state.save(choices)
    try:
        result = env.controller(choices.controller_args(apply=True))
    except (KeyboardInterrupt, EOFError) as exc:
        raise SetupStopped('Apply was interrupted and may have created recovery copies or part of the container. '
                           'Saved progress is retained. Run this setup again to verify and resume; '
                           'do not delete state or create replacement keys.') from exc
    if result is None or not result.get('escrow_verified'):
        raise SetupStopped('Provisioning stopped; see the ERROR line above. Nothing was deleted. '
                           'Fix the cause and run this setup again; it resumes safely')
    choices.completed = {key: result.get(key) for key in ('luks_uuid', 'primary_escrow', 'emergency_export')}
    choices.completed['at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    state.save(choices)
    console.ok(f'{choices.volume} on {choices.host} is provisioned (LUKS UUID {result["luks_uuid"]})')
    console.say('\n  Next steps (see the documentation):')
    console.say(f'    - on {choices.host}: sudo luxnix-operator-storage status')
    console.say('    - provision any other missing volume the same way, then follow the cutover')
    console.say(f'      instructions in {DOCUMENTATION}.')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', help='preselect the target host')
    parser.add_argument('--volume', help='preselect the declared volume')
    parser.add_argument('--recovery-host', help='preselect the independent recovery host')
    parser.add_argument('--backend', choices=BACKENDS, help='preselect the unlock backend')
    parser.add_argument('--sudo-password-file', help='private file with the target sudo password')
    parser.add_argument('--vault-dir', type=Path, default=Path.home() / '.lxv')
    parser.add_argument('--vault-key', type=Path, default=Path.home() / '.lxv.key')
    parser.add_argument('--state-dir', type=Path, default=default_state_root())
    args = parser.parse_args(argv)
    console = Console()
    if not (Path('flake.nix').is_file() and Path('devenv/commands.yml').is_file()):
        console.say('STOPPED: run this from the LuxNix repository root (devenv shell storage-provision-setup).')
        return 1
    if not sys.stdin.isatty():
        console.say('STOPPED: this setup needs an interactive terminal; '
                    'automation must call devenv shell storage-provision directly.')
        return 1
    try:
        run(console, Environment(), State(args.state_dir), args, args.vault_dir, args.vault_key)
    except SetupStopped as exc:
        console.say(f'\nSTOPPED: {exc}')
        return 1
    except (KeyboardInterrupt, EOFError):
        console.say('\nSTOPPED by you. Earlier completed or interrupted operations may have changed state. '
                    'Run this setup again to verify and resume; do not delete recovery copies or saved progress.')
        return 130
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
