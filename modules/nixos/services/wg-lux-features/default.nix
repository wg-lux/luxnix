{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.wg-lux-features;
  dependencyProviders = pkgs.lx-annotate.featureProviders or { };
  defaultProviders = {
    lx-annotate = {
      package = pkgs.lx-annotate;
      featureSubdir = "share/lx-annotate/features";
    };
  }
  // lib.optionalAttrs (dependencyProviders ? endoreg-db) {
    endoreg-db = {
      package = dependencyProviders.endoreg-db;
      featureSubdir = "share/endoreg-db/features";
    };
  }
  // lib.optionalAttrs (dependencyProviders ? lx-data-models) {
    lx-data-models = {
      package = dependencyProviders.lx-data-models;
      featureSubdir = "share/lx-data-models/features";
    };
  };
  providerType = lib.types.submodule (
    { config, ... }:
    {
      options = {
        package = lib.mkOption {
          type = lib.types.package;
          description = "Owning package derivation containing immutable feature specifications.";
        };
        featureSubdir = lib.mkOption {
          type = lib.types.str;
          description = "Feature directory below the owning package output.";
        };
        revision = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          description = "Source revision recorded by the package/deployment when available.";
        };
        version = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = config.package.version or null;
          description = "Owning package version when available.";
        };
      };
    }
  );
  registry = {
    schema_version = "1.0";
    providers = lib.mapAttrs (
      _provider: provider: {
        kind = "nix";
        feature_root = "${provider.package}/${provider.featureSubdir}";
        package_store_path = "${provider.package}";
        drv_path = provider.package.drvPath;
        inherit (provider) revision version;
        system_generation = cfg.deploymentId;
      }
    ) cfg.providers;
  };
  registrySource = pkgs.writeText "wg-lux-feature-providers.json" (
    builtins.toJSON registry
  );
in
{
  options.services.wg-lux-features = {
    enable = lib.mkEnableOption "system-level WG-Lux feature registry";
    providers = lib.mkOption {
      type = lib.types.attrsOf providerType;
      default = defaultProviders;
      defaultText = lib.literalExpression "the lx-annotate closure's feature providers";
      description = "Deployed package outputs resolved into the canonical provider registry.";
    };
    stateRoot = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/wg-lux/features";
      description = "Persistent mutable assessment ledger and projection root.";
    };
    group = lib.mkOption {
      type = lib.types.str;
      default = "wg-lux-features";
      description = "Group allowed to read system feature assessment state.";
    };
    deploymentId = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Optional deployment or system generation identity included in provenance.";
    };
    registryPath = lib.mkOption {
      type = lib.types.str;
      readOnly = true;
      default = "/etc/wg-lux/features/providers.json";
      description = "Nix-generated deployed provider registry projection.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.providers != { };
        message = "services.wg-lux-features requires at least one explicit deployed provider";
      }
    ];

    environment.etc."wg-lux/features/providers.json".source = registrySource;
    users.groups.${cfg.group} = { };
    systemd.tmpfiles.rules = [
      "d ${cfg.stateRoot} 0750 root ${cfg.group} - -"
      "d ${cfg.stateRoot}/assessments 0750 root ${cfg.group} - -"
      "d ${cfg.stateRoot}/events 0750 root ${cfg.group} - -"
      "d ${cfg.stateRoot}/projections 0750 root ${cfg.group} - -"
    ];
  };
}
