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

  accessKey = "nextcloud";
  secretKey = "test12345";

  rootCredentialsFile = pkgs.writeText "minio-credentials-full" ''
    MINIO_ROOT_USER=nextcloud
    MINIO_ROOT_PASSWORD=test12345
  '';

  vpnIp = config.luxnix.generic-settings.vpnIp;


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

    # TODO Should be on by default on nginx-host
    ## Add nginx to the sslCertGroupName
    users.users.nginx.extraGroups = [ sslCertGroupName ];
    
    networking.firewall.allowedTCPPorts = [ 80 443 8080 9000 ];

    networking.hosts = {
        "${vpnIp}" = [ cfg.hostname ];
    };

    services.nextcloud = {
      enable = true;
      configureRedis = true;
      package = cfg.package;
      hostName = cfg.hostname;
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
        prot = "http"; # or https
        host = "127.0.0.1";
        dir = ""; # e.g. "/nextcloud"
      in {
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
        # overwriteprotocol = prot;
        # overwritehost = host;
        # overwritewebroot = dir;
        # overwrite.cli.url = "${prot}://${host}${dir}/";
        # htaccess.RewriteBase = dir;
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
    services.nextcloud-secrets = {
      enable = true;
      description = ''
        Copy the secrets file to the nextcloud directory:
          ${sslCertFile} -> ${nextcloudSslCertFile} (Owner: nginx:${sslCertGroupName}, Permissions: 600)
          ${sslKeyFile} -> ${nextcloudSslKeyFile} (Owner: nginx:${sslCertGroupName}, Permissions: 600)
      '';
      script = ''
        ${pkgs.sudo}/bin/sudo ${pkgs.coreutils}/bin/cp ${sslCertFile} ${nextcloudSslCertFile} 
        ${pkgs.sudo}/bin/sudo ${pkgs.coreutils}/bin/cp ${sslKeyFile} ${nextcloudSslKeyFile} 

      '';
    };

    services.nginx.virtualHosts."${config.services.nextcloud.hostName}" = {
      sslCertificate = sslCertFile;
      sslCertificateKey = sslKeyFile;
      listen = [ 
        {
          addr = "127.0.0.1";
          port = 8080; # NOT an exposed port
        }
        { # listen to the VPN IP
          addr = "${vpnIp}";
          port = 443;
          ssl = true;
        }
      ];
    };

    environment.systemPackages = [ pkgs.minio-client ];


  };
}
