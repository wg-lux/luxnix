"""Evaluate opt-in Secure Boot: hosts hold only the public fleet certificate."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = "/etc/luxnix/secure-boot/db.pem"


@pytest.fixture(scope="module")
def hosts():
    if shutil.which("nix") is None:
        pytest.skip("Nix evaluation required")
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = f.inputs.nixpkgs.lib;
        failed = c: map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
        inspect = name: let
          fleet = f.nixosConfigurations.${name};
          # Fleet default is operator passphrase unlock; Secure Boot is opt-in.
          system = fleet.extendModules { modules = [ { system.boot.secureBoot = lib.mkForce true; } ]; };
          c = system.config;
          extend = extra: (system.extendModules { modules = [ extra ]; }).config;
        in {
          fleetSecureBoot = fleet.config.system.boot.secureBoot;
          secureBoot = c.system.boot.secureBoot;
          lanzaboote = c.boot.lanzaboote.enable;
          publicKey = c.boot.lanzaboote.publicKeyFile;
          privateKey = c.boot.lanzaboote.privateKeyFile;
          systemdBoot = c.boot.loader.systemd-boot.enable;
          hook = builtins.readFile c.boot.loader.external.installHook;
          keyringBind = c.luxnix.storage.operatorUnlocked.bindMounts ? "/var/lib/sbctl";
          artifactScript = builtins.readFile (lib.getExe (builtins.head (builtins.filter (p: (p.name or "") == "luxnix-boot-artifacts") c.environment.systemPackages)));
          artifactTool = builtins.any (p: (p.name or "") == "luxnix-boot-artifacts")
            c.environment.systemPackages;
          etc = builtins.filter (lib.hasPrefix "luxnix/secure-boot/") (builtins.attrNames c.environment.etc);
          withAutoKeys = failed (extend { boot.lanzaboote.autoGenerateKeys.enable = true; });
          withInitrdSecrets = failed (extend { boot.initrd.secrets."/key" = null; });
          withoutStorage = failed (extend {
            luxnix.storage.operatorUnlocked.enable = lib.mkForce false;
          });
          disabled = let d = fleet.config; in {
            lanzaboote = d.boot.lanzaboote.enable;
            systemdBoot = d.boot.loader.systemd-boot.enable;
          };
        };
      in builtins.listToAttrs (map (name: { inherit name; value = inspect name; })
        [ "gc-02" "gc-10" ])
    """
    result = subprocess.run(
        ["nix", "eval", "--refresh", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("host", ["gc-02", "gc-10"])
def test_hosts_install_keyless_with_public_certificate_only(hosts, host):
    c = hosts[host]
    assert c["secureBoot"] and c["lanzaboote"] and not c["systemdBoot"]
    assert c["publicKey"] == CERTIFICATE
    assert c["privateKey"] == "/run/luxnix-secure-boot/no-private-key-on-host"
    assert not c["keyringBind"]
    assert c["artifactTool"]
    hook = c["hook"]
    assert f"--private-key={c['privateKey']}" in hook
    assert f"[ -e {c['privateKey']} ]" in hook
    assert f"devenv shell secure-boot-sign {host}" in hook
    assert "--allow-unsigned false" in hook
    if (ROOT / "conf/secure-boot/db.pem").is_file():
        # First deployment must verify before the new /etc tree is activated.
        assert "--public-key=/nix/store/" in hook
        assert "sbverify --cert /nix/store/" in hook
    # Installed stubs and loaders are re-verified after lzbt.
    assert hook.index("install_generations; then") < hook.index("sbverify --cert")


@pytest.mark.parametrize("host", ["gc-02", "gc-10"])
def test_fleet_default_leaves_secure_boot_disabled(hosts, host):
    assert hosts[host]["fleetSecureBoot"] is False


def test_public_files_follow_repository_provisioning(hosts):
    provisioned = (ROOT / "conf/secure-boot/db.pem").is_file()
    expected = sorted(
        f"luxnix/secure-boot/{n}" for n in ("db.pem", "PK.auth", "KEK.auth", "db.auth")
    )
    for host in hosts.values():
        assert sorted(host["etc"]) == (expected if provisioned else [])


def test_first_install_skips_unsigned_history_but_keeps_pending_and_signed(hosts, tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    esp = tmp_path / "esp"
    (esp / "EFI/Linux").mkdir(parents=True)
    for generation in (1, 2, 3):
        (profiles / f"system-{generation}-link").symlink_to("/nix/store/test-system")
    (profiles / "system").symlink_to("system-3-link")
    (esp / "EFI/Linux/nixos-generation-2-existing.efi").touch()
    hook = hosts["gc-10"]["hook"]
    selection = hook[hook.index("# Select the pending"):hook.index("install_generations()")]
    selection = selection.replace("/nix/var/nix/profiles", str(profiles)).replace("/boot/EFI", f"{esp}/EFI")
    result = subprocess.run(
        ["bash", "-euc", selection + '\nprintf "%s\\n" "${profiles[@]}"'],
        text=True, capture_output=True, check=True,
    )
    assert result.stdout.splitlines() == [str(profiles / "system-2-link"), str(profiles / "system-3-link")]


def test_controller_signing_contract_assertions(hosts):
    c = hosts["gc-02"]
    assert any("controller-held keys" in m for m in c["withAutoKeys"])
    assert any("boot.initrd.secrets" in m for m in c["withInitrdSecrets"])
    # Secure Boot no longer depends on operator-unlocked storage.
    assert not any("Secure Boot" in m for m in c["withoutStorage"])
    assert c["disabled"] == {"lanzaboote": False, "systemdBoot": True}


def test_enrollment_requires_signed_stub_for_current_generation(hosts, tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "system").symlink_to("system-3-link")
    esp = tmp_path / "esp"
    linux = esp / "EFI/Linux"
    linux.mkdir(parents=True)
    # Execute the actual preflight with a verifier that accepts only files
    # containing the marker; no firmware variables are accessed.
    verifier = tmp_path / "sbverify"
    verifier.write_text('#!/bin/sh\n[ "$(cat "$3")" = signed ]\n')
    verifier.chmod(0o755)
    hook = hosts["gc-10"]["artifactScript"]
    guard = hook[hook.index("# A signed loader alone"):hook.index("efivars=/sys/")]
    guard = guard.replace("/nix/var/nix/profiles", str(profiles)).replace("/boot/EFI", f"{esp}/EFI")
    env = {**os.environ, "PATH": f"{tmp_path}:" + os.environ["PATH"]}

    def check():
        return subprocess.run(["bash", "-eu", "-c", 'die() { exit 1; }\n' + guard], env=env).returncode

    assert check() != 0
    (linux / "nixos-generation-2-orphan.efi").write_text("signed")
    assert check() != 0
    stub = linux / "nixos-generation-3-current.efi"
    stub.write_text("unsigned")
    assert check() != 0
    stub.write_text("signed")
    assert check() == 0
