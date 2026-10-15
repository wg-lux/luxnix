"""Execute the shared acceptance probe against controlled transport responses."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "modules/nixos/services/lx-annotate-local/scripts/acceptance-static.nix"


@pytest.fixture
def probe(tmp_path):
    fake_package = tmp_path / "curl"
    (fake_package / "bin").mkdir(parents=True)
    curl = fake_package / "bin/curl"
    curl.write_text(
        "#!/usr/bin/env python\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['TEST_CURL_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.stdout.write(os.environ['TEST_RESPONSE'])\n"
        "raise SystemExit(int(os.environ['TEST_CURL_STATUS']))\n"
    )
    curl.chmod(0o755)
    jq = shutil.which("jq")
    assert jq, "jq is required by the deployed acceptance helper"
    expression = (
        f"import {HELPER} {{ "
        f"pkgs = {{ curl = {json.dumps(str(fake_package))}; "
        f"jq = {json.dumps(str(Path(jq).parent.parent))}; }}; "
        # Fixture arguments contain no quotes; the actual caller uses nixpkgs lib.
        'lib.escapeShellArg = value: "\'" + value + "\'"; '
        'hostname = "clinical.test"; certificatePath = "/test/ca.crt"; }'
    )
    evaluated = subprocess.run(
        ["nix-instantiate", "--eval", "--strict", "--json", "--expr", expression],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    script = tmp_path / "probe.sh"
    script.write_text("set -euo pipefail\n" + json.loads(evaluated.stdout))
    arguments = tmp_path / "arguments.json"

    def run(response, status=0):
        result = subprocess.run(
            ["bash", script],
            capture_output=True,
            text=True,
            timeout=5,
            env=os.environ
            | {
                "TEST_RESPONSE": response,
                "TEST_CURL_STATUS": str(status),
                "TEST_CURL_ARGS": str(arguments),
            },
        )
        args = json.loads(arguments.read_text())
        for name, value in (
            ("--connect-timeout", "5"),
            ("--max-time", "15"),
            ("--max-filesize", "1048576"),
            ("--cacert", "/test/ca.crt"),
            ("--resolve", "clinical.test:443:127.0.0.1"),
        ):
            assert args[args.index(name) + 1] == value
        assert "--fail" in args
        assert "--insecure" not in args
        assert args[-1] == "https://clinical.test/static/.vite/manifest.json"
        return result

    return run


def test_acceptance_accepts_one_valid_vite_entrypoint(probe):
    result = probe('{"src/main.ts":{"file":"assets/main-a1.js","isEntry":true}}')
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "response",
    [
        "",
        "<html>TOP_SECRET error</html>",
        "not JSON",
        "null",
        "[]",
        "{}",
        '{"src/main.ts":null}',
        '{"src/main.ts":{"file":false}}',
        '{"src/main.ts":{"file":""}}',
        '{"src/main.ts":{"file":123}}',
        '{"src/main.ts":{"file":["TOP_SECRET"]}}',
        '{"src/main.ts":{"file":"assets/main.js"}}\n{}',
    ],
)
def test_acceptance_rejects_empty_malformed_or_wrong_manifest_without_body_logs(
    probe, response
):
    result = probe(response)
    assert result.returncode == 1
    assert "invalid entry-point manifest" in result.stderr
    assert "TOP_SECRET" not in result.stdout + result.stderr


@pytest.mark.parametrize("status", [22, 28, 60, 63])
def test_acceptance_rejects_http_timeout_tls_and_size_errors_even_with_valid_json(
    probe, status
):
    result = probe('{"src/main.ts":{"file":"assets/main.js"}}', status)
    assert result.returncode == 1
    assert "TLS static manifest probe failed" in result.stderr
