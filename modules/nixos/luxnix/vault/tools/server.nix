# Vault server lifecycle: VPN bind wait, rebuild preparation and managed TLS.
{
  lib,
  pkgs,
  config,
  ctx,
  ...
}:
with lib;
with lib.luxnix;
let
  inherit (ctx)
    runtimeDir
    serverCfg
    serverBindHost
    managedTlsCfg
    ;
  waitForServerBindAddress = pkgs.writeShellScript "luxnix-vault-wait-bind-address" ''
    set -euo pipefail
    for _ in $(${pkgs.coreutils}/bin/seq 120); do
      if [ -n "$(${pkgs.iproute2}/bin/ip -o addr show to ${lib.escapeShellArg serverBindHost})" ]; then
        exit 0
      fi
      ${pkgs.coreutils}/bin/sleep 1
    done
    echo "ERROR: Vault bind address ${serverBindHost} is not assigned; is the VPN up?" >&2
    exit 1
  '';

  serverRebuildPreparationTool = pkgs.writeShellApplication {
    name = "luxnix-vault-prepare-server-rebuild";
    runtimeInputs = [
      pkgs.age
      pkgs.coreutils
      pkgs.gnutar
      pkgs.systemd
    ];
    text = ''
      export EXPECTED_HOSTNAME=${lib.escapeShellArg config.networking.hostName}
      export VAULT_STORAGE_PATH=${lib.escapeShellArg (toString serverCfg.storagePath)}
      export VAULT_TLS_STATE_DIRECTORY=${lib.escapeShellArg managedTlsCfg.stateDirectory}
      export VAULT_TLS_CA_FILE=${lib.escapeShellArg (toString serverCfg.caCertFile)}
      exec ${pkgs.bash}/bin/bash ${../../../../../scripts/vault/prepare-server-rebuild.sh} "$@"
    '';
  };

  managedServerTlsTool = pkgs.writeShellApplication {
    name = "luxnix-vault-maintain-server-tls";
    runtimeInputs = [
      pkgs.bash
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.openssl
    ];
    text = builtins.readFile ../../../../../scripts/vault/maintain-server-tls.sh;
  };

  managedServerTlsCommand = lib.escapeShellArgs (
    [
      "${managedServerTlsTool}/bin/luxnix-vault-maintain-server-tls"
      "--state-dir"
      managedTlsCfg.stateDirectory
      "--ca-cert"
      (toString serverCfg.caCertFile)
      "--ca-key"
      managedTlsCfg.caKeyFile
      "--server-cert"
      (toString serverCfg.tlsCertFile)
      "--server-key"
      (toString serverCfg.tlsKeyFile)
      "--read-group"
      config.luxnix.generic-settings.sensitiveServiceGroupName
      "--ca-common-name"
      managedTlsCfg.caCommonName
      "--server-common-name"
      managedTlsCfg.serverCommonName
      "--ca-validity-days"
      (toString managedTlsCfg.caValidityDays)
      "--leaf-validity-days"
      (toString managedTlsCfg.leafValidityDays)
      "--renew-before-days"
      (toString managedTlsCfg.renewBeforeDays)
      "--rotation-marker"
      "${runtimeDir}/server-leaf-rotated"
    ]
    ++ lib.concatMap (name: [
      "--dns-name"
      name
    ]) managedTlsCfg.dnsNames
    ++ lib.concatMap (address: [
      "--ip-address"
      address
    ]) managedTlsCfg.ipAddresses
  );
in
{
  inherit
    waitForServerBindAddress
    serverRebuildPreparationTool
    managedServerTlsCommand
    ;
}
