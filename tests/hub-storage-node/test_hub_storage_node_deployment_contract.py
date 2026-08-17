from __future__ import annotations

from pathlib import Path

from hub_storage_nix_eval_helpers import eval_json


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "modules/nixos/services/hub-storage-node/default.nix"
PROFILE = REPO_ROOT / "modules/nixos/profiles/endoreg-storage-node/default.nix"
GS01 = REPO_ROOT / "systems/x86_64-linux/gs-01/default.nix"
GS02 = REPO_ROOT / "systems/x86_64-linux/gs-02/default.nix"
GS01_INVENTORY = REPO_ROOT / "ansible/inventory/host_vars/gs-01.yml"


def _node_module_eval(config: str, result: str):
    return eval_json(
        f"""
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          evaluated = flake.inputs.nixpkgs.lib.nixosSystem {{
            system = "x86_64-linux";
            modules = [ {MODULE} ({{ lib, ... }}: {{ {config} }}) ];
          }};
        in {result}
        """
    )


def _hub_module_eval(*, balancing: bool):
    enabled = "true" if balancing else "false"
    return _node_module_eval(
        f"""
        options.services.luxnix.lxAnnotateLocal.hub.enable = lib.mkOption {{
          type = lib.types.bool;
          default = false;
        }};
        options.services.luxnix.lxAnnotateLocal.runtime.deploymentRole =
          lib.mkOption {{ type = lib.types.str; default = "standalone"; }};
        config = {{
          services.luxnix.lxAnnotateLocal.hub.enable = true;
          services.luxnix.lxAnnotateLocal.runtime.deploymentRole = "central_hub";
          services.luxnix.hubStorage.hubClient = {{
            enable = true;
            balancing.enable = {enabled};
            nodes = [ {{
              identity = "storage-01";
              displayName = "Storage 01";
              failureDomain = "rack-a";
              residencyKey = "de";
              artifactKinds = [ "processed_report" ];
              endpoint = "https://storage-01.internal:9443";
              caCertificateFile = "/run/ca";
              clientCertificateFile = "/run/cert";
              clientKeyFile = "/run/key";
              recipientPublicKeyFile = "/run/recipient";
            }} ];
          }};
        }};
        """,
        """
        let
          contract = evaluated.config.systemd.services.
            lx-annotate-hub-storage-client-contract;
          services = evaluated.config.systemd.services;
          app = if builtins.hasAttr "lx-annotate" services
            then services.lx-annotate else {};
        in {
          requiredBy = contract.requiredBy;
          appRequires = app.requires or [];
          appEnvironmentFiles = app.serviceConfig.EnvironmentFile or [];
          balancingEnvironment = app.environment.ENDOREG_ENABLE_STORAGE_BALANCING;
        }
        """,
    )


def test_storage_node_role_is_inactive_until_explicitly_enabled() -> None:
    module = MODULE.read_text(encoding="utf-8")
    profile = PROFILE.read_text(encoding="utf-8")

    assert 'enable = mkEnableOption "the LX-Annotate protected storage-node' in module
    assert 'enable = mkEnableOption "the central-hub storage-node client' in module
    assert "config = lib.mkIf cfg.enable" in profile
    assert "services.luxnix.hubStorage.node.enable = lib.mkDefault true" in profile


def test_gs01_is_declared_as_gs02_only_storage_peer_with_balancing_gated() -> None:
    gs01 = GS01.read_text(encoding="utf-8")
    gs02 = GS02.read_text(encoding="utf-8")
    gs01_inventory = GS01_INVENTORY.read_text(encoding="utf-8")

    assert 'hubStorage.node.identity = "gs-01"' in gs01
    assert 'hubStorage.node.storage.mountPoint = "/archive"' in gs01
    assert 'encryptedDevice = "/dev/mapper/gs-01-storage"' in gs01
    assert 'listenAddress = "172.16.255.21"' in gs01
    assert 'allowedHubAddresses = [ "172.16.255.22" ]' in gs01
    assert 'allowedHubIdentities = [ "spiffe://endoreg/hub/gs-02" ]' in gs01
    assert "hubStorage.hubClient.enable = true" in gs02
    assert "hubStorage.hubClient.balancing.enable = false" in gs02
    assert 'identity = "gs-01"' in gs02
    assert 'endpoint = "https://gs-01.intern:9443"' in gs02
    assert 'recipientPublicKeyFile = "/etc/secrets/vault/hub-storage/' in gs02
    assert 'luxnix.hubStorage.node.enable: "true"' in gs01_inventory
    assert "luxnix.hubStorage.node.identity: '\"gs-01\"'" in gs01_inventory
    assert (
        "luxnix.hubStorage.node.storage.encryptedDevice: "
        "'\"/dev/mapper/gs-01-storage\"'"
    ) in gs01_inventory


