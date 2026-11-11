"""Run the actual sourced refresh helper with an expired bootstrap token."""

import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/vault/refresh-client-auth.sh"


def test_client_authentication_waits_for_vpn_readiness():
    expression = f'''let
      f = builtins.getFlake "git+file://{ROOT}";
      inspect = configuration: let
        c = configuration.config;
        auth = c.systemd.services.vault-auth-setup;
        vpn = "openvpn-${{c.roles.aglnet.client.networkName}}.service";
      in {{
        inherit vpn;
        inherit (auth) after wants;
        vpnRequires = c.systemd.services.openvpn-aglnet.requires;
      }};
      configured = f.nixosConfigurations.gc-10;
      withoutVpn = configured.extendModules {{ modules = [ {{
        roles.aglnet.client.enable = f.inputs.nixpkgs.lib.mkForce false;
      }} ]; }};
    in {{ configured = inspect configured; withoutVpn = inspect withoutVpn; }}'''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=180,
    )
    cases = json.loads(result.stdout)
    configured = cases["configured"]
    assert configured["vpn"] in configured["after"]
    assert configured["vpn"] in configured["wants"]
    assert "managed-secrets-setup.service" not in configured["vpnRequires"]
    without_vpn = cases["withoutVpn"]
    assert without_vpn["vpn"] not in without_vpn["after"]
    assert without_vpn["vpn"] not in without_vpn["wants"]


def run_condition(tmp_path, auth):
    source = (ROOT / "modules/nixos/luxnix/vault/tools/auth.nix").read_text()
    condition = source.split("  vaultAuthProvisioningConditionScript =", 1)[1]
    script = condition.split("    write_status()", 1)[1].split("    missing=0", 1)[0]
    script = "write_status()" + script
    script += "auth_error=" + condition.split("    auth_error=", 1)[1].split(
        "  '';", 1
    )[0]
    for name, filename in (("runtimeEnvironmentFile", "vault.env"),
                           ("runtimeTokenFile", "vault.token"),
                           ("runtimeStatusFile", "enrollment-status"),
                           ("runtimeDir", ".")):
        script = script.replace("${lib.escapeShellArg " + name + "}",
                                shlex.quote(str(tmp_path / filename)))
    script = script.replace("${pkgs.coreutils}/bin/", "")
    script = script.replace("${pkgs.systemd}/bin/systemctl", "systemctl")
    script = script.replace("${vaultAuthSetupScript}", "authenticate")
    script = script.replace(
        "${vaultAuthErrorClassifierTool}/bin/luxnix-vault-classify-auth-error",
        "bash " + shlex.quote(str(ROOT / "scripts/vault/classify-auth-error.sh")),
    )
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c",
         "systemctl() { echo \"$*\" >> systemctl.log; };\n"
         "authenticate() { " + auth + "; };\n" + script],
        cwd=tmp_path, capture_output=True, text=True,
    )


FRESH = "printf fresh > vault.env; printf fresh > vault.token"


# Exit 255 is a temporary failure that systemd retries; exit 1 waits for an operator.
@pytest.mark.parametrize("outcome, auth, code", [
    ("ready", FRESH, 0),
    ("vault-unreachable", "echo 'dial tcp: connection refused' >&2; return 1", 255),
    ("vault-sealed", "echo 'Vault is sealed' >&2; return 1", 255),
    ("auth-rejected",
     "echo 'invalid role or secret ID test-only-sensitive' >&2; return 1", 1),
    # Success without credentials is never readiness (formerly offline-cached).
    ("vault-error", "return 0", 1),
])
def test_enrollment_status_requires_fresh_authentication(tmp_path, outcome, auth, code):
    (tmp_path / "vault.env").write_text("test-only-stale-env")
    (tmp_path / "vault.token").write_text("test-only-stale-token")
    result = run_condition(tmp_path, auth)
    assert result.returncode == code, result.stderr
    assert (tmp_path / "enrollment-status").read_text().strip() == outcome
    assert (tmp_path / "vault.env").exists() == (outcome == "ready")
    assert (tmp_path / "vault.token").exists() == (outcome == "ready")
    assert not list(tmp_path.glob(".vault-auth-error.*"))
    assert "test-only-sensitive" not in result.stderr
    assert (tmp_path / ".recovery-pending").exists() == (code == 255)
    assert not (tmp_path / "systemctl.log").exists()
    # The unit is declared in config.nix since the vault module split.
    config = (ROOT / "modules/nixos/luxnix/vault/config.nix").read_text()
    unit = config.split("services.vault-auth-setup =", 1)[1]
    assert re.search(r"else\s+vaultAuthProvisioningConditionScript;", unit)


def test_recovery_after_outage_restarts_refused_services(tmp_path):
    refused = "echo 'dial tcp: connection refused' >&2; return 1"
    outage = run_condition(tmp_path, refused)
    assert outage.returncode == 255
    recovered = run_condition(tmp_path, FRESH)
    assert recovered.returncode == 0, recovered.stderr
    assert not (tmp_path / ".recovery-pending").exists()
    assert (tmp_path / "systemctl.log").read_text().split("\n")[0] == (
        "--no-block --job-mode=fail start default.target"
    )
    # A later success without an outage queues nothing again.
    run_condition(tmp_path, FRESH)
    assert len((tmp_path / "systemctl.log").read_text().splitlines()) == 1


