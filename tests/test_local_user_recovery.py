"""Evaluate real host policy and execute its validation snippet without activation."""

import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def recovery_policy():
    if shutil.which("nix") is None:
        pytest.skip("Nix is required for real host recovery policy evaluation")
    expression = r"""
      let
        flake = builtins.getFlake (toString ./.);
        host = flake.nixosConfigurations.gc-05;
        lib = flake.inputs.nixpkgs.lib;
        summarize = c: {
          fallback = c.user.admin.passwordFallback.enable;
          file = c.user.admin.passwordFile;
          script = c.system.activationScripts.luxnixValidateAdminPasswordFile.text;
          deps = c.system.activationScripts.users.deps;
          validationDeps =
            c.system.activationScripts.luxnixValidateAdminPasswordFile.deps;
          passwordAuth = c.services.openssh.settings.PasswordAuthentication;
          keyCount = builtins.length c.users.users.admin.openssh.authorizedKeys.keys;
          failures = map (a: a.message)
            (builtins.filter (a: !a.assertion) c.assertions);
        };
        change = module:
          summarize (host.extendModules { modules = [ module ]; }).config;
      in {
        default = summarize host.config;
        recovery = change {
          user.admin.passwordFile = lib.mkForce "/var/lib/luxnix-recovery/admin.hash";
        };
        disabledPolicy = change {
          security.luxnix.local-users.enable = lib.mkForce false;
        };
        legacyFallback = change { user.admin.passwordFallback.enable = true; };
        policyFallback = change {
          security.luxnix.local-users.adminPassword.fallback.enable = true;
        };
        bypassValidation = change {
          security.luxnix.local-users.adminPassword.requireUsableFile = false;
        };
        passwordOverride = change { user.admin.extraOptions.hashedPassword = "!"; };
        storeFile = change {
          user.admin.passwordFile = lib.mkForce "/nix/store/forbidden.hash";
        };
        sops = change {
          security.luxnix.local-users.adminPassword = {
            source = "sops";
            sops.sopsFile = ./flake.lock;
          };
        };
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_gc05_secure_default_and_independent_ssh_recovery(recovery_policy):
    policy = recovery_policy["default"]
    assert policy["failures"] == []
    assert policy["fallback"] is False
    assert policy["passwordAuth"] is False
    assert policy["keyCount"] > 0
    assert "luxnixValidateAdminPasswordFile" in policy["deps"]
    # Upstream etc depends on users; depending on etc would create a cycle.
    assert "etc" not in policy["validationDeps"]
    assert "specialfs" in policy["validationDeps"]
    assert "install -d" not in policy["script"]


def test_explicit_unique_recovery_file_uses_same_checks(recovery_policy):
    policy = recovery_policy["recovery"]
    assert policy["file"] == "/var/lib/luxnix-recovery/admin.hash"
    assert policy["file"] in policy["script"]
    assert policy["failures"] == []
    assert policy["keyCount"] == recovery_policy["default"]["keyCount"]
    assert (
        "luxnixValidateAdminPasswordFile" in recovery_policy["disabledPolicy"]["deps"]
    )


@pytest.mark.parametrize(
    "case, message",
    [
        ("legacyFallback", "Shared admin password fallback is removed"),
        ("policyFallback", "Shared admin password fallback is removed"),
        ("bypassValidation", "validation cannot be disabled"),
        ("passwordOverride", "extraOptions must not override"),
        ("storeFile", "absolute runtime path outside the Nix store"),
    ],
)
def test_inconsistent_policy_fails_loudly(recovery_policy, case, message):
    assert any(message in failure for failure in recovery_policy[case]["failures"])


def test_sops_precedes_validation_and_user_activation(recovery_policy):
    policy = recovery_policy["sops"]
    assert policy["failures"] == []
    assert "setupSecretsForUsers" in policy["validationDeps"]
    assert "luxnixValidateAdminPasswordFile" in policy["deps"]


@pytest.fixture(scope="module")
def generated_hash():
    """Disposable test-only credential; never configured on an actual account."""
    return subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input="disposable-recovery-regression\n",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def run_validation(policy, tmp_path, content, metadata="0:600"):
    password_file = tmp_path / "admin.hash"
    if content is not None:
        password_file.write_text(content)
        password_file.chmod(0o600)
    script = policy["script"].replace(policy["file"], str(password_file))
    # Tests never chown or activate accounts. Stub only stat's metadata result;
    # file existence, content validation and failure behavior run as rendered.
    metadata_tool = tmp_path / "stat-metadata"
    metadata_tool.write_text(
        "#!/bin/sh\nprintf '%s\\n' " + shlex.quote(metadata) + "\n"
    )
    metadata_tool.chmod(0o700)
    script = re.sub(
        r"/nix/store/[^ /]+/bin/stat", shlex.quote(str(metadata_tool)), script
    )
    result = subprocess.run(["bash", "-c", script], text=True, capture_output=True)
    return result, password_file


@pytest.mark.parametrize("content", [None, "", "plaintext\n", "!\n", "$6$bad\n"])
def test_missing_or_unusable_secret_aborts_without_creating_fallback(
    recovery_policy, tmp_path, content
):
    result, path = run_validation(recovery_policy["default"], tmp_path, content)
    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert path.read_text() == content if content is not None else not path.exists()


@pytest.mark.parametrize("metadata", ["1000:600", "0:644", "0:660", "0:777"])
def test_untrusted_hash_permissions_are_rejected(
    recovery_policy, tmp_path, generated_hash, metadata
):
    result, path = run_validation(
        recovery_policy["default"], tmp_path, generated_hash + "\n", metadata
    )
    assert result.returncode != 0
    assert "root-owned" in result.stderr
    assert generated_hash not in result.stderr + result.stdout
    assert path.read_text() == generated_hash + "\n"


@pytest.mark.parametrize("metadata", ["0:400", "0:600"])
def test_valid_recovery_hash_is_accepted_unchanged(
    recovery_policy, tmp_path, generated_hash, metadata
):
    result, path = run_validation(
        recovery_policy["recovery"], tmp_path, generated_hash + "\n", metadata
    )
    assert result.returncode == 0, result.stderr
    assert path.read_text() == generated_hash + "\n"
    assert result.stdout == result.stderr == ""


def test_multiple_hash_lines_are_rejected(recovery_policy, tmp_path, generated_hash):
    content = generated_hash + "\n" + generated_hash + "\n"
    result, path = run_validation(recovery_policy["default"], tmp_path, content)
    assert result.returncode != 0
    assert path.read_text() == content
    assert generated_hash not in result.stdout + result.stderr


def test_preexisting_shared_fallback_is_rejected(recovery_policy, tmp_path):
    # Public retired credential, kept only as a rejection fixture.
    retired_hash = (
        "$6$yC9hyVoZEYLlzjbZ$pILBYLOZBlplgoYL9L.dyIKPGPrcW2ifd1I3ffRA"
        "YIwsv8B.pA76Eo6OUq71gJJKl8kGyBsmlbKwnGcKQEpoa."
    )
    result, path = run_validation(
        recovery_policy["default"], tmp_path, retired_hash + "\n"
    )
    assert result.returncode != 0
    assert "retired shared admin password" in result.stderr
    assert retired_hash not in result.stdout + result.stderr
    assert path.read_text() == retired_hash + "\n"
