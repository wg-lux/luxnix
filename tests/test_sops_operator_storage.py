"""sops-nix on operator storage: one storage prompt, then automatic startup."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

EXPRESSION = r"""
repo:
let
  f0 = builtins.getFlake ("git+file://" + repo);
  f = f0 // { nixosConfigurations = builtins.mapAttrs (_: h: h.extendModules {
    modules = [{ luxnix.storage.operatorUnlocked.layout = "legacy-containers"; }];
  }) f0.nixosConfigurations; };
  host = f.nixosConfigurations.gc-10;
  lib = f.inputs.nixpkgs.lib;
  # flake.lock stands in for ciphertext; evaluation never decrypts it.
  ciphertext = /. + "${repo}/flake.lock";
  withKey = state: extra: (host.extendModules { modules = [ ({
    security.sops.operatorStorageKey = {
      enable = true;
      secretsFile = ciphertext;
      applicationSecrets.SCRT_example = { };
      consumers = [ "lx-annotate.service" ];
      volumeKeys.luxnix-app-storage = state;
    };
  }) extra ]; }).config;
  enabled = withKey "active";
  staged = withKey "staged" { };
  failures = c: map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
  pick = c: let s = c.systemd.services; in {
    failures = failures c;
    sops = {
      inherit (s.sops-install-secrets) wantedBy before after requiredBy;
      mounts = s.sops-install-secrets.unitConfig.RequiresMountsFor;
    };
    app = { inherit (s.luxnix-storage-unlock-luxnix-app-storage) requires before after; };
    secrets = { inherit (s.luxnix-storage-unlock-luxnix-secrets) before after; };
    consumer = s.lx-annotate.requires;
    keys = { age = c.sops.age.sshKeyPaths; gpg = c.sops.gnupg.sshKeyPaths; file = c.sops.age.keyFile; };
    examplePath = c.sops.secrets.SCRT_example.path;
  };
