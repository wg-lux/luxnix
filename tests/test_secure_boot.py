"""Evaluate fleet Secure Boot: hosts hold only the public fleet certificate."""

import json
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
          system = f.nixosConfigurations.${name};
          c = system.config;
          extend = extra: (system.extendModules { modules = [ extra ]; }).config;
        in {
          secureBoot = c.system.boot.secureBoot;
          lanzaboote = c.boot.lanzaboote.enable;
          publicKey = c.boot.lanzaboote.publicKeyFile;
          privateKey = c.boot.lanzaboote.privateKeyFile;
          systemdBoot = c.boot.loader.systemd-boot.enable;
          hook = builtins.readFile c.boot.loader.external.installHook;
          keyringBind = c.luxnix.storage.operatorUnlocked.bindMounts ? "/var/lib/sbctl";
          artifactTool = builtins.any (p: (p.name or "") == "luxnix-boot-artifacts")
            c.environment.systemPackages;
          etc = builtins.filter (lib.hasPrefix "luxnix/secure-boot/") (builtins.attrNames c.environment.etc);
          withAutoKeys = failed (extend { boot.lanzaboote.autoGenerateKeys.enable = true; });
          withInitrdSecrets = failed (extend { boot.initrd.secrets."/key" = null; });
          withoutStorage = failed (extend {
            luxnix.storage.operatorUnlocked.enable = lib.mkForce false;
          });
          disabled = let d = extend { system.boot.secureBoot = lib.mkForce false; }; in {
            lanzaboote = d.boot.lanzaboote.enable;
            systemdBoot = d.boot.loader.systemd-boot.enable;
          };
        };
      in builtins.listToAttrs (map (name: { inherit name; value = inspect name; })
        [ "gc-02" "gc-10" ])
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
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
    # Installed stubs and loaders are re-verified after lzbt.
    assert hook.index("install_generations; then") < hook.index("sbverify --cert")


def test_public_files_follow_repository_provisioning(hosts):
    provisioned = (ROOT / "conf/secure-boot/db.pem").is_file()
    expected = sorted(
        f"luxnix/secure-boot/{n}" for n in ("db.pem", "PK.auth", "KEK.auth", "db.auth")
    )
    for host in hosts.values():
        assert sorted(host["etc"]) == (expected if provisioned else [])


def test_controller_signing_contract_assertions(hosts):
    c = hosts["gc-02"]
    assert any("controller-held keys" in m for m in c["withAutoKeys"])
    assert any("boot.initrd.secrets" in m for m in c["withInitrdSecrets"])
    # Secure Boot no longer depends on operator-unlocked storage.
    assert not any("Secure Boot" in m for m in c["withoutStorage"])
    assert c["disabled"] == {"lanzaboote": False, "systemdBoot": True}
