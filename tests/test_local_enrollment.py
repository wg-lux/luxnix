"""Controller escrow ordering with real Ansible encryption and a fake host (class unit)."""

import json
import secrets
import subprocess
import sys
from types import SimpleNamespace

import pytest

from lx_administration.models.vault import secret
from lx_administration.storage import local_enrollment as le
from lx_administration.storage import openbao_enroll

LOCAL = {"enable": True, "sealKeyId": "local-v1"}
MATERIAL = {"recovery_key": "cmVjb3Zlcnk=",
            "provisioner": {"role_id": "r", "secret_id": "s", "accessor": "a"}}


@pytest.fixture
def custody(tmp_path, monkeypatch):
    monkeypatch.setattr(secret, "encrypted_storage", lambda *a, **k: None)
    key = tmp_path / "admin-vault-key"
    key.write_bytes(secrets.token_bytes(32).hex().encode())
    key.chmod(0o600)
    return tmp_path / "vault", key


class FakeHost:
    """Answers luxnix-openbao-local like an unenrolled host and records phases."""

    def __init__(self, events, enrolled=False, fail_confirm=False):
        self.events = events
        self.enrolled = enrolled
        self.seal_keys = []
        self.fail_confirm = fail_confirm

    def call(self, args, data=b"", privileged=False, relay_error=False):
        command = args[1]
        self.events.append(("host", command))
        request = json.loads(data) if data else {}
        if command in {"status", "preflight"}:
            return json.dumps({"host": "gc-10", "enrolled": self.enrolled,
                               "initialized": False}).encode()
        if command == "seal":
            self.seal_keys.append(request["seal_key"])
            return b'{"sealed": true}'
        if command == "initialize":
            return json.dumps({"escrow": MATERIAL}).encode()
        if command == "confirm":
            assert request["escrow_sha256"] == openbao_enroll.escrow_digest(MATERIAL)
            return b'{"confirmed": true}'
        raise AssertionError(command)


class FakeRecovery:
    def __init__(self, events, broken=False):
        self.events = events
        self.broken = broken
        self.stored = {}

    def call(self, args, data=b"", privileged=False):
        item = args[-1]
        self.events.append(("export", item))
        assert data.startswith(b"$ANSIBLE_VAULT;1.2;AES256;luxnix-master\n")
        self.stored[item] = data
        return data[:-1] if self.broken else data


def controller(custody, host, recovery):
    vault, key = custody
    return le.Controller("gc-10", host, recovery, vault, key, "1" * 32, LOCAL)


def test_escrow_precedes_every_dependent_phase(custody):
    events = []
    host, recovery = FakeHost(events), FakeRecovery(events)
    assert controller(custody, host, recovery).enroll()["escrow_verified"]
    order = [e for e in events if e[1] != "preflight"]
    assert order == [("export", "seal-key"), ("host", "seal"), ("host", "initialize"),
                     ("export", "enrollment"), ("host", "confirm")]
    vault, key = custody
    seal = le.load_escrow(vault, key, "gc-10", "seal-key")
    assert seal["seal_key"] == host.seal_keys[0] and seal["machine_id"] == "1" * 32
    assert le.load_escrow(vault, key, "gc-10", "enrollment")["provisioner"] == MATERIAL["provisioner"]
    # Only ciphertext left the controller.
    for data in recovery.stored.values():
        assert host.seal_keys[0].encode() not in data and b"cmVjb3Zlcnk" not in data


def test_rerun_reuses_escrowed_seal_key(custody):
    events = []
    host = FakeHost(events)
    controller(custody, host, FakeRecovery(events)).enroll()
    controller(custody, host, FakeRecovery(events)).enroll()
    assert len(set(host.seal_keys)) == 1


def test_passphrase_reenrollment_restages_without_reinitializing(custody):
    events = []
    host = FakeHost(events)
    task = controller(custody, host, FakeRecovery(events))
    task.local = dict(LOCAL, seal="passphrase")
    task.ask_passphrase = lambda _: "disposable boot passphrase"
    task.enroll()
    host.enrolled = True
    events.clear()
    task.enroll()
    assert [event for event in events if event[0] == "host"] == [("host", "preflight"), ("host", "seal")]
    assert len(set(host.seal_keys)) == 1