def test_storage_node_fails_closed_on_mount_identity_network_and_capacity() -> None:
    module = MODULE.read_text(encoding="utf-8")

    required_contracts = (
        "unitConfig.RequiresMountsFor = [ nodeCfg.storage.mountPoint ]",
        'cryptsetup status "$encrypted_device"',
        'nodeCfg.network.listenAddress != "0.0.0.0"',
        "nodeCfg.network.allowedHubAddresses != [ ]",
        "nodeCfg.network.allowedHubIdentities != [ ]",
        "recovery < warning < stop",
        "hubStorage.node.service.command must be an absolute executable path",
        "EnvironmentFile = nodeEnvironmentFile",
        "HUB_STORAGE_ALLOWED_HUB_IDENTITIES=",
        "HUB_STORAGE_MAX_OBJECT_BYTES=",
        "HUB_STORAGE_ENCRYPTED_DEVICE=",
        "HUB_STORAGE_MAX_CONCURRENT_REQUESTS=",
        "HUB_STORAGE_REQUEST_TIMEOUT_SECONDS=",
        "ReadWritePaths = [ nodeCfg.storage.mountPoint ]",
        "private identity material must be root-owned",
        "group-readable by the service",
        "protected storage mount is not backed by the configured encrypted device",
        "storage, mTLS, and recipient paths must be absolute",
    )
    for contract in required_contracts:
        assert contract in module


def test_storage_node_network_port_is_private_interface_only() -> None:
    module = MODULE.read_text(encoding="utf-8")

    assert "networking.firewall.extraInputRules" in module
    assert "ip saddr" in module
    assert "nodeCfg.network.allowedHubAddresses" in module
    assert "networking.firewall.allowedTCPPorts" not in module


def test_hub_nodes_json_uses_the_canonical_typed_schema() -> None:
    module = MODULE.read_text(encoding="utf-8")

    assert "node_key = node.identity" in module
    assert "failure_domain = node.failureDomain" in module
    assert "artifact_kinds = node.artifactKinds" in module
    assert "ca_certificate_file = node.caCertificateFile" in module
    assert "recipient_public_key_file = node.recipientPublicKeyFile" in module
    assert "privateHubEndpoint node.endpoint" in module


def test_hub_contract_requires_central_role_https_and_credentials() -> None:
    module = MODULE.read_text(encoding="utf-8")

    assert 'runtime.deploymentRole == "central_hub"' in module
    assert "privateHubEndpoint node.endpoint" in module
    assert (
        'requiredBy = lib.optionals hubCfg.balancing.enable [ "lx-annotate.service" ]'
        in module
    )
    assert 'requires = [ "lx-annotate-hub-storage-client-contract.service" ]' in module
    assert "HUB_STORAGE_NODES_FILE=" in module
    assert "recipientPublicKeyFile" in module
    assert "recipientPrivateIdentityFile" in module
    assert "group-readable by ${hubCfg.serviceGroup}" in module


def test_hub_credentials_do_not_block_application_while_balancing_is_off() -> None:
    evaluated = _hub_module_eval(balancing=False)

    assert evaluated == {
        "requiredBy": [],
        "appRequires": [],
        "appEnvironmentFiles": [],
        "balancingEnvironment": "0",
    }


def test_hub_credentials_gate_application_when_balancing_is_on() -> None:
    evaluated = _hub_module_eval(balancing=True)

    assert evaluated["requiredBy"] == ["lx-annotate.service"]
    assert evaluated["appRequires"] == [
        "lx-annotate-hub-storage-client-contract.service"
    ]
    assert evaluated["appEnvironmentFiles"] == [
        "/run/lx-annotate-hub-storage-client/environment"
    ]
    assert evaluated["balancingEnvironment"] == "1"


def test_deployment_contract_never_exports_application_master_key() -> None:
    module = MODULE.read_text(encoding="utf-8").lower()

    assert "application_master_key" not in module
    assert "master_key_file" not in module


def test_nix_evaluation_keeps_both_storage_contracts_disabled_by_default() -> None:
    evaluated = _node_module_eval(
        "",
        """{
          node = evaluated.config.services.luxnix.hubStorage.node.enable;
          hub = evaluated.config.services.luxnix.hubStorage.hubClient.enable;
        }""",
    )

    assert evaluated == {"node": False, "hub": False}


