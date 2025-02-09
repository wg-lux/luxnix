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

  nextcloudSslCertFile = config.luxnix.generic-settings.sslCertificatePath;
  nextcloudSslKeyFile = config.luxnix.generic-settings.sslCertificateKeyPath;

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
        # overwriteprotocol = "https";
      };
    };


    # manually run 
    
    # mc config host add minio http://localhost:9000 ${accessKey} ${secretKey} --api s3v4
    
    # mc config host add minio http://localhost:9000 nextcloud test12345 --api s3v4
    # mc mb minio/nextcloud
    



    services.minio = {
      enable = true;
      listenAddress = "127.0.0.1:9000";
      consoleAddress = "127.0.0.1:9001";
      inherit rootCredentialsFile;
    };

    # Add Service which runs before nginx as root and copies the secrets file to the nextcloud directory
    systemd.services.nextcloud-secrets = {
      description = "Copy SSL certificates for Nextcloud";
      requires = [ "local-fs.target" ];
      before = [ "nginx.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        Group = "root";
      };
      script = ''
        ${pkgs.sudo}/bin/sudo ${pkgs.coreutils}/bin/cp ${sslCertFile} ${nextcloudSslCertFile} 
        ${pkgs.sudo}/bin/sudo ${pkgs.coreutils}/bin/cp ${sslKeyFile} ${nextcloudSslKeyFile} 

      '';
    };


  environment.systemPackages = [ pkgs.minio-client ];

  networking.firewall.allowedTCPPorts = [ 80 443 ];

  };
}
