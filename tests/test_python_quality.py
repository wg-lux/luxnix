"""A reduced lint count must never hide a different new diagnostic."""
from collections import Counter
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUALITY = runpy.run_path(str(ROOT / 'scripts/python-quality.py'))


def test_baseline_roundtrip_preserves_duplicate_counts():
    findings = Counter({('app.py', 'E501', 'a' * 32): 2})
    assert QUALITY['decode_baseline'](
        QUALITY['encode_baseline'](findings)) == findings


def test_new_fingerprint_cannot_replace_resolved_debt(tmp_path):
    old = Counter({('app.py', 'E501', 'a' * 32): 2})
    new = Counter({('app.py', 'E501', 'b' * 32): 1})
    path = tmp_path / 'quality.yml'
    path.write_text('preserve policy')
    with pytest.raises(ValueError, match='new diagnostics'):
        QUALITY['ratchet'](path, {'baseline': QUALITY['encode_baseline'](old)}, new)
    assert path.read_text() == 'preserve policy'


def test_resolved_debt_can_only_lower_baseline(tmp_path):
    findings = Counter({('app.py', 'E501', 'a' * 32): 1})
    policy = {'schema_version': 1, 'baseline': QUALITY['encode_baseline'](
        Counter({('app.py', 'E501', 'a' * 32): 2}))}
    path = tmp_path / 'quality.yml'
    QUALITY['ratchet'](path, policy, findings)
    import yaml
    saved = yaml.safe_load(path.read_text())
    assert QUALITY['decode_baseline'](saved['baseline']) == findings


def test_real_ruff_scan_uses_source_fingerprint_not_line_number(tmp_path):
    source = tmp_path / 'example.py'
    source.write_text('import unused_module\n')
    policy = {'scope': ['*.py'], 'rules': ['E', 'F', 'W'],
              'line_length': 88, 'ruff_version': '0.14.14'}
    first, _ = QUALITY['scan'](tmp_path, policy)
    source.write_text('\n\nimport unused_module\n')
    second, _ = QUALITY['scan'](tmp_path, policy)
    assert first == second
    source.write_text('import another_unused_module\n')
    third, _ = QUALITY['scan'](tmp_path, policy)
    assert third - first


@pytest.mark.parametrize('bad', [[], {'../outside': {}},
                                  {'app.py': {'E501': {'a' * 32: 0}}}])
def test_invalid_baselines_fail_closed(bad):
    with pytest.raises(ValueError):
        QUALITY['decode_baseline'](bad)
