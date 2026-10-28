"""Evaluate the generated hosts: inventory overrides must not drop mount guards."""

import json
import os
import re
import shlex
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECRETS = "/var/lib/luxnix-secrets"
APPLICATION = "/var/lib/lx-annotate"
DATABASE = "/var/lib/postgresql"
RECOVERY = APPLICATION + "/data/.identity-salt-recovery"
PRIVATE = [
    "/etc/secrets/vault",
    "/var/lib/lx-annotate-identity-salts",
    RECOVERY,
    "/var/endoreg-service-user/lx-annotate-wheel/conf",
]


@pytest.fixture(scope="module")
def hosts():
    if shutil.which("nix") is None:
        pytest.skip("Nix evaluation required")
    expression = r'''
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        inspect = name: inspectConfig f.nixosConfigurations.${name}.config;
        inspectConfig = c: {
          mounts = builtins.mapAttrs (_: v: {
            inherit (v) device options depends;
          }) c.fileSystems;
          services = builtins.mapAttrs (_: v: {
            inherit (v) bindsTo unitConfig requires after;
          }) (f.inputs.nixpkgs.lib.filterAttrs (n: _: builtins.elem n [
            "vault-auth-setup" "managed-secrets-setup" "lx-annotate-identity-salts"
            "lx-annotate-runtime-env" "postgresql" "postgresql-setup"
            "postgres-endoreg-setup" "luxnix-vault-issue-hub-client-certificate"
            "lx-annotate" "lx-annotate-celery-hub-transfer-worker" "postgresqlBackup"
          ]) c.systemd.services);
          checks = builtins.mapAttrs (_: v: {
            inherit (v) serviceConfig unitConfig;
          }) (f.inputs.nixpkgs.lib.filterAttrs
            (n: _: f.inputs.nixpkgs.lib.hasPrefix "luxnix-storage-check-" n)
            c.systemd.services);
          helper = if c.luxnix.storage.operatorUnlocked.enable then
            let p = builtins.head (builtins.filter (p: (p.name or "") == "luxnix-operator-storage") c.environment.systemPackages);
            in { derivation = p.drvPath; output = p.outPath; } else null;
          adminHash = c.user.admin.passwordFile;
          accountHashes = builtins.filter (path: path != null) (map (u: u.hashedPasswordFile) (builtins.attrValues c.users.users));
          migration = c.luxnix.storage.operatorUnlocked.migration.enable;
          unlockMethod = c.luxnix.storage.operatorUnlocked.unlockMethod;
          unlockTimeout = c.systemd.services.luxnix-storage-unlock-luxnix-app-storage.serviceConfig.TimeoutStartSec;
          unlockBoot = builtins.mapAttrs (_: v: { inherit (v) wantedBy before after; })
            (f.inputs.nixpkgs.lib.filterAttrs (n: _: f.inputs.nixpkgs.lib.hasPrefix "luxnix-storage-unlock-" n)
            c.systemd.services);
          enabled = c.luxnix.storage.operatorUnlocked.enable;
          storageUnits = builtins.filter (n: f.inputs.nixpkgs.lib.hasPrefix "luxnix-storage-" n)
            (builtins.attrNames c.systemd.services);
          copiesAccountHashes = c.system.activationScripts ? luxnixPrepareBootAccountHashes;
          startup = c.luxnix.storage.operatorUnlocked.startupServices;
          workerBoot = builtins.attrNames (f.inputs.nixpkgs.lib.filterAttrs (n: v:
            f.inputs.nixpkgs.lib.hasPrefix "lx-annotate-celery-" n && builtins.elem "multi-user.target" v.wantedBy
          ) c.systemd.services);
          assertions = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
          swapDevices = map (v: v.device) c.swapDevices;
          generator = c.systemd.generators.systemd-gpt-auto-generator or null;
          sleep = c.systemd.sleep.settings.Sleep;
        };
      in builtins.listToAttrs (map (name: { inherit name; value = inspect name; })
        [ "gc-09" "gc-10" "gc-08" ])
        # Unattended start is only reachable through the TPM unlock path.
        // { "gc-10-tpm2" = inspectConfig (f.nixosConfigurations.gc-10.extendModules { modules = [{
          luxnix.storage.operatorUnlocked.unlockMethod = f.inputs.nixpkgs.lib.mkForce "tpm2";
        }]; }).config; }
        // { "gc-09-local-openbao" = inspectConfig (f.nixosConfigurations.gc-09.extendModules { modules = [{
          luxnix.storage.operatorUnlocked.unlockMethod = f.inputs.nixpkgs.lib.mkForce "local-openbao";
          luxnix.openbao.local.seal = f.inputs.nixpkgs.lib.mkForce "tpm";
        }]; }).config; }
    '''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, text=True, capture_output=True, timeout=240,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("host", ["gc-09", "gc-10"])
