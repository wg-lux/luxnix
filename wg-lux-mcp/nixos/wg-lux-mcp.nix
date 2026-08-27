{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.wg-lux-mcp;
  sslCfg = config.services.luxnix.lxSsl;
  source = lib.cleanSourceWith {
    src = ../.;
    filter =
      path: _type:
      let
        name = builtins.baseNameOf path;
      in
      !builtins.elem name [
        ".pytest_cache"
        ".ruff_cache"
        ".venv"
        "__pycache__"
      ];
  };
  defaultPackage = pkgs.python312Packages.buildPythonApplication {
    pname = "wg-lux-mcp";
    version = "0.1.0";
    src = source;
    pyproject = true;
    build-system = [ pkgs.python312Packages.hatchling ];
    dependencies = with pkgs.python312Packages; [
      mcp
      pyjwt
      cryptography
      pydantic-settings
      pyyaml
      starlette
      uvicorn
    ];
    pythonImportsCheck = [ "wg_lux_mcp.asgi" ];
  };
in
{
  options.services.wg-lux-mcp = {
    enable = lib.mkEnableOption "wg-lux read-only MCP server";
    package = lib.mkOption {
      type = lib.types.package;
      default = defaultPackage;
      defaultText = lib.literalExpression "the in-tree wg-lux-mcp package";
      description = "Package containing the wg-lux-mcp Python application.";
    };
    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Optional environment file containing additional WG_LUX_MCP_* settings.";
    };
    hostname = lib.mkOption {
      type = lib.types.str;
      default = "wg-lux-mcp.local";
      description = "Machine-local hostname added to /etc/hosts and accepted by the MCP server.";
    };
    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 8765;
    };
    oauth = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Require Keycloak OAuth access tokens for the MCP endpoint.";
      };
      issuerUrl = lib.mkOption {
        type = lib.types.str;
        default = "https://${config.luxnix.generic-settings.network.keycloak.domain}/realms/master";
        description = "Keycloak realm issuer URL used to validate access tokens.";
      };
      clientId = lib.mkOption {
        type = lib.types.str;
        default = "wg-lux-mcp";
        description = "Keycloak client ID or token audience accepted by the MCP server.";
      };
      requiredScopes = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "openid" ];
        description = "OAuth scopes or Keycloak roles required by the MCP server.";
      };
      jwtAlgorithms = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "RS256" ];
        description = "Allowed Keycloak JWT signature algorithms.";
      };
    };
    repositorySources = {
      lxAnnotate = lib.mkOption {
        type = lib.types.str;
        default = "/home/admin/dev/lx-annotate";
        description = "Host path mounted read-only as the lx-annotate repository.";
      };
      endoregDb = lib.mkOption {
        type = lib.types.str;
        default = "/home/admin/endoreg-db";
        description = "Host path mounted read-only as the endoreg-db repository.";
      };
      lxDataModels = lib.mkOption {
        type = lib.types.str;
        default = "/home/admin/lx-data-models";
        description = "Host path mounted read-only as the lx-data-models repository.";
      };
    };
    user = lib.mkOption {
      type = lib.types.str;
      default = "wg-lux-mcp";
    };
    group = lib.mkOption {
      type = lib.types.str;
      default = "wg-lux-mcp";
    };
  };

  config = lib.mkIf cfg.enable {
    services.wg-lux-features.enable = true;
    networking.hosts."127.0.0.1" = [ cfg.hostname ];

    services.luxnix.lxSsl = {
      enable = lib.mkDefault true;
      extraDnsNames = lib.mkAfter [ cfg.hostname ];
    };

    services.nginx = {
      enable = true;
      recommendedProxySettings = true;
      recommendedTlsSettings = true;
      virtualHosts.${cfg.hostname} = {
        forceSSL = true;
        sslCertificate = sslCfg.certPath;
        sslCertificateKey = sslCfg.keyPath;
        extraConfig = ''
          ssl_stapling off;
          ssl_stapling_verify off;
        '';
        locations."/" = {
          proxyPass = "http://${cfg.host}:${toString cfg.port}";
          extraConfig = ''
            proxy_http_version 1.1;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_set_header Host $host;
          '';
        };
      };
    };

    users.users.${cfg.user} = {
      isSystemUser = true;
      inherit (cfg) group;
      extraGroups = [ config.services.wg-lux-features.group ];
    };
    users.groups.${cfg.group} = { };

    systemd.services.wg-lux-mcp = {
      description = "wg-lux MCP server";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      path = [ pkgs.git ];
      environment = {
        WG_LUX_MCP_HOST = cfg.host;
        WG_LUX_MCP_PORT = toString cfg.port;
        WG_LUX_MCP_PUBLIC_HOST = cfg.hostname;
        WG_LUX_MCP_OAUTH_ENABLED = lib.boolToString cfg.oauth.enable;
        WG_LUX_MCP_OAUTH_ISSUER_URL = cfg.oauth.issuerUrl;
        WG_LUX_MCP_OAUTH_CLIENT_ID = cfg.oauth.clientId;
        WG_LUX_MCP_OAUTH_REQUIRED_SCOPES = builtins.toJSON cfg.oauth.requiredScopes;
        WG_LUX_MCP_OAUTH_JWT_ALGORITHMS = builtins.toJSON cfg.oauth.jwtAlgorithms;
        WG_LUX_MCP_REPO_LX_ANNOTATE = "/srv/wg-lux/lx-annotate";
        WG_LUX_MCP_REPO_ENDOREG_DB = "/srv/wg-lux/endoreg-db";
        WG_LUX_MCP_REPO_LX_DATA_MODELS = "/srv/wg-lux/lx-data-models";
        WG_LUX_FEATURE_PROVIDER_REGISTRY = config.services.wg-lux-features.registryPath;
        WG_LUX_FEATURE_STATE_ROOT = config.services.wg-lux-features.stateRoot;
      };
      serviceConfig = {
        User = cfg.user;
        Group = cfg.group;
        EnvironmentFile = lib.optional (cfg.environmentFile != null) cfg.environmentFile;
        ExecStart = "${cfg.package}/bin/wg-lux-mcp";
        Restart = "on-failure";
        RestartSec = "2s";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectHome = true;
        ProtectSystem = "strict";
        BindReadOnlyPaths = [
          "-${cfg.repositorySources.lxAnnotate}:/srv/wg-lux/lx-annotate"
          "-${cfg.repositorySources.endoregDb}:/srv/wg-lux/endoreg-db"
          "-${cfg.repositorySources.lxDataModels}:/srv/wg-lux/lx-data-models"
        ];
        ReadOnlyPaths = [
          config.services.wg-lux-features.registryPath
          config.services.wg-lux-features.stateRoot
        ] ++ lib.mapAttrsToList (
          _provider: provider: "${provider.package}/${provider.featureSubdir}"
        ) config.services.wg-lux-features.providers;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        UMask = "0077";
      };
    };
  };
}
