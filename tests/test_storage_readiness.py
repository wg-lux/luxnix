"""Readiness admission rejects incomplete evidence without mutating hosts."""
import copy
import json
import os
from pathlib import Path
import sys

import pytest
import yaml

from lx_administration.storage import readiness


def success(value=''):
    return {'exit': 0, 'output': json.dumps(value) if not isinstance(value, str) else value}


def baseline(layout='legacy-containers'):
    root = {'name': '/dev/mapper/cryptroot' if layout == 'boot-luks' else '/dev/sda1',
            'type': 'crypt' if layout == 'boot-luks' else 'part', 'uuid': 'root', 'fstype': 'btrfs'}
    devices = [{'name': '/dev/sda', 'type': 'disk', 'serial': 'selected-serial', 'children': [root]}]
    mounts = {'/': success({'filesystems': [{'target': '/', 'source': root['name'] + '[/root]', 'fstype': 'btrfs'}]})}
    for i, path in enumerate(readiness.LEGACY_MOUNTS):
        if layout == 'boot-luks':
            mounts[path] = {'exit': 1, 'output': ''}
        else:
            name = f'/dev/mapper/container{i}'
            devices.append({'name': name, 'type': 'crypt', 'uuid': f'fs-{i}'})
            mounts[path] = success({'filesystems': [{'target': path, 'source': name, 'fstype': 'ext4'}]})
    return {**{name: success() for name in readiness.CORE_PROBES}, 'host': 'gc-09',
            'boot_id': 'current-boot', 'privilege': success('0'), 'btrfs': success(),
            'generations': dict.fromkeys(readiness.GENERATIONS, '/nix/store/reviewed-system'),
            'mounts': mounts, 'block_devices': success({'blockdevices': devices}),
            'boot_storage': success()}


def admission(report, layout='legacy-containers', serials=None):
    return readiness.evaluate(report, 'gc-09', layout, ['selected-serial'] if serials is None else serials)


@pytest.mark.parametrize('layout', ['legacy-containers', 'unencrypted-root', 'boot-luks'])
def test_complete_baseline_is_explicitly_limited(layout):
    result = admission(baseline(layout), layout)
    assert result['admitted'] and result['scope'] == 'storage-baseline-only'
    assert 'not permission to erase' in result['notice']


@pytest.mark.parametrize('probe', readiness.CORE_PROBES)
@pytest.mark.parametrize('change', [None, {'exit': 1, 'output': ''}, {'exit': None}, {'exit': False, 'output': ''}])
def test_every_required_probe_fails_closed(probe, change):
    report = baseline()
    report[probe] = change
    assert not admission(report)['admitted']


@pytest.mark.parametrize('change', [
    {'host': 'gc-10'}, {'boot_id': None}, {'generations': {}},
    {'swap': success('/dev/sda2 partition')}, {'privilege': success('1000')},
    {'mounts': {}}, {'block_devices': success('{invalid')}, {'btrfs': {'exit': 1}},
])
def test_missing_or_unsafe_evidence_rejects(change):
    assert not admission(baseline() | change)['admitted']


@pytest.mark.parametrize('serials', [[], ['other'], ['selected-serial', 'other'], ['selected-serial'] * 2, [None], 'selected-serial'])
def test_operator_must_select_exact_unique_disk_serials(serials):
    assert not admission(baseline(), serials=serials)['admitted']


def test_new_disk_added_after_selection_is_rejected():
    report = baseline()
    data = json.loads(report['block_devices']['output'])
    data['blockdevices'].append({'name': '/dev/sdb', 'type': 'disk', 'serial': 'unreviewed'})
    report['block_devices'] = success(data)
    assert not admission(report)['admitted']


@pytest.mark.parametrize("layout", ["legacy-containers", "unencrypted-root"])
def test_unencrypted_legacy_mapping_rejected(layout):
    report = baseline(layout)
    data = json.loads(report['block_devices']['output'])
    data['blockdevices'][-1]['type'] = 'part'
    report['block_devices'] = success(data)
    assert not admission(report, layout)['admitted']


@pytest.mark.parametrize('mutation', ['missing_verifier', 'legacy_mount', 'plaintext_root', 'wrong_layout'])
def test_installed_layout_requires_actual_encryption_and_live_verifier(mutation):
    report = baseline('boot-luks')
    if mutation == 'missing_verifier':
        del report['boot_storage']
    elif mutation == 'legacy_mount':
        report['mounts'][readiness.LEGACY_MOUNTS[0]] = success()
    elif mutation == 'plaintext_root':
        data = json.loads(report['block_devices']['output'])
        data['blockdevices'][0]['children'][0]['type'] = 'part'
        report['block_devices'] = success(data)
    else:
        report = baseline()
    assert not admission(report, 'boot-luks')['admitted']


def test_no_input_mutation():
    report = baseline()
    before = copy.deepcopy(report)
    assert admission(report)['admitted']
    assert report == before


def test_cli_observation_does_not_claim_admission_but_admit_fails(monkeypatch, capsys):
    report = baseline() | {'swap': success('/dev/unsafe partition')}
    monkeypatch.setattr(readiness, 'collect', lambda _: copy.deepcopy(report))
    monkeypatch.setattr(sys, 'argv', ['readiness', '--expected-host', 'gc-09'])
    assert readiness.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['host_matches'] and not result['admitted']
    assert result['reasons'][0]['code'] == 'observation_only'
    monkeypatch.setattr(sys, 'argv', ['readiness', '--expected-host', 'gc-09', '--mode', 'admit',
                                     '--expected-layout', 'legacy-containers', '--expected-serials', '["selected-serial"]'])
    assert readiness.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert not result['admitted']
    assert any(r['code'] == 'swap_active' for r in result['reasons'])


