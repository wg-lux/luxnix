"""Real local supervisor processes prove sudo never consumes operation payloads."""
import os
import sys

import pytest

from lx_administration.storage import provision


@pytest.fixture
def target(tmp_path, monkeypatch):
    fake = tmp_path / 'sudo'
    fake.write_text(f'''#!{sys.executable}
import os, sys
from pathlib import Path
args = sys.argv[1:]
if args == ['-n', 'true']:
    sys.exit(1)
if '-S' in args:
    data = sys.stdin.buffer.read()
    Path(os.environ['AUTH_CAPTURE']).write_bytes(data)
    if data != b'correct-password\\n':
        sys.exit(1)
start = args.index('python3')
os.execvp(args[start], args[start:])
''')
    fake.chmod(0o700)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('AUTH_CAPTURE', str(tmp_path / 'auth'))
    monkeypatch.setattr(provision.socket, 'gethostname', lambda: 'test-host')
    monkeypatch.setattr(provision, 'encrypted_storage', lambda *a, **k: None)
    password = tmp_path / 'password'
    password.write_bytes(b'correct-password\n')
    password.chmod(0o600)
    return provision.Local('test-host', password), tmp_path


def test_wrong_password_receives_one_line_and_no_payload(target):
    remote, root = target
    remote.password_file.write_bytes(b'wrong-password\n')
    marker = root / 'command-ran'
    with pytest.raises(provision.ProvisionError, match='no operation payload was sent'):
        remote.call([sys.executable, '-c', f'open({str(marker)!r}, "w").write("ran")'],
                    b'secret recovery passphrase\nrequest JSON', privileged=True)
    assert (root / 'auth').read_bytes() == b'wrong-password\n'
    assert not marker.exists()


@pytest.mark.parametrize('password_required', [False, True])
def test_separate_authenticated_binary_payload_without_timestamp_cache(target, password_required):
    remote, root = target
    remote.password_required = password_required
    payload = bytes(range(256)) * 4096
    command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())']
    for _ in range(2):
        assert remote.call(command, payload, privileged=True) == payload
    if password_required:
        assert (root / 'auth').read_bytes() == b'correct-password\n'
    else:
        assert not (root / 'auth').exists()


def test_stream_api_is_ready_before_caller_sends_payload(target):
    remote, root = target
    process = remote.open_stream([sys.executable, '-c', 'import sys; print(len(sys.stdin.buffer.read()))'])
    assert (root / 'auth').read_bytes() == b'correct-password\n'
    stdout, _ = process.communicate(b'payload', timeout=5)
    assert process.returncode == 0 and stdout.strip() == b'7'


def test_multiline_password_refused_before_sudo(target):
    remote, root = target
    remote.password_file.write_bytes(b'password\nrequest')
    with pytest.raises(provision.ProvisionError, match='exactly one'):
        remote.call(['true'], b'payload', privileged=True)
    assert not (root / 'auth').exists()
