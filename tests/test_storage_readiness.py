"""Readiness admission rejects incomplete evidence without mutating hosts."""
import copy
import json
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
    assert 'admission' not in result and len(result['report_sha256']) == 64
    monkeypatch.setattr(sys, 'argv', ['readiness', '--expected-host', 'gc-09', '--mode', 'admit',
                                     '--expected-layout', 'legacy-containers', '--expected-serials', '["selected-serial"]'])
    assert readiness.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert not result['admission']['admitted']
    assert any(r['code'] == 'swap_active' for r in result['admission']['reasons'])


def test_playbook_uses_controller_collector_without_installing_files():
    play = yaml.safe_load(Path('ansible/playbooks/storage-readiness.yml').read_text())[0]
    task = next(t for t in play['tasks'] if 'ansible.builtin.command' in t)
    assert 'storage/readiness.py' in task['ansible.builtin.command']['stdin']
    assert task['changed_when'] is False
    assert any('ansible_play_hosts_all' in str(t) for t in play['tasks'])
    assert any('storage_readiness.rc == 0' in str(t) for t in play['tasks'])
