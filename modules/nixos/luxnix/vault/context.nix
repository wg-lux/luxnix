# Shared vault settings, runtime paths and storage verifiers.
{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.vault;
  adminName = config.user.admin.name;
  runtimeDir = "/run/luxnix/vault";
  runtimeEnvironmentFile = "${runtimeDir}/vault.env";
  runtimeTokenFile = "${runtimeDir}/vault.token";
  runtimeStatusFile = "${runtimeDir}/enrollment-status";
  clientReissueMarker = "${runtimeDir}/force-client-reissue";
  vaultAuthEnabled = cfg.enable && cfg.client.enable && cfg.client.auth.method != "none";
  verifySecretStorage = pkgs.writeShellScript "verify-vault-secret-storage" ''
    export PATH=${lib.makeBinPath [ pkgs.util-linux ]}:"$PATH"
    exec ${pkgs.python3}/bin/python ${../../../../lx_administration/secret_storage.py} --allow-runtime "$@"
  '';
  clientCredentialPaths = lib.filter (path: path != null) [
    cfg.client.auth.tokenFile
    cfg.client.auth.roleIdFile
    cfg.client.auth.secretIdFile
    cfg.client.environmentFile
  ];
  verifyClientStorage =
    "${verifySecretStorage} "
    + lib.escapeShellArgs ([ runtimeDir ] ++ map toString clientCredentialPaths);

  serverCfg = cfg.server;
  # The listener binds a VPN address that only exists once the tunnel is up.
  serverBindHost =
    let
      match = builtins.match "\\[?([^]]*)]?:[0-9]+" serverCfg.bindAddress;
    in
    if match == null then null else builtins.head match;
  serverWaitsForBindAddress =
    serverBindHost != null
    && !(builtins.elem serverBindHost [
      "0.0.0.0"
      "::"
      "127.0.0.1"
      "::1"
      "localhost"
    ]);
  serverVpnServices = lib.optional config.roles.aglnet.client.enable "openvpn-${config.roles.aglnet.client.networkName}.service";
  managedTlsCfg = serverCfg.managedTls;
  inherit (import "${pkgs.path}/nixos/lib/utils.nix" { inherit config lib pkgs; }) escapeSystemdPath;
  tlsStorageMountUnit = "${escapeSystemdPath managedTlsCfg.stateDirectory}.mount";
  hubPkiCfg = serverCfg.hubPki;
  clientHubPkiCfg = cfg.client.hubPki;
  clientHubPkiSecretDirectories = lib.unique [
    (builtins.dirOf clientHubPkiCfg.nodeSecretFile)
    (builtins.dirOf clientHubPkiCfg.recipientPublicKeyFile)
  ];
in
{
  inherit
    cfg
    adminName
    runtimeDir
    runtimeEnvironmentFile
    runtimeTokenFile
    runtimeStatusFile
    clientReissueMarker
    vaultAuthEnabled
    verifySecretStorage
    verifyClientStorage
    serverCfg
    serverBindHost
    serverWaitsForBindAddress
    serverVpnServices
    managedTlsCfg
    tlsStorageMountUnit
    hubPkiCfg
    clientHubPkiCfg
    clientHubPkiSecretDirectories
    ;
}
