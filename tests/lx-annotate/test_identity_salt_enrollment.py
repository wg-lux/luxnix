from __future__ import annotations

import pytest
import json
import os
import re
import sys

from nix_eval_helpers import eval_json
import subprocess


def test_identity_enrollment_is_automatic_on_every_enabled_host():
    hosts = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
      in f.inputs.nixpkgs.lib.mapAttrs (_: host:
        let c = host.config; d = c.services.luxnix.lxAnnotateLocal.django;
        in if !c.services.luxnix.lxAnnotateLocal.enable then null else {
          excludes = c.services.luxnix.lxAnnotateLocal.hub.backup.exclude;
          enabled = d.enrollLegacyDefaultSalt;
          keyring = d.identitySaltKeyringFile;
          runtime = { inherit (c.systemd.services.lx-annotate-runtime-env)
            after requires; };
          provision = { inherit (c.systemd.services.lx-annotate-identity-salts)
            after requires serviceConfig; };
          secrets = builtins.attrNames c.roles.managed-secrets.customSecrets;
          script = builtins.readFile
            c.systemd.services.lx-annotate-identity-salts.serviceConfig.ExecStart;
        }
      ) f.nixosConfigurations
    """)
    enabled = {name: c for name, c in hosts.items() if c is not None}
    assert {"gc-02", "gc-05", "gc-06", "gc-09", "gc-10", "gs-02"} <= enabled.keys()
    for host, contract in enabled.items():
        assert contract["enabled"], host
        assert ".identity-salt-recovery" in contract["excludes"]
        assert (
            contract["keyring"] == "/etc/secrets/vault/lx_annotate_identity_keyring.yml"
        )
        for edge in ("after", "requires"):
            assert "lx-annotate-identity-salts.service" in contract["runtime"][edge]
        assert contract["provision"]["serviceConfig"]["User"] == "root"
        assert "--replica-dir" in contract["script"]
        assert (
            "--recovery-dir /var/lib/lx-annotate-identity-salts" in contract["script"]
        )
        assert not any(
            name.startswith("lx_annotate_identity_") for name in contract["secrets"]
        )


@pytest.mark.parametrize("option", ["identitySaltViaSecretSpec"])
def test_central_identity_options_fail_closed(option):
    rejected = eval_json(
        """
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          lib = f.inputs.nixpkgs.lib;
          c = (f.nixosConfigurations.gc-02.extendModules {
            modules = [{
              services.luxnix.lxAnnotateLocal.django.OPTION = lib.mkForce true;
            }];
          }).config;
      in builtins.any (a: !a.assertion && lib.hasPrefix
        "Central identity salt provisioning is disabled" a.message) c.assertions
    """.replace("OPTION", option)
    )
    assert rejected


@pytest.mark.parametrize(
    "host,center",
    [
        ("gc-02", "university_hospital_wuerzburg"),
        ("gc-06", "university_hospital_wuerzburg"),
        ("gc-09", "university_hospital_wuerzburg"),
        ("gc-10", "university_hospital_wuerzburg"),
    ],
)
def test_wuerzburg_hosts_opt_in_to_the_shared_center_salt(host, center):
    contract = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.HOST.config;
          opts = f.nixosConfigurations.HOST.options;
      in {
        enabled = c.services.luxnix.lxAnnotateLocal.django.centerIdentitySalt;
        defaultEnabled = (opts.services.luxnix.lxAnnotateLocal.django.type.getSubOptions []).centerIdentitySalt.default;
        center = c.roles.endoreg-client.defaultCenterKey;
        secret = c.roles.managed-secrets.customSecrets.lx_annotate_center_identity_source;
        script = builtins.readFile c.systemd.services.lx-annotate-identity-salts.serviceConfig.ExecStart;
      }
    """.replace("HOST", host))
    assert contract["enabled"] is True
    assert contract["defaultEnabled"] is False
    assert contract["center"] == center
    secret = contract["secret"]
    assert (secret["owner"], secret["permissions"]) == ("root", "600")
    assert secret["refreshOnBoot"]
    assert f"/centers/{center}/identity" in secret["generator"]
    assert "--source-salt" in contract["script"]
    assert secret["path"] in contract["script"]