def test_cli_prints_only_summary_until_private_transport_requested(monkeypatch, capsys):
    report = baseline() | {'capacity': success('private-capacity'),
                           'active_units': success('private-service')}
    monkeypatch.setattr(readiness, 'collect', lambda _: copy.deepcopy(report))
    arguments = ['readiness', '--expected-host', 'gc-09', '--mode', 'admit',
                 '--expected-layout', 'legacy-containers', '--expected-serials', '["selected-serial"]']
    monkeypatch.setattr(sys, 'argv', arguments)
    assert readiness.main() == 0
    output = capsys.readouterr().out
    assert json.loads(output)['admitted']
    for private in ('selected-serial', 'private-capacity', 'private-service', 'mounts', 'generations'):
        assert private not in output
    monkeypatch.setattr(sys, 'argv', arguments + ['--full-report'])
    assert readiness.main() == 0
    full = json.loads(capsys.readouterr().out)
    assert full['admission']['expected_serials'] == ['selected-serial']
    assert len(full['report_sha256']) == 64


@pytest.fixture
def controller_reports(tmp_path, monkeypatch):
    # save_report is deliberately anchored to this tool's controller checkout.
    monkeypatch.setattr(readiness, '__file__', str(tmp_path / 'lx_administration/storage/readiness.py'))
    (tmp_path / 'cmdb').mkdir()
    return tmp_path / 'cmdb/storage-readiness'


def test_full_report_is_atomic_private_local_artifact(controller_reports):
    report = baseline()
    readiness.save_report(report, 'gc-09')
    artifact = controller_reports / 'gc-09.json'
    assert json.loads(artifact.read_text()) == report
    assert controller_reports.stat().st_mode & 0o777 == 0o700
    assert artifact.stat().st_mode & 0o777 == 0o600
    readiness.save_report(report | {'boot_id': 'next-boot'}, 'gc-09')
    assert json.loads(artifact.read_text())['boot_id'] == 'next-boot'
    assert list(controller_reports.iterdir()) == [artifact]


@pytest.mark.parametrize('unsafe', ['parent_symlink', 'directory_symlink', 'directory_public',
                                    'file_symlink', 'file_public', 'file_directory', 'foreign_owner'])
def test_private_report_rejects_unsafe_existing_paths(controller_reports, tmp_path, monkeypatch, unsafe):
    root = controller_reports.parent
    victim = tmp_path / 'victim'
    victim.write_text('preserve')
    if unsafe == 'parent_symlink':
        root.rmdir()
        external = tmp_path / 'external'
        external.mkdir()
        root.symlink_to(external, target_is_directory=True)
    elif unsafe == 'directory_symlink':
        controller_reports.symlink_to(tmp_path, target_is_directory=True)
    else:
        controller_reports.mkdir(mode=0o700)
        target = controller_reports / 'gc-09.json'
        if unsafe == 'directory_public':
            controller_reports.chmod(0o755)
        elif unsafe == 'file_symlink':
            target.symlink_to(victim)
        elif unsafe == 'file_directory':
            target.mkdir()
        elif unsafe == 'foreign_owner':
            monkeypatch.setattr(os, 'geteuid', lambda: -1)
        else:
            target.write_text('preserve')
            target.chmod(0o644)
    with pytest.raises((ValueError, OSError)):
        readiness.save_report(baseline(), 'gc-09')
    assert victim.read_text() == 'preserve'


@pytest.mark.parametrize('host', ['../other', '/other', 'gc-10', ''])
def test_private_report_rejects_mismatched_or_unsafe_host(controller_reports, host):
    with pytest.raises(ValueError, match='host identity'):
        readiness.save_report(baseline(), host)
    assert not controller_reports.exists()


def test_playbook_uses_controller_collector_without_installing_files():
    play = yaml.safe_load(Path('ansible/playbooks/storage-readiness.yml').read_text())[0]
    task = next(t for t in play['tasks'] if 'ansible.builtin.command' in t)
    assert 'storage/readiness.py' in task['ansible.builtin.command']['stdin']
    assert task['changed_when'] is False
    assert task['no_log'] is True
    assert '--full-report' in task['ansible.builtin.command']['argv']
    debug = next(t for t in play['tasks'] if 'ansible.builtin.debug' in t)
    assert 'storage_readiness_reasons' in debug['ansible.builtin.debug']['msg']
    assert 'storage_readiness.stdout' not in debug['ansible.builtin.debug']['msg']
    extract = next(t for t in play['tasks'] if 'ansible.builtin.set_fact' in t)
    assert '.reasons' in extract['ansible.builtin.set_fact']['storage_readiness_reasons']
    assert extract['no_log'] is True
    save = next(t for t in play['tasks'] if t.get('delegate_to') == 'localhost')
    assert save['no_log'] is True and save['become'] is False
    assert '--save-report' in save['ansible.builtin.command']['argv']
    assert 'storage_readiness_save_report' in str(save['when'])
    assert play['tasks'][-1]['no_log'] is True
    assert any('ansible_play_hosts_all' in str(t) for t in play['tasks'])
    assert any('storage_readiness.rc == 0' in str(t) for t in play['tasks'])
