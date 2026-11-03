#!/usr/bin/env python3
"""Reject new Ruff diagnostics; baseline updates may only remove existing debt."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lx_administration.yaml.loading import load_unique_yaml_file  # noqa: E402


def fingerprint(code, source):
    return hashlib.sha256((code + '\0' + source).encode()).hexdigest()[:32]


def encode_baseline(findings):
    grouped = {}
    for (path, code, digest), count in sorted(findings.items()):
        grouped.setdefault(path, {}).setdefault(code, {})[digest] = count
    return grouped


def decode_baseline(value):
    result = Counter()
    if not isinstance(value, dict):
        raise ValueError('Baseline must be a mapping')
    for path, rules in value.items():
        if (not isinstance(path, str) or Path(path).is_absolute()
                or '..' in Path(path).parts or not isinstance(rules, dict)):
            raise ValueError('Invalid baseline path')
        for code, fingerprints in rules.items():
            if not isinstance(code, str) or not isinstance(fingerprints, dict):
                raise ValueError('Invalid baseline rule')
            for digest, count in fingerprints.items():
                if (not isinstance(digest, str) or len(digest) != 32
                        or any(c not in '0123456789abcdef' for c in digest)
                        or type(count) is not int or count <= 0):
                    raise ValueError('Invalid baseline fingerprint')
                result[path, code, digest] = count
    return result


def scan(root, policy):
    version = subprocess.check_output(['ruff', '--version'], text=True).strip()
    if version != 'ruff ' + policy['ruff_version']:
        raise ValueError('Ruff version differs from the locked quality policy')
    paths = sorted({str(path.relative_to(root)) for pattern in policy['scope']
                    for path in root.glob(pattern)})
    if not paths:
        raise ValueError('Python quality scope is empty')
    command = ['ruff', 'check', '--isolated', '--target-version', 'py312',
               '--select', ','.join(policy['rules']), '--line-length',
               str(policy['line_length']), '--output-format', 'json', *paths]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise ValueError('Ruff could not complete the configured scan')
    findings, locations = Counter(), {}
    for item in json.loads(result.stdout):
        path = Path(item['filename']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Ruff reported a source outside the repository')
        lines = path.read_text().splitlines()
        row, end = item['location']['row'], item['end_location']['row']
        source = '\n'.join(lines[row - 1:end])
        key = (path.relative_to(root).as_posix(), item['code'],
               fingerprint(item['code'], source))
        findings[key] += 1
        locations[key] = row
    return findings, locations


def ratchet(path, policy, findings):
    """Replace baseline data only after rejecting every added diagnostic."""
    if findings - decode_baseline(policy['baseline']):
        raise ValueError('Cannot ratchet a baseline with new diagnostics')
    # The policy header is kept human-readable; compact per-rule mappings keep
    # baseline data small while fingerprints survive unrelated line insertions.
    import yaml
    policy = dict(policy, baseline=encode_baseline(findings))
    header = {key: value for key, value in policy.items() if key != 'baseline'}
    text = yaml.safe_dump(header, sort_keys=False) + 'baseline:\n'
    for source, rules in policy['baseline'].items():
        text += '  ' + json.dumps(source) + ':\n'
        for code, values in rules.items():
            text += '    ' + code + ': ' + json.dumps(values) + '\n'
    from lx_administration.utils.file_operations import atomic_write_file
    atomic_write_file(destination=path, content=[text.encode()], file_mode=0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=ROOT / 'python-quality.yml')
    parser.add_argument('--ratchet', action='store_true')
    args = parser.parse_args()
    policy = load_unique_yaml_file(args.policy)
    if (not isinstance(policy, dict) or policy.get('schema_version') != 1
            or policy.get('rules') != ['E', 'F', 'W']
            or policy.get('line_length') != 88
            or not isinstance(policy.get('scope'), list)
            or not all(isinstance(p, str) and not Path(p).is_absolute()
                       and '..' not in Path(p).parts for p in policy['scope'])):
        parser.error('Invalid Python quality policy')
    baseline = decode_baseline(policy['baseline'])
    findings, locations = scan(ROOT, policy)
    added = findings - baseline
    for path, code, digest in sorted(added):
        print(f'{path}:{locations[path, code, digest]}: new {code} diagnostic')
    if added:
        print(f'Python quality failed: {sum(added.values())} new diagnostics')
        return 1
    if args.ratchet:
        ratchet(args.policy, policy, findings)
    print(f'Python quality passed: {sum(findings.values())} existing diagnostics; '
          f'{sum((baseline - findings).values())} resolved')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        sys.exit(f'Python quality failed: {error}')
