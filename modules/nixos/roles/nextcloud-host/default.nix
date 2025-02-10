{config, lib, pkgs, ...}: 


# Useful documentation: 
# https://github.com/helsinki-systems/nc4nix (Nextcloud4Nix)
# https://nixos.wiki/wiki/Nextcloud

with lib; 
with lib.luxnix; let
  cfg = config.roles.nextcloudHost;

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
    hostname = mkOption {
      type = types.str;
      default = "cloud.endo-reg.net";
      description = "Hostname for the Nextcloud instance";
    };
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

    # make sure nextcloud user and group exist; nextcloud is systemuser
    # make sure nextcloud dir exists with correct permissions (750) (nextcloud:nextcloud)
    # make sure nextcloud has extra group sslCert
    # make sure nextcloud has access to sslCert files
    # make sure nextcloud has access to sslKey files
    # make sure nextcloud has access to /etc/nextcloud-admin-pass

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
      enable = true;
      https = false;
      configureRedis = true;
      package = cfg.package;
      hostName = "cloud.endo-reg.net"; 
      extraApps = {
        inherit (config.services.nextcloud.package.packages.apps) news contacts calendar tasks forms;
      };
      extraAppsEnable = true;
      maxUploadSize = cfg.maxUploadSize;
      config.adminuser = "root";
      config.adminpassFile = "/etc/nextcloud-admin-pass"; # initial pwd for user "root"
      config.dbtype = "sqlite";
      config.objectstore.s3 = {
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

      settings = let
      in {
        trusted_domains = [ "localhost" "cloud.endo-reg.net" ];
        trusted_proxies = [ config.luxnix.generic-settings.network.nginx.vpnIp "172.16.255.12" ];
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
        # overwritehost = "cloud.endo-reg.net";
        # overwriteprotocol = "http";
      };
    };


    # manually run 
    
    # mc config host add minio http://localhost:9000 ${accessKey} ${secretKey} --api s3v4
    
    # mc config host add minio http://localhost:9000 nextcloud test12345 --api s3v4
    # mc mb minio/nextcloud
    
    services.nginx.virtualHosts."cloud.endo-reg.net" = {
      forceSSL = true;
      sslCertificate = nginx_cert_path;
      sslCertificateKey = nginx_key_path;
      locations."/" = {
        proxyPass = "http://localhost";
      };
    };

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

  networking.firewall.allowedTCPPorts = [ 443 ];

  };
}