def test_other_centers_keep_local_identity_salts():
    contract = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.gc-05.config;
      in {
        enabled = c.services.luxnix.lxAnnotateLocal.django.centerIdentitySalt;
        hasSource = c.roles.managed-secrets.customSecrets ? lx_annotate_center_identity_source;
        script = builtins.readFile c.systemd.services.lx-annotate-identity-salts.serviceConfig.ExecStart;
      }
    """)
    assert contract["enabled"] is False
    assert not contract["hasSource"]
    assert "--source-salt" not in contract["script"]


@pytest.mark.parametrize("denied", [False, True])
def test_enrollment_publishes_only_allowlisted_center_salts(tmp_path, denied):
    script = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.gs-02.config;
          tool = builtins.head (builtins.filter
            (p: (p.name or "") == "luxnix-vault-reconcile-hub-sites")
            c.environment.systemPackages);
      in builtins.readFile "${tool}/bin/luxnix-vault-reconcile-hub-sites"
    """)
    # Execute the built enrollment script against a recording Vault CLI, never a server.
    recorder = tmp_path / "vault.py"
    recorder.write_text("""
import json, os, sys
from pathlib import Path
path = Path(os.environ["RECORDING_VAULT"])
state = (json.loads(path.read_text()) if path.exists() else
         {"created": [], "policies": {}, "puts": []})
args = sys.argv[1:]
if args[:2] == ["secrets", "list"]:
    print(json.dumps({"lx-hub-pki/": {}, "lx-hub-secrets/": {}}))
elif args[:2] == ["auth", "list"]:
    print(json.dumps({"approle/": {}}))
elif args[:2] == ["kv", "get"]:
    if os.environ["DENIED"] == "true":
        print("permission denied", file=sys.stderr)
        sys.exit(2)
    if args[-1] not in state["created"]:
        print("No value found at requested path", file=sys.stderr)
        sys.exit(2)
    print("existing-test-material")
elif args[:2] == ["kv", "put"]:
    assert "-cas=0" in args
    assert len(sys.stdin.read().strip()) == 64
    state["puts"].append(args[-2])
    state["created"].append(args[-2])
elif args[:2] == ["policy", "write"]:
    state["policies"][args[2]] = Path(args[3]).read_text()
path.write_text(json.dumps(state))
""")
    script = re.sub(r"(?<![\w/-])vault(?= )", f"{sys.executable} {recorder}", script)
    script = script.replace(
        "/var/lib/luxnix-vault-site-lifecycle", str(tmp_path / "lifecycle")
    )
    record = tmp_path / "calls.json"
    result = subprocess.run(
        ["bash", "-c", script, "enroll", "gc-02.intern", "gc-10.intern", "gc-05.intern"],
        env={
            **os.environ,
            "VAULT_ADDR": "https://test.invalid",
            "VAULT_TOKEN": "test-only",
            "RECORDING_VAULT": str(record),
            "DENIED": str(denied).lower(),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )
    state = json.loads(record.read_text())
    if denied:
        # A permission error is never treated as an absent secret.
        assert result.returncode != 0
        assert state["puts"] == []
        return
    assert result.returncode == 0, result.stderr
    assert state["puts"] == [
        "lx-hub-secrets/centers/university_hospital_wuerzburg/identity"
    ]
    for site in ("gc_02_intern", "gc_10_intern"):
        policy = state["policies"][f"lx-hub-site-{site}"]
        assert "data/centers/university_hospital_wuerzburg/identity" in policy
        assert "rbk_stuttgart" not in policy
        rules = policy.split("data/centers/", 1)[1]
        assert 'capabilities = ["read"]' in rules
        assert '"update"' not in rules and '"create"' not in rules
    assert "/centers/" not in state["policies"]["lx-hub-site-gc_05_intern"]


def test_gs02_acceptance_trusts_its_vault_ca():
    script = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
      in builtins.readFile
        f.nixosConfigurations.gs-02.config.systemd.services
          .lx-annotate-acceptance.serviceConfig.ExecStart
    """)
    assert "--cacert /var/lib/luxnix-vault-pki/ca.crt" in script
    assert "--insecure" not in script


@pytest.mark.parametrize("mode", ["enrolled", "external", "disabled", "no-keyring"])
def test_background_identity_migration_contract(mode):
    contract = eval_json(
        """
      let
        f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        c = (f.nixosConfigurations.gc-02.extendModules {
          modules = [({ lib, ... }: {
            services.luxnix.lxAnnotateLocal.django = {
              enrollLegacyDefaultSalt = lib.mkForce ("MODE" == "enrolled");
              automaticIdentitySaltMigration = "MODE" != "disabled";
              identitySaltKeyringFile = lib.mkIf ("MODE" != "enrolled")
                (lib.mkForce (if "MODE" == "no-keyring"
                  then null else "/private/identity.yml"));
            };
          })];
        }).config;
        unit = "lx-annotate-identity-salt-migration";
          in {
            provisioning = c.systemd.services ? lx-annotate-identity-salts;
        service = if c.systemd.services ? ${unit} then {
          inherit (c.systemd.services.${unit})
            wantedBy before after requires serviceConfig;
        } else null;
        timer = if c.systemd.timers ? ${unit} then {
          inherit (c.systemd.timers.${unit}) wantedBy timerConfig;
        } else null;
        dependents = builtins.attrNames (f.inputs.nixpkgs.lib.filterAttrs (_: s:
          builtins.elem "${unit}.service"
            (s.requires ++ s.wants ++ s.after ++ s.bindsTo)
        ) c.systemd.services);
        web = c.systemd.services.lx-annotate.serviceConfig;
      }
    """.replace("MODE", mode)
    )
    assert contract["dependents"] == []
    assert contract["provisioning"] is (mode == "enrolled")
    if mode in {"disabled", "no-keyring"}:
        assert contract["service"] is None
        assert contract["timer"] is None
        return
    service = contract["service"]
    config = service["serviceConfig"]
    assert service["wantedBy"] == service["before"] == []
    assert "lx-annotate.service" in service["after"]
    for prerequisite in ("load-base-data", "master-key-check", "runtime-env"):
        assert f"lx-annotate-{prerequisite}.service" in service["requires"]
        assert f"lx-annotate-{prerequisite}.service" in service["after"]
    assert config["ExecStart"].endswith(
        "/bin/lx-annotate-manage rotate_identity_salt --apply --allow-partial"
    )
    assert config["Type"] == "oneshot"
    assert config["TimeoutStartSec"] == "15m"
    assert config.get("SuccessExitStatus", []) == []
    for field in ("User", "Group", "EnvironmentFile", "LogNamespace"):
        assert config[field] == contract["web"][field]
    assert contract["timer"]["wantedBy"] == ["timers.target"]
    assert contract["timer"]["timerConfig"] == {
        "OnBootSec": "10m",
        "OnUnitInactiveSec": "1h",
        "RandomizedDelaySec": "1m",
        "Unit": "lx-annotate-identity-salt-migration.service",
    }


def test_reviewed_migration_path_is_passed_as_one_literal_argument(tmp_path):
    script = eval_json("""
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = (f.nixosConfigurations.gc-02.extendModules {
            modules = [{ services.luxnix.lxAnnotateLocal.django = {
              identitySaltMigrationReviewFile =
              "/private/review file $(false).yml"; }; }];
          }).config;
      in builtins.readFile
        c.systemd.services.lx-annotate-identity-salt-migration.serviceConfig.ExecStart
    """)
    # Exercise shell quoting without running Django or touching a real review file.
    command = script.split("exec ", 1)[1].split(" rotate_identity_salt", 1)[0]
    capture = tmp_path / "capture"
    capture.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    capture.chmod(0o700)
    result = subprocess.run(
        ["bash", "-c", script.replace(command, str(capture))],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "rotate_identity_salt",
        "--apply",
        "--allow-partial",
        "--review-file",
        "/private/review file $(false).yml",
    ]