def test_mounts_and_startup_guards_survive_inventory_merging(hosts, host):
    c = hosts[host]
    mounts = c["mounts"]
    assert c["assertions"] == []
    assert c["adminHash"] == "/var/lib/luxnix-account/admin-password.hash"
    assert set(c["accountHashes"]) == {c["adminHash"], "/var/lib/luxnix-account/client-password.hash"}
    assert {"lx-annotate", *c["workerBoot"]} <= set(c["startup"])
    assert c["migration"] == (host != "gc-10")
    for root in [SECRETS, "/var/lib/luxnix-app-storage"]:
        assert mounts[root]["device"] == "/dev/mapper/" + root.rsplit("/", 1)[1]
        assert "noauto" in mounts[root]["options"]
    for path in PRIVATE + [APPLICATION, DATABASE]:
        assert "bind" in mounts[path]["options"]
        assert "noauto" in mounts[path]["options"]
    assert mounts["/etc/secrets"]["device"] == SECRETS + "/host-secrets"
    assert "/etc/secrets" in mounts["/etc/secrets/vault"]["depends"]
    assert mounts["/var/backup/postgresql"]["device"] == "/var/lib/luxnix-app-storage/postgresql-backups"
    assert APPLICATION in mounts[RECOVERY]["depends"]
    assert SECRETS in mounts[RECOVERY]["depends"]
    guards = {
        "postgresqlBackup": [DATABASE, "/var/backup/postgresql"],
        "vault-auth-setup": ["/etc/secrets", PRIVATE[0]],
        "managed-secrets-setup": [PRIVATE[0]],
        "lx-annotate-identity-salts": PRIVATE[:3],
        "lx-annotate-runtime-env": PRIVATE + [APPLICATION, DATABASE],
        "postgresql": [DATABASE],
        "postgresql-setup": [DATABASE],
        "postgres-endoreg-setup": [DATABASE],
        "luxnix-vault-issue-hub-client-certificate": [PRIVATE[0], APPLICATION],
        "lx-annotate": [APPLICATION],
        "lx-annotate-celery-hub-transfer-worker": [APPLICATION],
    }
    if host == "gc-10":
        pki = APPLICATION + "/hub-pki"
        assert mounts[pki]["device"] == SECRETS + "/hub-client-pki"
        assert {SECRETS, APPLICATION} <= set(mounts[pki]["depends"])
        for service in ["luxnix-vault-issue-hub-client-certificate", "lx-annotate",
                        "lx-annotate-celery-hub-transfer-worker"]:
            guards[service].append(pki)
    for service, paths in guards.items():
        unit = c["services"][service]
        check_name = "luxnix-storage-check-" + service
        assert check_name + ".service" in unit["requires"]
        assert check_name + ".service" in unit["after"]
        check = c["checks"][check_name]
        assert check["serviceConfig"]["User"] == "root"
        assert not check["serviceConfig"].get("RemainAfterExit", False)
        assert "secret_storage.py" in check["serviceConfig"]["ExecStart"]
        assert "--allow-runtime" not in check["serviceConfig"]["ExecStart"]
        assert "systemd-tmpfiles --create" in check["serviceConfig"]["ExecStartPost"]
        for path in paths:
            assert path in check["serviceConfig"]["ExecStart"]
            assert "--prefix=" + path in check["serviceConfig"]["ExecStartPost"]
            assert path in check["unitConfig"]["AssertPathIsMountPoint"]
        for path in paths:
            assert path in unit["unitConfig"]["RequiresMountsFor"], (host, service, path)
            assert path in unit["unitConfig"]["AssertPathIsMountPoint"], (host, service, path)
            escaped = path.lstrip("/").replace("-", r"\x2d").replace("/", "-")
            assert escaped + ".mount" in unit["bindsTo"], (host, service, path)
    assert c["swapDevices"] == []
    assert c["generator"] == "/dev/null"
    for setting in ["AllowHibernation", "AllowHybridSleep", "AllowSuspendThenHibernate"]:
        assert c["sleep"][setting] is False


