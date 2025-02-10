{config, lib, pkgs, ...}: 


# Useful documentation: 
# https://github.com/helsinki-systems/nc4nix (Nextcloud4Nix)
# https://nixos.wiki/wiki/Nextcloud

with lib; 
with lib.luxnix; let
  cfg = config.roles.nextcloudHost;

  ncApps = config.services.nextcloud.package.packages.apps;

  sslCertFile = config.luxnix.generic-settings.sslCertificatePath;
  sslKeyFile = config.luxnix.generic-settings.sslCertificateKeyPath;
  sslCertGroupName = config.users.groups.sslCert.name;

  nginx_cert_path = "/etc/nginx-host/ssl_cert";
  nginx_key_path = "/etc/nginx-host/ssl_key";

  nginxPrepareScript = pkgs.writeScript "nginx-prepare-files_nxtcld.sh" ''
    #!/bin/sh
    set -e
    cp ${sslCertFile} ${nginx_cert_path}
    cp ${sslKeyFile} ${nginx_key_path}
    chown nginx:sslCert ${nginx_cert_path} ${nginx_key_path}
    chmod 600 ${nginx_cert_path} ${nginx_key_path}
  '';

  conf = config.luxnix.generic-settings.network.nextcloud;

  accessKey = "nextcloud";
  secretKey = "test12345";

  rootCredentialsFile = pkgs.writeText "minio-credentials-full" ''
    MINIO_ROOT_USER=nextcloud
    MINIO_ROOT_PASSWORD=test12345
  '';


in {
  options.roles.nextcloudHost = {
    enable = mkBoolOpt false "Enable NGINX";
    passwordFilePath = mkOption {
      type = types.path;
      default = "/etc/nextcloud-admin-pass";
      description = "Path to the file containing the Nextcloud admin password";
    };

    secretFile = mkOption {
      type = types.path;
      default = "/etc/nextcloud-secrets.json";
      description = "Path to the file containing the Nextcloud admin password";
    };

    package = mkOption {
      type = types.package;
      default = pkgs.nextcloud30;
      description = "The Nextcloud package to install";
    };

    maxUploadSize = mkOption {
      type = types.str;
      default = "2G";
      description = "Maximum upload size for Nextcloud";
    };
  };

  config = mkIf cfg.enable {

    users.users.nextcloud = {
      isSystemUser = true;
      home = "/var/lib/nextcloud";
      group = "nextcloud";
      extraGroups = [ sslCertGroupName ];
    };
    
    # TODO Service to supply from vault
    environment.etc."nextcloud-admin-pass" = {
      text = "InitialDefaultPWD123!";
    };

    services.nextcloud = {
      enable = cfg.enable;
      https = false; # ssl is terminated by reverse proxy
      enableBrokenCiphersForSSE = false;
      package = cfg.package;
      hostName = conf.domain;
      maxUploadSize = cfg.maxUploadSize;


      # Applications
      # Available apps: https://github.com/NixOS/nixpkgs/blob/master/pkgs/servers/nextcloud/packages/nextcloud-apps.json
      extraAppsEnable = true;
      extraApps = {
        inherit (ncApps) news contacts calendar tasks forms;
        inherit (ncApps) groupfolders deck notes polls;
        inherit (ncApps) integration_paperless twofactor_totp sociallogin previewgenerator end_to_end_encryption;
        inherit (ncApps) music memories files_markdown files_automatedtagging files_mindmap files_retention files_texteditor;

        ## Example of adding a custom app      
        # cookbook = pkgs.fetchNextcloudApp rec {
        #   url =
        #     "https://github.com/nextcloud/cookbook/releases/download/v0.10.2/Cookbook-0.10.2.tar.gz";
        #   sha256 = "sha256-XgBwUr26qW6wvqhrnhhhhcN4wkI+eXDHnNSm1HDbP6M=";
        # };

      };
      
      database.createLocally = true;

      # Maintenance
      autoUpdateApps.enable = true;


      configureRedis = true;

      config = {
        adminuser = "root";
        adminpassFile = "/etc/nextcloud-admin-pass"; # initial pwd for user "root"
        dbtype = "pgsql";
        objectstore.s3 = {
          enable = true;
          bucket = "nextcloud";
          autocreate = true;
          key = accessKey;
          secretFile = "${pkgs.writeText "secret" "test12345"}";
          hostname = "localhost";
          useSsl = false;
          port = 9000;
          usePathStyle = true;
          region = "us-east-1";
        };
      };
      
      settings = let
      in {
        trusted_domains = [ "localhost" "cloud.endo-reg.net"];
        trusted_proxies = [ 
          config.luxnix.generic-settings.network.nginx.vpnIp 
          config.luxnix.generic-settings.network.nextcloud.vpnIp 
        ];
        mail_smtpmode = "sendmail";
        mail_sendmailmode = "pipe";
        enabledPreviewProviders = [
          "OC\\Preview\\BMP"
          "OC\\Preview\\GIF"
          "OC\\Preview\\JPEG"
          "OC\\Preview\\Krita"
          "OC\\Preview\\MarkDown"
          "OC\\Preview\\MP3"
          "OC\\Preview\\OpenDocument"
          "OC\\Preview\\PNG"
          "OC\\Preview\\TXT"
          "OC\\Preview\\XBitmap"
          "OC\\Preview\\HEIC"
        ];
        overwritehost = "cloud.endo-reg.net";
        overwriteprotocol = "https";
      };
    };


    # manually run 
    #TODO Add to docs
    # mc config host add minio http://localhost:9000 ${accessKey} ${secretKey} --api s3v4
    # mc config host add minio http://localhost:9000 nextcloud test12345 --api s3v4
    # mc mb minio/nextcloud
    
    services.nginx.virtualHosts."${config.services.nextcloud.hostName}".listen = [ 
      {
        addr = config.luxnix.generic-settings.vpnIp;
        port = 80; # NOT an exposed port
      } 
    ];


    services.minio = {
      enable = true;
      listenAddress = "127.0.0.1:9000";
      consoleAddress = "127.0.0.1:9001";
      inherit rootCredentialsFile;
    };

    # systemd.tmpfile.rule to make sure /etc/nginx-host exists
    systemd.tmpfiles.rules = [
      "d /etc/nginx-host 0700 nginx nginx -"
    ];

    systemd.services.nginx-prepare-files = {
      description = "Deploy SSL certificate and key for NGINX";
      before = [ "nginx.service" ];
      requiredBy = [ "nginx.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${nginxPrepareScript}";
      };
    };

  environment.systemPackages = [ pkgs.minio-client cfg.package];

  networking.firewall.allowedTCPPorts = [ 80 443 ];

  };
}
