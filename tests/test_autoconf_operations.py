import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.autoconf_test_support import isolated_source_script, write_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_fact_refresh_script_is_safe_to_inspect_and_run_from_any_directory():
    script = REPO_ROOT / "scripts/refresh-ansible-facts.sh"
    script_text = script.read_text()

    subprocess.run(["bash", "-n", script], check=True)
    help_result = subprocess.run(
        ["bash", script, "--help"],
        check=True,
        capture_output=True,
        text=True,
        cwd="/tmp",
    )

    assert "last-known-good snapshot" in help_result.stdout
    assert "--strict fails on any stale host" in help_result.stdout
    assert 'dirname -- "${BASH_SOURCE[0]}"' in script_text
    assert "mktemp -d" in script_text
    assert "rm -rf ./ansible/cmdb" not in script_text
    assert "docs/hostinfo" not in script_text
    assert 'ansible_root="$repo_root/ansible"' not in script_text
    assert 'config_file="$repo_root/autoconf/config.yml"' not in script_text
    assert "--print-option paths.ansible_root" in script_text

    conflicting_paths = subprocess.run(
        [
            "bash",
            script,
            "--config",
            "config.yml",
            "--ansible-root",
            "ansible",
        ],
        capture_output=True,
        text=True,
        cwd="/tmp",
        check=False,
    )
    assert conflicting_paths.returncode == 2
    assert "mutually exclusive" in conflicting_paths.stderr


def test_fact_refresh_delegates_the_default_config_to_autoconf(tmp_path):
    script = REPO_ROOT / "scripts/refresh-ansible-facts.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    arguments_file = tmp_path / "python-arguments"
    ansible_root = tmp_path / "ansible"
    ansible_root.mkdir()

    _write_executable(
        fake_bin / "python",
        """#!/usr/bin/env bash
printf '%s\n' "$@" > "$AUTOCONF_ARGUMENTS_FILE"
printf '%s\n' "$AUTOCONF_ANSIBLE_ROOT"
""",
    )
    for command_name in ("ansible", "jq"):
        _write_executable(fake_bin / command_name, "#!/usr/bin/env bash\nexit 1\n")

    result = subprocess.run(
        ["bash", script],
        capture_output=True,
        text=True,
        cwd="/tmp",
        env=os.environ
        | {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AUTOCONF_ARGUMENTS_FILE": str(arguments_file),
            "AUTOCONF_ANSIBLE_ROOT": str(ansible_root),
        },
        check=False,
    )

    assert result.returncode == 1
    assert arguments_file.read_text().splitlines() == [
        str(REPO_ROOT / "scripts/autoconf-pipeline.py"),
        "--print-option",
        "paths.ansible_root",
    ]
    assert "Ansible inventory not found" in result.stderr


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def test_fact_refresh_updates_successes_and_preserves_failed_hosts(tmp_path):
    repo = tmp_path / "repo"
    script_dir = repo / "scripts"
    inventory_dir = repo / "ansible/inventory"
    facts_dir = repo / "ansible/cmdb"
    fake_bin = tmp_path / "bin"
    script_dir.mkdir(parents=True)
    inventory_dir.mkdir(parents=True)
    facts_dir.mkdir()
    fake_bin.mkdir()
    shutil.copy2(REPO_ROOT / "scripts/refresh-ansible-facts.sh", script_dir)
    (inventory_dir / "hosts.ini").write_text("[all]\nfresh\nstale\nmissing\n")

    old_fresh = {"fresh": [{"ansible_facts": {"marker": "old-fresh"}}]}
    old_stale = {"stale": [{"ansible_facts": {"marker": "old-stale"}}]}
    (facts_dir / "fresh.json").write_text(json.dumps(old_fresh))
    (facts_dir / "stale.json").write_text(json.dumps(old_stale))

    _write_executable(
        fake_bin / "ansible",
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == "--list-hosts" ]]; then
    printf '  hosts (3):\\n    fresh\\n    stale\\n    missing\\n'
    exit 0
  fi
done