def test_missing_selected_seal_blocks_before_escrow_or_mutation(custody, monkeypatch):
    events = []
    task = controller(custody, FakeHost(events), FakeRecovery(events))
    monkeypatch.setattr(task, "tool", lambda _: {"initialized": True, "seal_credential": False, "enrolled": False})
    with pytest.raises(le.EnrollmentError, match="selected seal"):
        task.enroll()
    assert not events
    assert not custody[0].exists()


def test_failed_export_blocks_seal_and_confirm(custody):
    events = []
    with pytest.raises(le.EnrollmentError, match="export"):
        controller(custody, FakeHost(events), FakeRecovery(events, broken=True)).enroll()
    assert ("host", "seal") not in events and ("host", "confirm") not in events


def test_enrolled_host_without_escrow_is_not_reenrolled(custody):
    events = []
    with pytest.raises(le.EnrollmentError, match="no enrollment escrow"):
        controller(custody, FakeHost(events, enrolled=True), FakeRecovery(events)).enroll()
    assert [e for e in events if e[0] == "host"] == [("host", "preflight")]


def test_conflicting_escrow_is_never_replaced(custody):
    vault, key = custody
    record = {"schema_version": 1, "host": "gc-10", "item": "seal-key", "seal_key": "a"}
    le.escrow(vault, key, record, lambda d: d)
    with pytest.raises(le.EnrollmentError, match="conflicts"):
        le.escrow(vault, key, dict(record, seal_key="b"), lambda d: d)
    assert le.load_escrow(vault, key, "gc-10", "seal-key")["seal_key"] == "a"


def test_emergency_publisher_repeats_but_never_overwrites(custody, tmp_path):
    vault, key = custody
    ciphertext = secret._encrypt_bytes(b"{}", key, secret.MASTER_VAULT_ID)
    home = tmp_path / "separate-host"
    home.mkdir()
    program = le.LOCAL_EXPORT.replace("Path.home()", "Path(" + repr(str(home)) + ")")
    command = [sys.executable, "-c", program, "gc-10", "seal-key"]
    for _ in range(3):
        result = subprocess.run(command, input=ciphertext, capture_output=True)
        assert result.returncode == 0 and result.stdout == ciphertext
    target = home / ".luxnix-recovery/openbao-local/gc-10/seal-key.vault"
    assert target.stat().st_mode & 0o777 == 0o600
    changed = secret._encrypt_bytes(b"[]", key, secret.MASTER_VAULT_ID)
    assert subprocess.run(command, input=changed, capture_output=True).returncode != 0
    assert subprocess.run(command, input=b"plaintext", capture_output=True).returncode != 0
    bad_item = [sys.executable, "-c", program, "gc-10", "../escape"]
    assert subprocess.run(bad_item, input=ciphertext, capture_output=True).returncode != 0
    assert target.read_bytes() == ciphertext


def test_limit_selects_only_fleet_hosts():
    host = lambda name, groups: SimpleNamespace(hostname=name, ansible_group_names=groups)
    inventory = SimpleNamespace(
        all=[host("gc-10", [le.FLEET_GROUP, "gpu"]), host("gs-02", [le.FLEET_GROUP]),
             host("other", ["gpu"])],
        get_hostnames=lambda: ["gc-10", "gs-02", "other"],
        group_name_exists=lambda name: name in {le.FLEET_GROUP, "gpu"},
    )
    assert le.select_hosts(inventory, le.FLEET_GROUP) == ["gc-10", "gs-02"]
    assert le.select_hosts(inventory, "gc-10") == ["gc-10"]
    for limit in ("gpu", "other", "missing"):
        with pytest.raises(le.EnrollmentError):
            le.select_hosts(inventory, limit)


