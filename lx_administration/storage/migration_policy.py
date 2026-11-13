"""Canonical migration scope; JSON-compatible YAML also loads on stdlib-only hosts."""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
from pathlib import Path
import re


# Read-only stdin transports embed this exact canonical text; file execution reads
# the adjacent policy. Neither path invents an implicit scope when policy is absent.
POLICY_TEXT = None


def load_policy(path=None):
    text = POLICY_TEXT if path is None and POLICY_TEXT is not None else (
        Path(path) if path else Path(__file__).with_name('migration-policy.yml')).read_text()
    policy = json.loads(text)
    if policy.get('schema_version') != 1 or not policy.get('hosts') or not policy.get('writer_patterns'):
        raise ValueError('Missing or invalid storage migration policy')
    for host, sources in policy['hosts'].items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', host) or not sources or len(set(sources.values())) != len(sources):
            raise ValueError('Invalid migration host coverage')
        for name, source in sources.items():
            if source != '/' and (not source.startswith('/') or str(Path(source)) != source or '..' in Path(source).parts):
                raise ValueError('Invalid migration source path')
            if name != ('root' if source == '/' else source.strip('/').replace('/', '-')):
                raise ValueError('Invalid migration component name')
    return policy


def supported_hosts():
    return tuple(load_policy()['hosts'])


def snapshot_sources(host):
    try:
        return load_policy()['hosts'][host]
    except KeyError as error:
        raise ValueError('Host has no reviewed migration coverage') from error


def inner_mounts():
    return tuple(load_policy()['inner_mounts'])


def writer(unit):
    name, separator, suffix = unit.rpartition('.')
    return separator != '' and suffix in {'service', 'timer'} and any(
        fnmatchcase(name, pattern) for pattern in load_policy()['writer_patterns'])


def snapshot_parent(source, identifier, base="/var/lib/luxnix-migration-snapshots"):
    root = load_policy()["snapshot_roots"].get(source, str(base))
    return f"{root}/{identifier}"


def validate_snapshot(host, identifier, item):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{5,60}', identifier):
        raise ValueError('Invalid backup target')
    allowed = snapshot_sources(host)
    if allowed.get(item['name']) != item['source']:
        raise ValueError('Unexpected snapshot source')
    if item['snapshot'] != f"{snapshot_parent(item['source'], identifier)}/{item['name']}":
        raise ValueError('Unexpected snapshot path')
