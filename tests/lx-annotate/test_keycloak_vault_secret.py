from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from nix_eval_helpers import eval_json

KV_PATH = "lx-hub-secrets/oidc/endoregdb-api"


def test_keycloak_secret_is_fetched_from_the_shared_vault_path_when_enabled():
    contract = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          host = f.nixosConfigurations.gc-02;
          c = (host.extendModules { modules = [{
            services.luxnix.lxAnnotateLocal.django.keycloakSecretViaVault = true;
          }]; }).config;
      in {
        defaultEnabled = host.config.services.luxnix.lxAnnotateLocal.django.keycloakSecretViaVault;
        defaultSecret = host.config.roles.managed-secrets.customSecrets ? lx_annotate_keycloak_client_secret;
        consumerPath = toString c.services.luxnix.lxAnnotateLocal.django.keycloakSecretFile;
        secret = c.roles.managed-secrets.customSecrets.lx_annotate_keycloak_client_secret;
        failed = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      }
    """)
    assert contract["defaultEnabled"] is False
    assert contract["defaultSecret"] is False
    assert contract["failed"] == []
    secret = contract["secret"]
    assert secret["path"] == contract["consumerPath"] == "/etc/secrets/vault/keycloak.env"
    assert (secret["owner"], secret["group"], secret["permissions"]) == ("root", "root", "600")
    assert secret["refreshOnBoot"] and secret["customScript"]
    assert f"-field=client_secret {KV_PATH}" in secret["generator"]
    assert "Vault returned an empty Keycloak client secret" in secret["generator"]


def test_keycloak_secret_via_vault_requires_enrolled_machine_auth():
    rejected = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          lib = f.inputs.nixpkgs.lib;
          c = (f.nixosConfigurations.gc-02.extendModules { modules = [{
            services.luxnix.lxAnnotateLocal.django.keycloakSecretViaVault = true;
            luxnix.vault.client.auth.deferUntilProvisioned = lib.mkForce true;
          }]; }).config;
      in builtins.any (a: !a.assertion && lib.hasInfix "keycloakSecretViaVault" a.message) c.assertions
    """)
    assert rejected


def _gs02_tool(name: str) -> str:
    return eval_json(
        """
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          tool = builtins.head (builtins.filter (p: (p.name or "") == "NAME")
            f.nixosConfigurations.gs-02.config.environment.systemPackages);
      in builtins.readFile "${tool}/bin/NAME"
    """.replace("NAME", name)
    )


# Site policy grants are exercised by the recorded reconciliation in
# test_identity_salt_enrollment.py::test_enrollment_publishes_only_allowlisted_center_salts.

RECORDER = """
import json, os, sys
from pathlib import Path
path = Path(os.environ["RECORDING_VAULT"])
state = json.loads(path.read_text())
args = sys.argv[1:]
if args[:2] == ["kv", "get"]:
    if state.get("denied"):
        print("permission denied", file=sys.stderr)
        sys.exit(2)
    if state.get("current") is None:
        print("No value found at " + args[-1], file=sys.stderr)
        sys.exit(2)
    print(json.dumps({"data": {"data": {"client_secret": state["current"]},
                               "metadata": {"version": state["version"]}}}))
elif args[:2] == ["kv", "put"]:
    assert args[-1] == "client_secret=-", args
    state["puts"].append({"cas": args[2], "path": args[3], "value": sys.stdin.read()})
path.write_text(json.dumps(state))
"""


@pytest.fixture(scope="module")
def publish_script():
    return _gs02_tool("luxnix-vault-publish-oidc-client-secret")


@pytest.mark.parametrize(
    "current,denied,rotate,value,returncode,puts",
    [
        (None, False, False, "new-secret", 0, [{"cas": "-cas=0", "path": KV_PATH, "value": "new-secret"}]),
        ("new-secret", False, False, "new-secret", 0, []),
        ("old-secret", False, False, "new-secret", 1, []),
        ("old-secret", False, True, "new-secret", 0, [{"cas": "-cas=3", "path": KV_PATH, "value": "new-secret"}]),
        (None, True, False, "new-secret", 1, []),
        (None, False, False, "two words", 1, []),
        (None, False, False, "", 1, []),
    ],
)
def test_publish_tool_never_replaces_implicitly(
    tmp_path, publish_script, current, denied, rotate, value, returncode, puts
):
    recorder = tmp_path / "vault.py"
    recorder.write_text(RECORDER)
    record = tmp_path / "state.json"
    record.write_text(json.dumps({"current": current, "version": 3, "denied": denied, "puts": []}))
    script = re.sub(r"(?<![\w/-])vault(?= )", f"{sys.executable} {recorder}", publish_script)
    env = {
        **os.environ,
        "VAULT_ADDR": "https://test.invalid",
        "VAULT_TOKEN": "test-only",
        "RECORDING_VAULT": str(record),
    }
    env.pop("LUXNIX_VAULT_ALLOW_OIDC_CLIENT_SECRET_ROTATION", None)
    if rotate:
        env["LUXNIX_VAULT_ALLOW_OIDC_CLIENT_SECRET_ROTATION"] = "1"
    result = subprocess.run(
        ["bash", "-c", script, "publish"],
        input=value + "\n",
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == returncode, result.stderr
    assert json.loads(record.read_text())["puts"] == puts
    # The secret never reaches logs.
    assert "new-secret" not in result.stdout + result.stderr