def test_rollout_orders_provision_adoption_and_explicit_cutover(custody, monkeypatch):
    events = []
    class Target:
        def call(self, args, data=b'', **kwargs):
            if args[:2] == ['systemctl', 'show']:
                return b'loaded\n'
            if args[0] == 'sh':
                return b'present' if args[-1].endswith('old.luks') else b''
            events.append(tuple(args))
            return b''
    task = controller(custody, Target(), FakeRecovery(events))
    monkeypatch.setattr(task, 'tool', lambda *a, **k: {'enrolled': False})
    monkeypatch.setattr(task, 'enroll', lambda: events.append('enroll'))
    monkeypatch.setattr(task, 'adopt', lambda name, *a, **k: events.append(('adopt', name, k['open_mapping'])))
    volumes = {name: {'container': '/private/' + name + '.luks', 'luksUUID': '1' * 36}
               for name in ('new', 'old')}
    plan = task.rollout(volumes, None, migration_enabled=True)
    assert [p['action'] for p in plan['volumes']] == ['provision', 'adopt']
    assert events == []
    task.rollout(volumes, lambda name: events.append(('provision', name)), apply=True, cutover=True, migration_enabled=True)
    assert events == ['enroll', ('provision', 'new'), ('adopt', 'old', True),
                      ('systemctl', 'start', 'luxnix-storage-precopy.service'),
                      ('systemctl', 'start', 'luxnix-storage-cutover.service')]


def test_rollout_failure_never_starts_precopy_or_stops_writers(custody, monkeypatch):
    calls = []
    target = SimpleNamespace(call=lambda args, **kw: calls.append(args) or
                             (b'loaded\n' if args[:2] == ['systemctl', 'show'] else b''))
    task = controller(custody, target, None)
    monkeypatch.setattr(task, 'tool', lambda *a, **k: {'enrolled': True})
    monkeypatch.setattr(task, 'enroll', lambda: None)
    def fail(name):
        raise le.EnrollmentError('independent export unavailable')
    with pytest.raises(le.EnrollmentError, match='export'):
        task.rollout({'data': {'container': '/private/data.luks', 'luksUUID': '1' * 36}}, fail, apply=True, cutover=True, migration_enabled=True)
    assert not any(c[:2] == ['systemctl', 'start'] for c in calls)


@pytest.mark.parametrize('missing', ['luxnix-storage-precopy.service', 'luxnix-storage-cutover.service'])
@pytest.mark.parametrize('apply', [False, True])
def test_rollout_missing_deployed_unit_blocks_before_mutations(custody, monkeypatch, missing, apply):
    calls = []
    def call(args, **kwargs):
        calls.append(args)
        return b'not-found\n' if args[-1] == missing else b'loaded\n'
    task = controller(custody, SimpleNamespace(call=call), None)
    monkeypatch.setattr(task, 'tool', lambda *a, **k: pytest.fail('enrollment preflight reached'))
    monkeypatch.setattr(task, 'enroll', lambda: pytest.fail('enrollment reached'))
    with pytest.raises(le.EnrollmentError, match=missing):
        task.rollout({}, lambda name: pytest.fail('provision reached'), apply=apply, migration_enabled=True)
    assert all(c[:2] == ['systemctl', 'show'] for c in calls)


def test_rollout_disabled_configuration_blocks_before_remote_calls(custody):
    task = controller(custody, SimpleNamespace(call=lambda *a, **k: pytest.fail('remote call reached')), None)
    with pytest.raises(le.EnrollmentError, match='migration enabled'):
        task.rollout({}, None, migration_enabled=False)


class RecordingHost(FakeHost):
    def __init__(self, events):
        super().__init__(events)
        self.requests = []

    def call(self, args, data=b"", privileged=False, relay_error=False):
        if args[1] == "seal":
            self.requests.append(json.loads(data))
        return super().call(args, data, privileged, relay_error)


@pytest.mark.parametrize("seal, expected", [("passphrase", True), ("tpm", False)])
def test_boot_passphrase_is_sent_only_for_passphrase_seal_and_never_escrowed(custody, seal, expected):
    events = []
    host, recovery = RecordingHost(events), FakeRecovery(events)
    vault, key = custody
    instance = le.Controller("gc-10", host, recovery, vault, key, "1" * 32, dict(LOCAL, seal=seal))
    instance.ask_passphrase = lambda name: "correct horse battery"
    instance.enroll()
    assert ("seal_passphrase" in host.requests[0]) is expected
    for item in ("seal-key", "enrollment"):
        assert "correct horse battery" not in json.dumps(le.load_escrow(vault, key, "gc-10", item))