def test_auth_never_reports_offline_success():
    source = (ROOT / "modules/nixos/luxnix/vault/tools/auth.nix").read_text()
    setup = source.split("vaultAuthSetupScript =", 1)[1].split(
        "vaultAuthProvisioningConditionScript =", 1)[0]
    assert "allowOffline" not in setup
    assert "write_status offline-cached" not in source


def eval_host(host, attribute, wrap=""):
    expression = f'''
      let f = builtins.getFlake "git+file://{ROOT}";
      in {wrap} (f.nixosConfigurations.{host}.config.{attribute})
    '''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("host, offline", [("gc-09", True), ("gc-02", False)])
def test_vault_outage_is_retried_and_named_not_a_dead_end(host, offline):
    unit = "systemd.services.vault-auth-setup"
    config = eval_host(host, f"{unit}.serviceConfig")
    assert config["Restart"] == "on-failure"
    assert config["RestartPreventExitStatus"] == "1"
    assert eval_host(host, f"{unit}.startLimitIntervalSec") == 0
    secrets = {
        name: eval_host(host, f"systemd.services.managed-secrets-setup.{name}")
        for name in ("after", "wants", "requires")
    }
    # readFile builds the script, so the assertion reads the deployed text.
    script = eval_host(
        host,
        "systemd.services.managed-secrets-setup.serviceConfig.ExecStart",
        wrap="builtins.readFile",
    )
    assert "vault-auth-setup.service" in secrets["after"]
    # allowOffline hosts reuse existing secrets and name the blocker meanwhile.
    assert ("vault-auth-setup.service" in secrets["wants"]) == offline
    assert ("vault-auth-setup.service" in secrets["requires"]) != offline
    assert ("BLOCKER: Vault authentication is unavailable" in script) == offline


def test_certificate_service_can_resolve_authentication_tools():
    expression = f'''
      let f = builtins.getFlake "git+file://{ROOT}";
      in f.nixosConfigurations.gc-02.config.systemd.services
        .luxnix-vault-issue-hub-client-certificate.environment.PATH
    '''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    path = json.loads(result.stdout)
    for command in ("vault", "jq", "getent"):
        executable = shutil.which(command, path=path)
        assert executable, f"{command} is missing from the service PATH"
        subprocess.run(
            [executable, "version" if command == "vault" else "--version"],
            env={"PATH": path}, capture_output=True, text=True, check=True,
        )
    # Without HOME, Vault resolves its token-helper config through getent before
    # contacting the server. Exercise that path with no live credentials.
    result = subprocess.run(
        [shutil.which("vault", path=path), "write", "auth/approle/login", "-"],
        input="{}", env={"PATH": path, "VAULT_ADDR": "http://127.0.0.1:1"},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "connection refused" in result.stderr


@pytest.mark.parametrize("error, state", [
    (None, None),
    ("test-only-sensitive-error", "vault-error"),
    ("x509: certificate signed by unknown authority", "tls-trust-failed"),
    ("Vault is sealed", "vault-sealed"),
    ("dial tcp: connection refused", "vault-unreachable"),
    ("invalid role or secret ID", "auth-rejected"),
])
def test_refresh_ignores_expired_token_and_redacts_errors(tmp_path, error, state):
    fail = error is not None
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
    print(os.environ['TEST_ERROR'] + ' test-only-sensitive-error', file=sys.stderr)
    sys.exit(2)
print('test-only-fresh-token')
""")
    vault.chmod(0o700)
    (tmp_path / "role").write_text("test-only-role\n")
    (tmp_path / "secret").write_text("test-only-secret\n")
    classifier = tmp_path / "classify-auth-error"
    classifier.write_text((ROOT / "scripts/vault/classify-auth-error.sh").read_text())
    classifier.chmod(0o700)
    env = dict(
        os.environ,
        PATH=str(tmp_path) + ":" + os.environ["PATH"],
        VAULT_TOKEN="test-only-expired",
        ROLE_ID_FILE=str(tmp_path / "role"),
        SECRET_ID_FILE=str(tmp_path / "secret"),
        TEST_FAIL=str(int(fail)),
        TEST_ERROR=error or "",
        TMPDIR=str(tmp_path),
        VAULT_AUTH_ERROR_CLASSIFIER=str(classifier),
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
    assert not list(tmp_path.glob("tmp.*"))
    if fail:
        assert f"state: {state}" in result.stderr
    assert "test-only-sensitive" not in result.stderr
    assert "test-only-fresh-token" not in result.stdout
    assert "test-only-secret" not in result.stderr


def test_issuance_refreshes_after_cache_check_and_before_vault_write():
    source = (ROOT / "modules/nixos/luxnix/vault/tools/client.nix").read_text()
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
    source = (ROOT / "modules/nixos/luxnix/vault/tools/client.nix").read_text()
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