def test_host_specific_storage_and_unselected_host(hosts):
    assert "/data/raid01" not in hosts["gc-09"]["mounts"]["/var/lib/luxnix-app-storage"]["depends"]
    assert SECRETS in hosts["gc-08"]["mounts"]
    assert hosts["gc-08"]["migration"]


def test_gc10_uses_fleet_unlock_migration_and_boot_account_hashes(hosts):
    c = hosts["gc-10"]
    assert c["enabled"] and not c["migration"]
    assert c["unlockMethod"] == "passphrase"
    # Operator unlock waits for the passphrase; the 90s bound applies to TPM unlock.
    assert c["unlockTimeout"] == "infinity"
    assert hosts["gc-10-tpm2"]["unlockTimeout"] == "90s"
    # The operator answers the boot prompt; no manual start command is needed.
    secrets = c["unlockBoot"]["luxnix-storage-unlock-luxnix-secrets"]
    app = c["unlockBoot"]["luxnix-storage-unlock-luxnix-app-storage"]
    for unit in (secrets, app):
        assert unit["wantedBy"] == ["multi-user.target"]
        assert {"display-manager.service", "plymouth-quit.service", "plymouth-quit-wait.service"} <= set(unit["before"])
    # Serialized prompts let a shared passphrase be entered once.
    assert "luxnix-storage-unlock-luxnix-app-storage.service" in secrets["after"]
    assert "luxnix-storage-unlock-luxnix-secrets.service" not in app["after"]
    for unit in hosts["gc-10-tpm2"]["unlockBoot"].values():
        assert unit["wantedBy"] == [] and unit["before"] == []
    assert {
        "luxnix-storage-unlock-luxnix-secrets",
        "luxnix-storage-unlock-luxnix-app-storage",
    } <= set(c["storageUnits"])
    assert "luxnix-storage-migrate" not in c["storageUnits"]
    assert c["copiesAccountHashes"]
    assert c["helper"] is not None
    assert "/data/raid01" in c["mounts"]["/var/lib/luxnix-app-storage"]["depends"]


