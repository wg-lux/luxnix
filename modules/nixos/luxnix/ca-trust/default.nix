{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.caTrust;
  caBundle = config.security.pki.caBundle;

  # Fails the system build when any distrusted root is still present in the
  # final bundle, including as an OpenSSL TRUSTED CERTIFICATE block.
  bundleCheck =
    pkgs.runCommand "luxnix-ca-trust-check"
      {
        nativeBuildInputs = [ pkgs.python3 ];
      }
      ''
        python3 -I ${./verify-bundle.py} \
          --source ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt \
          --bundle ${caBundle} \
          ${concatMapStringsSep " " (label: "--label ${escapeShellArg label}") cfg.distrustedCertificates}
        touch "$out"
      '';

  repairPackage = pkgs.writeShellScriptBin "luxnix-ca-trust-repair" ''
    exec ${pkgs.python3}/bin/python3 -I ${./repair.py} --bundle ${caBundle} "$@"
  '';
in
{
  options.luxnix.caTrust = {
    enable = mkBoolOpt true "Remove distrusted roots from the system CA bundle and verify the result at build time";

    distrustedCertificates =
      mkOpt (types.listOf types.str)
        [
          # CVE-2026-111943 (eMudhra intermediate compromise). nixpkgs
          # nixos/modules/security/ca.nix appends the same labels since
          # 2026-10-20; listing them here keeps them under the build check.
          "Comodo AAA Services root"
          "emSign ECC Root CA - G3"
          "emSign Root CA - C1"
          "emSign ECC Root CA - C3"
        ]
        "Mozilla trust store labels excluded from the system CA bundle. Remove an entry once the pinned cacert no longer ships it.";

    repairPackage = mkOption {
      type = types.package;
      readOnly = true;
      default = repairPackage;
      description = "Command that relinks certifi bundles in mutable Python environments to the system CA bundle.";
    };
  };

  config = mkIf cfg.enable {
    security.pki.caCertificateBlacklist = cfg.distrustedCertificates;
    # The default bundle keeps blacklisted roots as OpenSSL "rejected"
    # TRUSTED CERTIFICATE blocks. Parsers that drop OpenSSL trust rules
    # (Python cadata=, rustls, Node) would still trust them, so publish only
    # roots trusted for server authentication.
    security.pki.useCompatibleBundle = true;

    system.checks = [ bundleCheck ];
    environment.systemPackages = [ cfg.repairPackage ];
  };
}
