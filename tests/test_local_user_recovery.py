"""Evaluate real host policy and execute its validation snippet without activation."""

import hashlib
import json
import os
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
        flake = builtins.getFlake __REPO_FLAKE_URI__;
        host = flake.nixosConfigurations.gc-05;
        lib = flake.inputs.nixpkgs.lib;
        summarize = c: {
          fallback = c.user.admin.passwordFallback.enable;
          file = c.user.admin.passwordFile;
          script = c.system.activationScripts.luxnixValidateAdminPasswordFile.text;
          prepareScript = c.system.activationScripts.luxnixPrepareBootAccountHashes.text or "";
          deps = c.system.activationScripts.users.deps;
          validationDeps =
            c.system.activationScripts.luxnixValidateAdminPasswordFile.deps;
          clientScript =
            if c.system.activationScripts ? luxnixValidateClientPasswordFile
            then c.system.activationScripts.luxnixValidateClientPasswordFile else null;
          clientFile = c.user.client.hashedPasswordFile;
          clientSecret = builtins.hasAttr
            c.security.luxnix.local-users.clientPassword.sops.secretName c.sops.secrets;
          # Traverse the real dependency graph without rendering unrelated services.
          activationOrder = lib.textClosureList (lib.mapAttrs (name: value: {
            deps = value.deps or [];
            text = name;
          }) (builtins.removeAttrs c.system.activationScripts [ "script" ]))
            [ "users" ];
          passwordAuth = c.services.openssh.settings.PasswordAuthentication;
          keyCount = builtins.length c.users.users.admin.openssh.authorizedKeys.keys;
          failures = map (a: a.message)
            (builtins.filter (a: !a.assertion) c.assertions);
        };
        change = module:
          summarize (host.extendModules { modules = [ module ]; }).config;
      in {
        rotationTool = builtins.readFile (lib.getExe (builtins.head
          (builtins.filter (p: (p.name or "") == "luxnix-admin-password") host.config.environment.systemPackages)));
        vaultHash = host.config.luxnix.vault.adminPasswordHashedFile;
        vaultPassword = host.config.luxnix.vault.adminPasswordFile;
        default = summarize host.config;
        server = summarize flake.nixosConfigurations.s-03.config;
        disabledClient = summarize (flake.nixosConfigurations.s-03.extendModules {
          modules = [{ security.luxnix.local-users.clientPassword.source = "sops"; }];
        }).config;
        optionalClient = change {
          security.luxnix.local-users.clientPassword.requireUsableFile = false;
        };
        noClientFile = change {
          user.client.hashedPasswordFile = lib.mkForce null;
          users.mutableUsers = lib.mkForce true;
        };
        noPreparation = change {
          luxnix.storage.operatorUnlocked.migration.accountHashes = lib.mkForce {};
        };
        clientSops = change {
          security.luxnix.local-users.clientPassword = {
            source = "sops";
            sops.sopsFile = ./flake.lock;
          };
        };
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
        directAdminOverride = change { users.users.admin.hashedPasswordFile = lib.mkForce "/run/other.hash"; };
        directClientOverride = change { users.users.client-user.hashedPasswordFile = lib.mkForce "/run/other.hash"; };
        directClientHash = change { users.users.client-user.hashedPassword = lib.mkForce "!"; };
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
    expression = expression.replace(
        "__REPO_FLAKE_URI__", json.dumps(f"git+file://{ROOT}")
    )
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
        ("optionalClient", "Client password file validation cannot be disabled"),
        ("directAdminOverride", "direct user password overrides"),
        ("directClientOverride", "direct user password overrides"),
        ("directClientHash", "direct user password overrides"),
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


def run_validation(policy, tmp_path, content, metadata="0:600", current=None,
                   shadow_status=2, passwd_status=2):
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
    lookup = tmp_path / "getent-fixture"
    lookup.write_text(
        "#!/bin/sh\nif [ \"$3\" = shadow ]; then\n" + (
            "printf '%s\\n' " + shlex.quote(f"admin:{current}:1:0:99999:7:::") + "\n"
            if current is not None else f"exit {shadow_status}\n"
        ) + f"else exit {passwd_status}; fi\n"
    )
    lookup.chmod(0o700)
    script = re.sub(r"/nix/store/[^ /]+/bin/getent", shlex.quote(str(lookup)), script)
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


def test_preexisting_shared_fallback_is_rejected(recovery_policy, tmp_path, generated_hash):
    # The policy keeps only a SHA-256 fingerprint of the retired credential.
    # Substitute a disposable hash's fingerprint to exercise the same check.
    policy = dict(recovery_policy["default"])
    digests = re.findall(r"\b[0-9a-f]{64}\b", policy["script"])
    assert len(digests) == 1
    policy["script"] = policy["script"].replace(
        digests[0], hashlib.sha256(generated_hash.encode()).hexdigest()
    )
    result, path = run_validation(policy, tmp_path, generated_hash + "\n")
    assert result.returncode != 0
    assert "retired shared admin password" in result.stderr
    assert generated_hash not in result.stdout + result.stderr
    assert path.read_text() == generated_hash + "\n"


@pytest.mark.parametrize(
    "case", ["server", "disabledClient", "noClientFile"]
)
def test_absent_client_validation_does_not_create_partial_script(recovery_policy, case):
    policy = recovery_policy[case]
    assert policy["clientScript"] is None
    assert "luxnixValidateClientPasswordFile" not in policy["deps"]
    assert policy["clientSecret"] is False
    assert policy["activationOrder"][-1] == "users"
    assert policy["failures"] == []


def test_password_producers_precede_validators_and_account_updates(recovery_policy):
    for case in ("default", "clientSops"):
        policy = recovery_policy[case]
        client = policy["clientScript"]
        assert client["text"]
        assert "luxnixValidateClientPasswordFile" in policy["deps"]
        assert "etc" not in client["deps"]
        assert "luxnixPrepareBootAccountHashes" in client["deps"]
        assert "luxnixPrepareBootAccountHashes" in policy["validationDeps"]
        order = policy["activationOrder"]
        for validator in (
            "luxnixValidateAdminPasswordFile",
            "luxnixValidateClientPasswordFile",
        ):
            assert order.index("luxnixPrepareBootAccountHashes") < order.index(
                validator
            )
            assert order.index(validator) < order.index("users")
    assert recovery_policy["clientSops"]["clientSecret"] is True
    assert (
        "setupSecretsForUsers" in recovery_policy["clientSops"]["clientScript"]["deps"]
    )
    unprepared = recovery_policy["noPreparation"]
    assert "luxnixPrepareBootAccountHashes" not in unprepared["validationDeps"]
    assert "luxnixPrepareBootAccountHashes" not in unprepared["clientScript"]["deps"]
    assert unprepared["activationOrder"][-1] == "users"


@pytest.mark.parametrize("present", [False, True])
def test_client_validator_aborts_for_missing_or_empty_file(
    recovery_policy, tmp_path, present
):
    path = tmp_path / "client.hash"
    if present:
        path.touch()
    policy = recovery_policy["default"]
    script = policy["clientScript"]["text"].replace(policy["clientFile"], str(path))
    result = subprocess.run(["bash", "-c", script], text=True, capture_output=True)
    assert result.returncode != 0
    assert "Refusing activation" in result.stderr
    assert path.exists() == present


def test_client_validator_accepts_existing_hash_without_changing_shell_options(
    recovery_policy, tmp_path, generated_hash
):
    policy = recovery_policy["default"]
    adapted = {"script": policy["clientScript"]["text"], "file": policy["clientFile"]}
    result, path = run_validation(adapted, tmp_path, generated_hash + "\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert path.read_text() == generated_hash + "\n"


def test_activation_never_invokes_the_interactive_tool(recovery_policy):
    for script in [recovery_policy["default"]["script"],
                   recovery_policy["default"]["clientScript"]["text"]]:
        assert not re.search(r"/nix/store/[^ /]+/bin/luxnix-admin-password", script)
        assert "systemd-ask-password" not in script


@pytest.mark.parametrize("action", ["switch", "test", "boot", ""])
def test_missing_hash_never_prompts_or_mutates_during_activation(
    recovery_policy, tmp_path, monkeypatch, action
):
    monkeypatch.setenv("NIXOS_ACTION", action)
    policy = recovery_policy["default"]
    assert "LUXNIX_ADMIN_PASSWORD_FROM_ACTIVATION=1" not in policy["script"]
    result, path = run_validation(policy, tmp_path, None)
    assert result.returncode != 0
    assert not path.exists()
    assert "explicit account recovery" in result.stderr


@pytest.mark.parametrize("content", ["!\n", "plaintext\n", "$6$bad\n"])
def test_client_rejects_malformed_hash(recovery_policy, tmp_path, content):
    policy = recovery_policy["default"]
    adapted = {"script": policy["clientScript"]["text"], "file": policy["clientFile"]}
    result, path = run_validation(adapted, tmp_path, content)
    assert result.returncode != 0
    assert path.read_text() == content


def test_preparation_failure_aborts_before_user_updates(recovery_policy):
    script = recovery_policy["default"]["prepareScript"]
    command = script.partition(" accounts")[0] + " accounts"
    # NixOS records ERR but does not enable errexit for activation snippets.
    script = "trap '_status=1' ERR\n" + script.replace(command, "false", 1)
    result = subprocess.run(
        ["bash", "-c", script + "\nprintf USER_UPDATE_REACHED"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "USER_UPDATE_REACHED" not in result.stdout


@pytest.mark.parametrize("user", ["admin", "client"])
@pytest.mark.parametrize("current", ["same", "!", "!!", "*", "other"])
def test_existing_password_never_changes_implicitly(recovery_policy, tmp_path, generated_hash, user, current):
    policy = recovery_policy["default"]
    if user == "client":
        policy = {"script": policy["clientScript"]["text"], "file": policy["clientFile"]}
    live = generated_hash if current == "same" else current
    result, path = run_validation(policy, tmp_path, generated_hash, current=live)
    assert (result.returncode == 0) == (current == "same")
    assert generated_hash not in result.stdout + result.stderr
    assert path.read_text() == generated_hash
    if current != "same":
        assert "refusing automatic password change" in result.stderr


@pytest.mark.parametrize("shadow_status,passwd_status", [(1, 2), (2, 0), (2, 1)])
def test_shadow_lookup_failure_cannot_masquerade_as_new_account(
    recovery_policy, tmp_path, generated_hash, shadow_status, passwd_status
):
    result, _ = run_validation(recovery_policy["default"], tmp_path, generated_hash,
                               shadow_status=shadow_status, passwd_status=passwd_status)
    assert result.returncode != 0


@pytest.mark.parametrize("entry", ["cancel", "mismatch", "short", "valid"])
def test_local_rotation_requires_password_entry_before_any_write(recovery_policy, tmp_path, entry):
    """Run the built tool, replacing only prompts, privilege and live chpasswd."""
    files = [tmp_path / name for name in ("boot.hash", "vault.hash", "vault.password")]
    for path in files:
        path.write_text("unchanged")
    script = recovery_policy["rotationTool"]
    for source, target in zip(
        [recovery_policy["default"]["file"], recovery_policy["vaultHash"], recovery_policy["vaultPassword"]], files
    ):
        script = script.replace(source, str(target))
    commands = tmp_path / "commands"
    commands.mkdir()
    marker = tmp_path / "applied.hash"
    counter = tmp_path / "prompt-count"
    synthetic = "synthetic entered password"
    prompt = f'''#!/bin/sh
n=$(cat {shlex.quote(str(counter))} 2>/dev/null || printf 0)
n=$((n + 1)); printf '%s' "$n" > {shlex.quote(str(counter))}
'''
    prompt += {
        "cancel": "exit 1\n",
        "mismatch": "printf 'synthetic mismatched password %s' \"$n\"\n",
        "short": "printf short\n",
        "valid": "printf '%s' " + shlex.quote(synthetic) + "\n",
    }[entry]
    for name, body in {
        "systemd-ask-password": prompt,
        "id": "#!/bin/sh\nprintf '0\\n'\n",
        "chown": "#!/bin/sh\nexit 0\n",
        "chpasswd": "#!/bin/sh\ncat > " + shlex.quote(str(marker)) + "\n",
    }.items():
        path = commands / name
        path.write_text(body)
        path.chmod(0o700)
    # Keep the actual pinned runtime tools after the narrow test doubles.
    script = script.replace('export PATH="', 'export PATH="' + str(commands) + ':', 1)
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                            env={**os.environ, "LUXNIX_ADMIN_PASSWORD_FROM_ACTIVATION": "1"}, timeout=30)
    assert (result.returncode == 0) == (entry == "valid"), result.stderr
    assert marker.exists() == (entry == "valid")
    assert synthetic not in result.stdout + result.stderr
    if entry == "valid":
        assert files[0].read_text().startswith("$6$")
        assert marker.read_text().split(":", 1)[1] == files[0].read_text()
    else:
        assert all(path.read_text() == "unchanged" for path in files)