@pytest.mark.parametrize("profile", ["gc-10-tpm2", "gc-09-local-openbao"])
def test_endoreg_role_rejects_unaccepted_unattended_unlock(hosts, profile):
    assert (
        "EndoReg unattended unlock is blocked until authenticated system and application runtime acceptance is implemented."
        in hosts[profile]["assertions"]
    )


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_generic_module_layout_merging_and_invalid_configuration():
    expression = r'''
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = f.inputs.nixpkgs.lib;
        evaluate = additions: (lib.nixosSystem {
          system = "x86_64-linux";
          modules = [ ./modules/nixos/luxnix/operator-unlocked-storage {
            system.stateVersion = "26.05";
            boot.loader.grub.enable = false;
            fileSystems."/" = { device = "none"; fsType = "tmpfs"; };
            systemd.services.consumer = {
              script = "true";
              after = [ "network.target" ];
              serviceConfig.PrivateDevices = true;
            };
            luxnix.storage.operatorUnlocked = {
              enable = true;
              volumes.archive = { mountPoint = "/srv/private"; noexec = true; };
              bindMounts = {
                "/srv/app" = { volume = "archive"; directory = "application"; };
                "/srv/app/identity" = { volume = "archive"; directory = "identity"; };
              };
              guardedServices.consumer = [ "/srv/app" ];
            };
          } ] ++ additions;
        }).config;
        preservedSwap = evaluate [{ swapDevices = [{ device = "/dev/disk/by-label/encrypted-swap"; randomEncryption.enable = true; }]; }];
        nested = evaluate [{ luxnix.storage.operatorUnlocked.volumes.child.mountPoint = "/srv/private/child"; }];
        c = evaluate [{ luxnix.storage.operatorUnlocked.guardedServices.consumer = [ "/srv/private" ]; }];
        failed = extra: map (a: a.message) (builtins.filter (a: !a.assertion) (evaluate [extra]).assertions);
        checked = extra: builtins.tryEval (builtins.deepSeq (evaluate [extra]).fileSystems true);
        disabled = evaluate [{ luxnix.storage.operatorUnlocked.enable = lib.mkForce false; }];
      in {
        mounts = builtins.mapAttrs (_: v: { inherit (v) device depends options; }) c.fileSystems;
        consumer = { inherit (c.systemd.services.consumer) after requires bindsTo unitConfig; };
        check = c.systemd.services.luxnix-storage-check-consumer.serviceConfig;
        swap = map (v: { inherit (v) device randomEncryption; }) preservedSwap.swapDevices;
        generator = c.systemd.generators.systemd-gpt-auto-generator or null;
        nestedDepends = nested.fileSystems."/srv/private/child".depends;
        missingService = failed { luxnix.storage.operatorUnlocked.guardedServices.typo = [ "/srv/app" ]; };
        disabledService = failed { systemd.services.consumer.enable = false; };
        missingStartup = failed { luxnix.storage.operatorUnlocked.startupServices = [ "typo" ]; };
        independentTpm = failed { luxnix.storage.operatorUnlocked = { unlockMethod = "tpm2"; migration.enable = false; }; };
        valid = builtins.all (a: a.assertion) c.assertions;
        disabledMounts = builtins.attrNames disabled.fileSystems;
        disabledServices = builtins.attrNames disabled.systemd.services;
        unknownVolume = failed { luxnix.storage.operatorUnlocked.bindMounts."/srv/other" = { volume = "missing"; directory = "data"; }; };
        unknownGuard = failed { luxnix.storage.operatorUnlocked.guardedServices.mistake = [ "/srv/typo" ]; };
        duplicate = failed { luxnix.storage.operatorUnlocked.volumes.second.mountPoint = "/srv/private"; };
        invalidTarget = failed { luxnix.storage.operatorUnlocked.bindMounts."/srv/../bad" = { volume = "archive"; directory = "data"; }; };
        cycle = failed { luxnix.storage.operatorUnlocked.volumes.archive.depends = [ "/srv/app" ]; };
        traversal = checked { luxnix.storage.operatorUnlocked.bindMounts."/srv/app".directory = lib.mkForce "../outside"; };
        rawDevice = checked { luxnix.storage.operatorUnlocked.volumes.archive.device = "/dev/sda"; };
      }
    '''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT, text=True, capture_output=True, timeout=240,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["valid"]
    assert data["swap"][0]["device"] == "/dev/disk/by-label/encrypted-swap"
    assert data["swap"][0]["randomEncryption"]["enable"]
    assert data["generator"] != "/dev/null"
    assert "/srv/private" in data["nestedDepends"]
    assert "secret_storage.py" in data["check"]["ExecStart"]
    assert "systemd-tmpfiles --create" in data["check"]["ExecStartPost"]
    assert data["mounts"]["/srv/private"]["device"] == "/dev/mapper/archive"
    assert {"/srv/private", "/srv/app"} <= set(data["mounts"]["/srv/app/identity"]["depends"])
    assert "noexec" in data["mounts"]["/srv/app"]["options"]
    assert "network.target" in data["consumer"]["after"]
    assert {"/srv/app", "/srv/app/identity", "/srv/private"} <= set(data["consumer"]["unitConfig"]["RequiresMountsFor"])
    assert data["check"]["User"] == "root"
    assert not data["check"].get("PrivateDevices", False)
    assert data["disabledMounts"] == ["/"]
    assert "luxnix-storage-check-consumer" not in data["disabledServices"]
    assert data["independentTpm"] == []
    for invalid in ["unknownVolume", "unknownGuard", "duplicate", "invalidTarget", "cycle", "missingService", "missingStartup", "disabledService"]:
        assert data[invalid], invalid
    assert not data["traversal"]["success"]
    assert not data["rawDevice"]["success"]