tree_dir=""
while (( $# > 0 )); do
  if [[ "$1" == "--tree" ]]; then
    tree_dir="$2"
    break
  fi
  shift
done
printf '%s\\n' '{"ansible_facts":{"marker":"new-fresh"}}' > "$tree_dir/fresh"
printf '%s\\n' 'TOP_SECRET_COLLECTOR_OUTPUT'
printf '%s\\n' 'TOP_SECRET_COLLECTOR_ERROR' >&2
exit 4
""",
    )
    env = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}
    script = script_dir / "refresh-ansible-facts.sh"

    partial = subprocess.run(
        ["bash", script, "--ansible-root", repo / "ansible"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )

    assert partial.returncode == 0
    assert json.loads((facts_dir / "fresh.json").read_text()) == {
        "fresh": [{"ansible_facts": {"marker": "new-fresh"}}]
    }
    assert json.loads((facts_dir / "stale.json").read_text()) == old_stale
    assert not (facts_dir / "missing.json").exists()
    assert "Stale or missing (2): stale missing" in partial.stderr
    assert "stale: retained last-known-good snapshot" in partial.stderr
    assert "missing: no valid snapshot available" in partial.stderr
    assert "TOP_SECRET" not in partial.stdout + partial.stderr
    assert facts_dir.stat().st_mode & 0o777 == 0o700
    assert (facts_dir / "fresh.json").stat().st_mode & 0o777 == 0o600
    assert not list((repo / "ansible").glob(".cmdb-refresh.*"))

    strict = subprocess.run(
        ["bash", script, "--strict", "--ansible-root", repo / "ansible"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )

    assert strict.returncode != 0
    assert json.loads((facts_dir / "stale.json").read_text()) == old_stale


def test_private_report_is_redacted_and_preserves_last_good_output(tmp_path):
    repo = tmp_path / "repo"
    script_dir = repo / "scripts"
    facts_dir = repo / "ansible/cmdb"
    script_dir.mkdir(parents=True)
    facts_dir.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts/generate-cmdb-report.py", script_dir)
    (facts_dir / "node-01.json").write_text(
        json.dumps(
            {
                "node-01": [
                    {
                        "ansible_facts": {
                            "ansible_architecture": "x86_64",
                            "ansible_distribution": "NixOS",
                            "ansible_distribution_version": "25.11",
                            "ansible_env": {"TOKEN": "TOP_SECRET"},
                            "ansible_product_serial": "SERIAL_SECRET",
                        }
                    }
                ]
            }
        )
    )
    script = script_dir / "generate-cmdb-report.py"

    generated = subprocess.run(
        [
            sys.executable,
            script,
            "--facts-dir",
            facts_dir,
            "--output",
            repo / "cmdb/index.html",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    report = repo / "cmdb/index.html"
    assert generated.returncode == 0, generated.stderr
    report_text = report.read_text()
    assert "node-01" in report_text
    assert "NixOS 25.11" in report_text
    assert "TOP_SECRET" not in report_text
    assert "SERIAL_SECRET" not in report_text
    assert "<script" not in report_text
    assert "http://" not in report_text
    assert "https://" not in report_text
    assert report.stat().st_mode & 0o777 == 0o600
    assert report.parent.stat().st_mode & 0o777 == 0o700

    (facts_dir / "node-01.json").write_text("not JSON")
    failed = subprocess.run(
        [
            sys.executable,
            script,
            "--facts-dir",
            facts_dir,
            "--output",
            report,
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert failed.returncode != 0
    assert report.read_text() == report_text


def test_private_report_resolves_input_and_output_from_alternative_config(
    tmp_path,
) -> None:
    config_file = write_config(tmp_path)
    facts_dir = tmp_path / "ansible/cmdb"
    (facts_dir / "node-01.json").write_text(
        json.dumps({"ansible_facts": {"ansible_distribution": "NixOS"}})
    )

    generated = subprocess.run(
        isolated_source_script(
            REPO_ROOT / "scripts/generate-cmdb-report.py",
            "--config",
            config_file,
        ),
        capture_output=True,
        text=True,
        cwd="/tmp",
        check=False,
    )

    report = tmp_path / "report/index.html"
    assert generated.returncode == 0, generated.stderr
    assert report.is_file()
    assert "node-01" in report.read_text(encoding="utf-8")
    assert report.stat().st_mode & 0o777 == 0o600


def test_private_report_has_no_second_default_config_path() -> None:
    source = (REPO_ROOT / "scripts/generate-cmdb-report.py").read_text(encoding="utf-8")

    assert 'DEFAULT_CONFIG_PATH = REPO_ROOT / "autoconf/config.yml"' not in source


def _run_private_report(tmp_path, payload):
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir(exist_ok=True)
    (facts_dir / "node-01.json").write_text(json.dumps(payload))
    output = tmp_path / "report/index.html"
    result = subprocess.run(
        [
            sys.executable,
            REPO_ROOT / "scripts/generate-cmdb-report.py",
            "--facts-dir",
            facts_dir,
            "--output",
            output,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output


def test_private_report_exposes_static_observation_age_and_unknown_timestamp(tmp_path):
    result, output = _run_private_report(
        tmp_path,
        {
            "ansible_facts": {
                "ansible_distribution": "NixOS",
                "ansible_date_time": {"epoch": "946684800"},
                "ansible_memtotal_mb": "2048",
                "ansible_processor_vcpus": "4",
            }
        },
    )
    assert result.returncode == 0, result.stderr
    report = output.read_text()
    assert "Generated at " in report
    assert "2000-01-01T00:00:00+00:00" in report
    assert "seconds at generation" in report
    assert "Static inventory snapshot, not live health or availability" in report
    assert "No clinical" in report
    assert "<td>4</td><td>2.0</td>" in report
    result, output = _run_private_report(
        tmp_path,
        {
            "ansible_facts": {
                "ansible_distribution": "NixOS",
            }
        },
    )
    assert result.returncode == 0, result.stderr
    assert "<td>unknown</td><td>unknown</td>" in output.read_text()


def test_private_report_marks_future_observation_as_clock_skew(tmp_path):
    result, output = _run_private_report(
        tmp_path,
        {
            "ansible_facts": {
                "ansible_date_time": {"epoch": "4102444800"},
            }
        },
    )
    assert result.returncode == 0, result.stderr
    assert "clock skew: observation is in the future" in output.read_text()


def test_private_report_rejects_malformed_fields_and_failed_results(tmp_path):
    result, output = _run_private_report(
        tmp_path,
        {
            "ansible_facts": {
                "ansible_distribution": "NixOS",
            }
        },
    )
    assert result.returncode == 0
    last_good = output.read_text()
    invalid = [
        {"ansible_facts": {}},
        {"failed": True, "ansible_facts": {"ansible_distribution": "NixOS"}},
        {"unreachable": True, "ansible_facts": {"ansible_distribution": "NixOS"}},
        {"failed": None, "ansible_facts": {"ansible_distribution": "NixOS"}},
        {"node-01": [{"unreachable": True, "ansible_facts": {"x": 1}}]},
    ]
    for key, value in [
        ("ansible_distribution", {"unexpected": "TOP_SECRET"}),
        ("ansible_architecture", ["TOP_SECRET"]),
        ("ansible_memtotal_mb", "NaN"),
        ("ansible_memtotal_mb", -1024),
        ("ansible_memtotal_mb", True),
        ("ansible_memtotal_mb", "Infinity"),
        ("ansible_processor_vcpus", 1.5),
        ("ansible_processor_vcpus", False),
        ("ansible_date_time", "TOP_SECRET"),
        ("ansible_date_time", {"epoch": "1e300"}),
    ]:
        invalid.append({"ansible_facts": {key: value}})
    for payload in invalid:
        result, output = _run_private_report(tmp_path, payload)
        assert result.returncode == 1, payload
        assert output.read_text() == last_good
        assert "TOP_SECRET" not in result.stderr + result.stdout


def test_fact_refresh_rejects_failed_unreachable_empty_and_malformed_flags(tmp_path):
    inventory = tmp_path / "ansible/inventory"
    inventory.mkdir(parents=True)
    (inventory / "hosts.ini").write_text("[all]\nnode-01\n")
    facts = tmp_path / "ansible/cmdb"
    facts.mkdir()
    snapshot = facts / "node-01.json"
    snapshot.write_text(json.dumps({"ansible_facts": {"marker": "last-good"}}))
    original = snapshot.read_bytes()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ansible",
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == "--list-hosts" ]]; then
    printf '  hosts (1):\\n    node-01\\n'
    exit 0
  fi
done
while (( $# > 0 )); do
  if [[ "$1" == "--tree" ]]; then
    cp "$TEST_FACT_RESPONSE" "$2/node-01"
    exit 0
  fi
  shift
done
exit 2
""",
    )
    response = tmp_path / "response.json"
    payloads = [{"ansible_facts": {}}]
    for flag in ("failed", "unreachable"):
        for value in (True, None, "false", 0):
            item = {flag: value, "ansible_facts": {"marker": "bad"}}
            payloads.extend([item, {"node-01": [item]}])
    raw_responses = [json.dumps(payload) for payload in payloads]
    raw_responses.extend(
        [
            "",
            "not JSON",
            '{"ansible_facts":{"x":1}}\n{"ansible_facts":{"x":2}}',
        ]
    )
    for raw_response in raw_responses:
        response.write_text(raw_response)
        result = subprocess.run(
            [
                "bash",
                REPO_ROOT / "scripts/refresh-ansible-facts.sh",
                "--ansible-root",
                inventory.parent,
            ],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ
            | {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "TEST_FACT_RESPONSE": str(response),
            },
        )
        assert result.returncode == 1, raw_response
        assert "retained last-known-good snapshot" in result.stderr
        assert snapshot.read_bytes() == original
