from __future__ import annotations

import pytest

from nix_eval_helpers import eval_json


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
