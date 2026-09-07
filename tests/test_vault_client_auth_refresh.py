"""Run the actual sourced refresh helper with an expired bootstrap token."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/vault/refresh-client-auth.sh"


@pytest.mark.parametrize("fail", [False, True])
def test_refresh_ignores_expired_token_and_redacts_errors(tmp_path, fail):
    if not shutil.which("jq"):
        pytest.skip("jq is required by deployed refresh helper")
    vault = tmp_path / "vault"
    vault.write_text("""#!/usr/bin/env python3
import json, os, sys
assert not os.environ.get('VAULT_TOKEN'), 'expired token leaked into fresh login'
assert sys.argv[1:] == ['write', '-field=token', 'auth/approle/login', '-']
assert json.load(sys.stdin) == {
    'role_id':'test-only-role', 'secret_id':'test-only-secret'}
if os.environ.get('TEST_FAIL') == '1':
    print('test-only-sensitive-error', file=sys.stderr)
    sys.exit(2)
print('test-only-fresh-token')
""")
    vault.chmod(0o700)
    (tmp_path / "role").write_text("test-only-role\n")
    (tmp_path / "secret").write_text("test-only-secret\n")
    env = dict(
        os.environ,
        PATH=str(tmp_path) + ":" + os.environ["PATH"],
        VAULT_TOKEN="test-only-expired",
        ROLE_ID_FILE=str(tmp_path / "role"),
        SECRET_ID_FILE=str(tmp_path / "secret"),
        TEST_FAIL=str(int(fail)),
    )
    result = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            'source "$1"; refresh_client_auth; '
            'test "$VAULT_TOKEN" = test-only-fresh-token',
            "_",
            str(HELPER),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == int(fail)
    assert "test-only-sensitive" not in result.stderr
    assert "test-only-fresh-token" not in result.stdout
    assert "test-only-secret" not in result.stderr


def test_issuance_refreshes_after_cache_check_and_before_vault_write():
    source = (ROOT / "modules/nixos/luxnix/vault/default.nix").read_text()
    issue = source.split("  issueHubClientCertificateScript =", 1)[1].split(
        "  vaultAuthSetupScript =", 1
    )[0]
    assert issue.index(
        "-checkend ${toString clientHubPkiCfg.renewBeforeSeconds}"
    ) < issue.index("refresh_client_auth")
    assert issue.index("refresh_client_auth") < issue.index("vault write -format=json")
    assert "-checkend 0" in issue


@pytest.mark.parametrize(
    "forced, failed", [(False, False), (True, False), (True, True)]
)
def test_force_marker_bypasses_valid_cache_and_survives_failure(
    tmp_path, forced, failed
):
    source = (ROOT / "modules/nixos/luxnix/vault/default.nix").read_text()
    issue = source.split("  issueHubClientCertificateScript =", 1)[1].split(
        "  publishHubClientCaScript =", 1
    )[0]
    # Execute the actual cache decision with a valid cached certificate/key;
    # issuance is deliberately a controlled local success/failure boundary.
    cache = issue.split("    force_reissue=0", 1)[1].split("    ${optionalString", 1)[0]
    cache = "force_reissue=0" + cache
    cache = cache.replace("${lib.escapeShellArg clientReissueMarker}", '"$marker"')
    cache = cache.replace("${pkgs.openssl}/bin/openssl", "true")
    cache = cache.replace("${toString clientHubPkiCfg.renewBeforeSeconds}", "86400")
    published_cleanup = issue.rsplit('    ${pkgs.coreutils}/bin/rm -f "$response"', 1)[
        1
    ].split("\n", 1)[0]
    assert "clientReissueMarker" in published_cleanup
    assert issue.index('"$ca_tmp" "$client_ca"') < issue.rindex(published_cleanup)
    marker = tmp_path / "force"
    if forced:
        marker.touch()
    cert = tmp_path / "cert"
    cert.write_text("test-only-valid-cache")
    script = "certificate_matches_key() { return 0; };\n" + cache
    script += '\nprintf issuance > "$observed"\n'
    script += "exit 1\n" if failed else 'rm -f "$marker"\n'
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env=dict(
            os.environ,
            marker=str(marker),
            certificate=str(cert),
            private_key=str(cert),
            observed=str(tmp_path / "observed"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == int(failed)
    assert (tmp_path / "observed").exists() == forced
    assert marker.exists() == (forced and failed)
    assert issue.count('if [ "$force_reissue" = 0 ]') == 4