in {
  default = { keys = host.config.sops.age.sshKeyPaths; failures = failures host.config; };
  enabled = pick (enabled { });
  staged = {
    failures = failures staged;
    keyFile = staged.luxnix.storage.operatorUnlocked.volumes.luxnix-app-storage.keyFile;
    appBefore = staged.systemd.services.luxnix-storage-unlock-luxnix-app-storage.before;
    volumeKey = staged.sops.secrets.volume-key-luxnix-app-storage.path;
  };
  # A bogus repository must never be fetched while the host uses no sops secret.
  lazy = let c = (host.extendModules { modules = [ {
    security.sops.operatorStorageKey = {
      enable = true;
      secretsRepository = { url = "ssh://git@invalid.example/none.git"; rev = "0000000000000000000000000000000000000001"; };
    };
  } ]; }).config; in {
    drv = c.system.build.toplevel.drvPath;
    ssh = c.programs.ssh.extraConfig;
    github = c.programs.ssh.knownHosts."github.com".publicKey;
  };
  keyVolume = failures (withKey "staged" {
    security.sops.operatorStorageKey.volumeKeys.luxnix-secrets = "active";
  });
  notSops = failures (enabled {
    luxnix.storage.operatorUnlocked.volumes.luxnix-app-storage.keyFile = lib.mkForce "/run/other";
  });
  circular = failures (enabled {
    security.sops.operatorStorageKey.volume = lib.mkForce "luxnix-app-storage";
  });
  account = failures (enabled {
    security.sops.operatorStorageKey.applicationSecrets.SCRT_client_user_password_hash = { };
  });
  lxAnnotate = let
    c = enabled { services.luxnix.lxAnnotateLocal.runtime.sopsMasterKey.enable = true; };
    s = c.systemd.services;
  in {
    failures = failures c;
    secret = { inherit (c.sops.secrets.lx_annotate_master_key) path owner mode sopsFile; };
    serviceUser = c.users.users.endoreg-service-user.name;
    env = map (u: s.${u}.environment.LX_ANNOTATE_MASTER_KEY_FILE) [ "lx-annotate" "lx-annotate-master-key-check" ];
    inlineKey = s.lx-annotate.environment ? LX_ANNOTATE_MASTER_KEY;
    requires = map (u: s.${u}.requires) [ "lx-annotate" "lx-annotate-master-key-check" ];
    generated = c.roles.managed-secrets.customSecrets ? lx_annotate_master_key_local;
    mounts = s.sops-install-secrets.unitConfig.RequiresMountsFor;
  };
  lxAnnotateWithoutSops = failures (host.extendModules { modules = [ {
    services.luxnix.lxAnnotateLocal.runtime.sopsMasterKey.enable = true;
  } ]; }).config;
}
"""


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory):
    if shutil.which("nix") is None:
        pytest.skip("Nix evaluation required")
    expression = tmp_path_factory.mktemp("sops") / "eval.nix"
    expression.write_text(EXPRESSION)
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", f'import {expression} "{ROOT}"'],
        cwd=ROOT, text=True, capture_output=True, timeout=500,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_default_hosts_are_unchanged(evaluated):
    assert evaluated["default"]["failures"] == []
    assert evaluated["default"]["keys"] == ["/etc/ssh/ssh_host_ed25519_key"]


def test_secrets_install_after_the_single_prompt(evaluated):
    c = evaluated["enabled"]
    assert c["failures"] == []
    # Only the first volume prompts and holds back the login screen.
    assert "display-manager.service" in c["secrets"]["before"]
    assert "luxnix-storage-unlock-luxnix-app-storage.service" not in c["secrets"]["after"]
    # sops runs as a normal service after that unlock, never in sysinit.
    assert c["sops"]["wantedBy"] == ["multi-user.target"]
    assert c["sops"]["before"] == [] and c["sops"]["requiredBy"] == []
    assert "luxnix-storage-unlock-luxnix-secrets.service" in c["sops"]["after"]
    assert set(c["sops"]["mounts"]) == {"/etc/secrets/vault", "/var/lib/luxnix-secrets/sops-age/keys.txt"}
    # Application storage opens from the installed key without blocking login.
    assert c["app"]["requires"] == ["sops-install-secrets.service"]
    assert {"sops-install-secrets.service", "luxnix-storage-unlock-luxnix-secrets.service"} <= set(c["app"]["after"])
    assert c["app"]["before"] == []
    assert "sops-install-secrets.service" in c["consumer"]
    assert c["examplePath"] == "/etc/secrets/vault/SCRT_example"


def test_staged_volume_key_is_installed_but_volume_still_prompts(evaluated):
    c = evaluated["staged"]
    assert c["failures"] == []
    assert c["keyFile"] is None
    assert "display-manager.service" in c["appBefore"]
    assert c["volumeKey"] == "/run/secrets/volume-key-luxnix-app-storage"


def test_no_offline_readable_identity_decrypts(evaluated):
    keys = evaluated["enabled"]["keys"]
    assert keys["age"] == [] and keys["gpg"] == []
    assert keys["file"] == "/var/lib/luxnix-secrets/sops-age/keys.txt"


@pytest.mark.parametrize(
    "case, message",
    [
        ("notSops", "path of a declared sops-nix secret"),
        ("circular", "cannot hold its own sops key"),
        ("account", "must not be sops application secrets"),
        ("keyVolume", "never the age key volume"),
        ("lxAnnotateWithoutSops", "runtime.sopsMasterKey requires security.sops.operatorStorageKey"),
    ],
)
def test_unsafe_configurations_fail_evaluation(evaluated, case, message):
    assert any(message in failure for failure in evaluated[case])


def test_lx_annotate_reads_its_storage_key_from_sops(evaluated):
    c = evaluated["lxAnnotate"]
    assert c["failures"] == []
    # The default sops-nix path is a regular ramfs file, so the gate's
    # non-symlink check holds; only the service user may read it.
    key = "/run/secrets/lx_annotate_master_key"
    assert c["secret"]["path"] == key
    assert c["secret"]["owner"] == c["serviceUser"]
    assert c["secret"]["mode"] == "0400"
    assert c["secret"]["sopsFile"].endswith("flake.lock")
    # The application receives a file handle, never the key value itself.
    assert c["env"] == [key, key]
    assert c["inlineKey"] is False
    assert all("sops-install-secrets.service" in r for r in c["requires"])
    assert c["generated"] is False
    assert "/run/secrets" not in c["mounts"]


def test_sync_secrets_skips_names_owned_by_sops():
    play = yaml.safe_load((ROOT / "ansible/playbooks/deploy_secrets.yml").read_text())[0]
    tasks = {task["name"]: task for task in play["tasks"]}
    read = tasks["Read export names migrated to sops-nix"]["ansible.builtin.command"]["argv"]
    assert any("security.sops.operatorStorageKey.applicationSecrets" in arg for arg in read)
    deploy = tasks["Deploy secrets individually"]
    assert "sops_migrated_secrets" in deploy["when"]
    assert deploy["no_log"] is True


def test_secrets_repository_is_fetched_only_for_hosts_using_it(evaluated):
    lazy = evaluated["lazy"]
    assert lazy["drv"].endswith(".drv")
    assert "Match localuser root host github.com" in lazy["ssh"]
    assert "IdentityFile /root/.ssh/luxnix-secrets-deploy" in lazy["ssh"]
    assert lazy["github"].startswith("ssh-ed25519 ")