@pytest.mark.parametrize("profile", ["gc-10", "gc-10-tpm2"])
@pytest.mark.parametrize("mismatch", [False, True])
def test_packaged_start_preserves_healthy_services_and_rejects_wrong_mapping(hosts, tmp_path, mismatch, profile):
    """Execute the packaged CLI with device/systemctl probes isolated from the host."""
    helper = hosts[profile]["helper"]
    result = subprocess.run(
        ["nix", "build", "--no-link", helper["derivation"] + "^out"],
        capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stderr
    mocks = tmp_path / "commands"
    mocks.mkdir()
    scripts = {
        "id": "echo 0",
        "systemd-tty-ask-password-agent": 'printf "%s\\n" "$@" > "$AGENT_LOG"',
        "realpath": 'printf "%s\\n" "$2"',
        "systemctl": '''if [ "$PASSPHRASE" = 1 ]; then
  for i in 1 2 3 4 5; do [ -f "$AGENT_LOG" ] && break; sleep 0.1; done
  [ -f "$AGENT_LOG" ] || exit 98
fi
printf "%s\\n" "$@" >> "$CALL_LOG"''',
        "cryptsetup": '''[ "$1" = status ] || exit 99
if [ "$MISMATCH" = 1 ]; then
  echo "loop: /wrong-container"
elif [ "$2" = luxnix-app-storage ]; then
  echo "loop: /data/raid01/luxnix-app-storage.luks"
else
  echo "loop: /var/lib/luxnix-secrets.luks"
fi''',
    }
    for name, body in scripts.items():
        command = mocks / name
        command.write_text("#!/bin/sh\n" + body + "\n")
        command.chmod(0o700)
    source = (Path(helper["output"]) / "bin/luxnix-operator-storage").read_text()
    source, count = re.subn(
        r"(?m)^export PATH=.*$",
        lambda match: match[0] + "\nexport PATH=" + shlex.quote(str(mocks)) + ":$PATH",
        source,
    )
    assert count == 1
    executable = tmp_path / "helper"
    executable.write_text(source)
    executable.chmod(0o700)
    calls = tmp_path / "calls"
    agent = tmp_path / "agent"
    master, slave = os.openpty()
    try:
        run = subprocess.run(
            [str(executable), "start"], stdin=slave, capture_output=True, text=True,
            env={**os.environ, "CALL_LOG": str(calls), "AGENT_LOG": str(agent),
                 "PASSPHRASE": str(int(profile == "gc-10")), "MISMATCH": str(int(mismatch))},
            timeout=20,
        )
    finally:
        os.close(master)
        os.close(slave)
    if mismatch:
        assert run.returncode != 0
        assert "mismatched mapping" in run.stderr
        assert not calls.exists()
    else:
        assert run.returncode == 0, run.stderr
        assert calls.read_text().splitlines() == [
            "start", *[name + ".service" for name in hosts[profile]["startup"]]
        ]
        if profile == "gc-10":
            assert agent.read_text().splitlines() == ["--watch"]


def test_fleet_inventory_defaults_and_all_host_assertions():
    inventory = (ROOT / "ansible/inventory/hosts.ini").read_text()
    def members(group):
        block = inventory.split("[" + group + "]", 1)[1].split("[", 1)[0]
        return sorted(line.split()[0] for line in block.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    fleet = members("active_clients")
    assert members("operator_unlocked_secrets") == fleet
    expression = r'''
      let f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      inspect = name: let c = f.nixosConfigurations.${name}.config; in {
        enabled = c.luxnix.storage.operatorUnlocked.enable;
        migration = c.luxnix.storage.operatorUnlocked.migration.enable;
        unlockMethod = c.luxnix.storage.operatorUnlocked.unlockMethod;
        clientRole = c.roles.endoreg-client.enable;
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
        baselineFailures = map (a: a.message) (builtins.filter (a: !a.assertion)
          (f.nixosConfigurations.${name}.extendModules { modules = [{ luxnix.storage.operatorUnlocked.enable = f.inputs.nixpkgs.lib.mkForce false; }]; }).config.assertions);
        prepare = c.systemd.services.luxnix-storage-migrate.serviceConfig.ExecStart or null;
        dependencies = c.systemd.services.luxnix-storage-migrate.unitConfig or {};
        mountOptions = map (v: c.fileSystems.${v.mountPoint}.options)
          (builtins.filter (v: v.container != null && c.luxnix.storage.operatorUnlocked.enable)
            (builtins.attrValues c.luxnix.storage.operatorUnlocked.volumes));
      }; in builtins.listToAttrs (map (name: { inherit name; value = inspect name; }) FLEET)
    '''.replace("FLEET", "[ " + " ".join(json.dumps(name) for name in fleet) + " ]")
    result = subprocess.run(["nix", "eval", "--impure", "--json", "--expr", expression], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    for host, settings in json.loads(result.stdout).items():
        assert settings["enabled"], host
        assert settings["migration"] == (host != "gc-10"), host
        assert settings["unlockMethod"] == "passphrase", host
        expected = settings["failures"] + ([
            "EndoReg clients require encrypted operator storage for secrets and application data."
        ] if settings["clientRole"] else [])
        assert sorted(settings["baselineFailures"]) == sorted(expected), (host, settings)
        if host == "gc-10":
            assert settings["prepare"] is None
            assert all("x-systemd.device-timeout=infinity" in options for options in settings["mountOptions"])
            continue
        assert "operator_migration.py" in settings["prepare"]
        assert settings["dependencies"]["DefaultDependencies"] is False
        assert all("x-systemd.device-timeout=infinity" in options for options in settings["mountOptions"])