def test_nix_evaluation_wires_private_firewall_mount_and_environment() -> None:
    evaluated = _node_module_eval(
        """
        services.luxnix.hubStorage.node = {
          enable = true;
          identity = "storage-01";
          storage.encryptedDevice = "/dev/mapper/storage";
          network = {
            listenAddress = "10.0.0.2";
            interface = "tun0";
            allowedHubAddresses = [ "10.0.0.1" ];
            allowedHubIdentities = [ "spiffe://endoreg/hub/primary" ];
            hubIdentityOperations."spiffe://endoreg/hub/primary" = [
              "health"
              "capacity"
              "store"
              "fetch_plaintext"
              "verify"
              "delete"
            ];
          };
          tls = {
            caCertificateFile = "/run/ca";
            certificateFile = "/run/cert";
            keyFile = "/run/key";
          };
          recipientPrivateIdentityFile = "/run/recipient";
          service.command = "/bin/false";
        };
        """,
        """
        let
          service = evaluated.config.systemd.services.lx-annotate-hub-storage-node;
          preflight = evaluated.config.systemd.services.
            lx-annotate-hub-storage-node-contract;
        in {
          command = service.serviceConfig.ExecStart;
          mounts = service.unitConfig.RequiresMountsFor;
          bindsTo = service.bindsTo;
          preflightRemainAfterExit =
            preflight.serviceConfig.RemainAfterExit or false;
          preflightRequiredBy = preflight.requiredBy;
          firewallRules = evaluated.config.networking.firewall.extraInputRules;
          environmentFile = service.serviceConfig.EnvironmentFile;
        }
        """,
    )

    assert evaluated == {
        "command": "/bin/false",
        "mounts": ["/mnt/lx-annotate-storage"],
        "bindsTo": [
            "mnt-lx\\x2dannotate\\x2dstorage.mount",
            "dev-mapper-storage.device",
        ],
        "preflightRemainAfterExit": False,
        "preflightRequiredBy": ["lx-annotate-hub-storage-node.service"],
        "firewallRules": 'iifname "tun0" ip saddr { 10.0.0.1 } tcp dport 9443 accept\n',
        "environmentFile": "/run/lx-annotate-hub-storage-node/environment",
    }


def test_nix_evaluation_provides_packaged_application_command() -> None:
    command = _node_module_eval(
        """
        services.luxnix.hubStorage.node = {
          enable = true;
          identity = "storage-01";
          storage.encryptedDevice = "/dev/mapper/storage";
          network = {
            listenAddress = "10.0.0.2";
            interface = "tun0";
            allowedHubAddresses = [ "10.0.0.1" ];
            allowedHubIdentities = [ "spiffe://endoreg/hub/primary" ];
            hubIdentityOperations."spiffe://endoreg/hub/primary" = [
              "health"
              "capacity"
              "store"
              "fetch_plaintext"
              "verify"
              "delete"
            ];
          };
          tls = {
            caCertificateFile = "/run/ca";
            certificateFile = "/run/cert";
            keyFile = "/run/key";
          };
          recipientPrivateIdentityFile = "/run/recipient";
        };
        """,
        "evaluated.config.systemd.services.lx-annotate-hub-storage-node.serviceConfig.ExecStart",
    )
    assert command.endswith("/bin/lx-hub-storage-node")


def test_packaged_command_ignores_ambient_python_import_paths() -> None:
    module = MODULE.read_text(encoding="utf-8")

    assert "unset PYTHONPATH PYTHONHOME" in module
    assert "export PYTHONNOUSERSITE=1" in module
    assert "/bin/python -I -s -c" in module
    assert "export PYTHONPATH=" not in module
    assert "at most three overlapping recipient identities" in module


def test_nix_evaluation_wires_fail_closed_crash_artifact_janitor() -> None:
    evaluated = _node_module_eval(
        """
        services.luxnix.hubStorage.node = {
          enable = true;
          identity = "storage-01";
          storage.encryptedDevice = "/dev/mapper/storage";
          network = {
            listenAddress = "10.0.0.2";
            interface = "tun0";
            allowedHubAddresses = [ "10.0.0.1" ];
            allowedHubIdentities = [ "spiffe://endoreg/hub/primary" ];
            hubIdentityOperations."spiffe://endoreg/hub/primary" = [ "health" ];
          };
          tls = {
            caCertificateFile = "/run/ca";
            certificateFile = "/run/cert";
            keyFile = "/run/key";
          };
          recipientPrivateIdentityFile = "/run/recipient";
        };
        """,
        """
        let
          service = evaluated.config.systemd.services.
            lx-annotate-hub-storage-node-janitor;
          timer = evaluated.config.systemd.timers.
            lx-annotate-hub-storage-node-janitor;
        in {
          command = service.serviceConfig.ExecStart;
          environmentFile = service.serviceConfig.EnvironmentFile;
          calendar = timer.timerConfig.OnCalendar;
        }
        """,
    )
    assert evaluated["command"].endswith(
        "/bin/lx-hub-storage-node janitor --minimum-age-seconds 86400 "
        "--max-entries 10000"
    )
    assert evaluated["environmentFile"] == (
        "/run/lx-annotate-hub-storage-node/environment"
    )
    assert evaluated["calendar"] == "daily"
