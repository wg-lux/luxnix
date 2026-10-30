{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.luxnix.tpmReleaseClient;
  storage = config.luxnix.storage.operatorUnlocked;

  # Activates the TPM provider only for this tool; the system OpenSSL config is untouched.
  opensslConf = pkgs.writeText "luxnix-tpm-release-openssl.cnf" ''
    openssl_conf = init
    [init]
    providers = providers
    [providers]
    tpm2 = activate
    default = activate
    [activate]
    activate = 1
  '';

  package = pkgs.writeShellApplication {
    name = "luxnix-tpm-release";
    runtimeInputs = [
      pkgs.curl
      pkgs.openssl
      pkgs.tpm2-tools
    ];
    text = ''
      export OPENSSL_MODULES=${pkgs.tpm2-openssl}/lib/ossl-modules
      export OPENSSL_CONF=${opensslConf}
      exec ${pkgs.python3}/bin/python3 -I ${../../../../lx_administration/storage/tpm_release.py} "$@"
    '';
  };

  # Every identity file must be readable before any operator-unlocked volume opens.
  lockedPaths =
    map (volume: volume.mountPoint) (builtins.attrValues storage.volumes)
    ++ builtins.attrNames storage.bindMounts;
  insideLocked =
    path: lib.any (prefix: path == prefix || lib.hasPrefix "${prefix}/" path) lockedPaths;
  identityFiles = [
    cfg.keyFile
    cfg.certificateFile
    cfg.caFile
  ];
in
{
  options.luxnix.tpmReleaseClient = {
    enable = lib.mkEnableOption "TPM-bound client identity for central volume release by gs-02";
    package = lib.mkOption {
      type = lib.types.package;
      default = package;
      readOnly = true;
      description = "luxnix-tpm-release command with the TPM OpenSSL provider.";
    };
    releaseUrl = lib.mkOption {
      type = lib.types.str;
      description = "HTTPS base URL of the OpenBao release listener on gs-02.";
    };
    identityName = lib.mkOption {
      type = lib.types.str;
      default = config.networking.hostName;
      defaultText = lib.literalExpression "config.networking.hostName";
      description = "Certificate common name and OpenBao cert-auth role of this host.";
    };
    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/luxnix-tpm-identity";
      description = "Root-filesystem directory for the TPM-wrapped key and public certificates.";
    };
    keyFile = lib.mkOption {
      type = lib.types.str;
      default = "${cfg.stateDir}/device.tss2.pem";
      defaultText = lib.literalExpression ''"''${stateDir}/device.tss2.pem"'';
      description = "TSS2 TPM-wrapped identity key; useless without this host's TPM.";
    };
    certificateFile = lib.mkOption {
      type = lib.types.str;
      default = "${cfg.stateDir}/device.pem";
      defaultText = lib.literalExpression ''"''${stateDir}/device.pem"'';
      description = "Client certificate issued for the TPM identity during enrollment.";
    };
    caFile = lib.mkOption {
      type = lib.types.str;
      default = "${cfg.stateDir}/release-ca.pem";
      defaultText = lib.literalExpression ''"''${stateDir}/release-ca.pem"'';
      description = "Pinned CA for the gs-02 release listener; never trust-on-first-use.";
    };
    mount = lib.mkOption {
      type = lib.types.str;
      default = "volume-release";
      description = "OpenBao KV v2 mount holding one record per host and volume.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = lib.hasPrefix "https://" cfg.releaseUrl;
        message = "luxnix.tpmReleaseClient.releaseUrl must use HTTPS.";
      }
      {
        assertion = lib.all (p: lib.hasPrefix "/" p && !(lib.hasPrefix "/nix/store/" p)) identityFiles;
        message = "TPM release identity files must be absolute runtime paths outside the Nix store.";
      }
      {
        assertion = !(lib.any insideLocked identityFiles);
        message = "TPM release identity files must not live on an operator-unlocked volume or bind (ENC-07).";
      }
    ];
    security.tpm2.enable = true;
    environment.systemPackages = [ cfg.package ];
    systemd.tmpfiles.rules = [ "d ${cfg.stateDir} 0700 root root -" ];
  };
}
