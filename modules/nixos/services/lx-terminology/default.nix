{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.luxnix.lxTerminology;
  python = pkgs.python3.withPackages (ps: [
    ps.flask
    ps.gunicorn
    ps.pyyaml
  ]);
  source = builtins.path {
    path = ./.;
    name = "lx-terminology-server";
    filter =
      path: type:
      type == "directory"
      || builtins.elem (baseNameOf path) [
        "server.py"
        "index.html"
      ];
  };
in
{
  options.services.luxnix.lxTerminology = {
    enable = lib.mkEnableOption "LX terminology package host";
    domain = lib.mkOption {
      type = lib.types.str;
      description = "Public HTTPS hostname.";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 8791;
      description = "Loopback HTTP port.";
    };
    uploadTokenFile = lib.mkOption {
      type = lib.types.str;
      description = "Runtime file containing a random upload bearer token (at least 32 characters).";
    };
    certificateFile = lib.mkOption {
      type = lib.types.str;
      description = "Runtime TLS certificate path, managed by the host.";
    };
    certificateKeyFile = lib.mkOption {
      type = lib.types.str;
      description = "Runtime TLS private key path, managed by the host.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = builtins.match "[A-Za-z0-9.-]+" cfg.domain != null;
        message = "lxTerminology.domain must be a hostname.";
      }
    ];
    systemd.services.lx-terminology = {
      description = "LX terminology runtime package store";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      environment = {
        LX_TERMINOLOGY_DATABASE = "/var/lib/lx-terminology/packages.sqlite3";
        LX_TERMINOLOGY_TOKEN_FILE = "%d/upload-token";
        LX_TERMINOLOGY_PUBLIC_URL = "https://${cfg.domain}";
      };
      serviceConfig = {
        ExecStart = "${python}/bin/gunicorn --bind 127.0.0.1:${toString cfg.port} --workers 2 --timeout 120 --chdir ${source} 'server:create_app()'";
        LoadCredential = "upload-token:${cfg.uploadTokenFile}";
        DynamicUser = true;
        StateDirectory = "lx-terminology";
        StateDirectoryMode = "0700";
        UMask = "0077";
        Restart = "on-failure";
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        NoNewPrivileges = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_UNIX"
        ];
      };
    };
    services.nginx.enable = true;
    services.nginx.virtualHosts.${cfg.domain} = {
      forceSSL = true;
      sslCertificate = cfg.certificateFile;
      sslCertificateKey = cfg.certificateKeyFile;
      locations."/" = {
        proxyPass = "http://127.0.0.1:${toString cfg.port}";
        extraConfig = ''
          client_max_body_size 64m;
          proxy_read_timeout 120s;
        '';
      };
    };
    networking.firewall.allowedTCPPorts = [
      80
      443
    ];
  };
}
