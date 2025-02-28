{ config, lib, pkgs, ... }:


# Useful documentation: 
# https://github.com/helsinki-systems/nc4nix (Nextcloud4Nix)
# https://nixos.wiki/wiki/Nextcloud

#TODO Docs:
# To reset delete stateful dirs:
# rm -r /var/lib/postgresql /var/lib/nextcloud

with lib;
with lib.luxnix; let
  cfg = config.roles.nextcloudHost;

  ncApps = config.services.nextcloud.package.packages.apps;

  sslCertFile = config.luxnix.generic-settings.sslCertificatePath;
  sslKeyFile = config.luxnix.generic-settings.sslCertificateKeyPath;
  sslCertGroupName = config.users.groups.sslCert.name;

  nginx_cert_path = "/etc/nginx-host/ssl_cert";
  nginx_key_path = "/etc/nginx-host/ssl_key";

  lxVaultDir = config.luxnix.vault.dir;

  nextcloudPwdFile = cfg.customDir + "/admin-pwd";
  rootCredentialsFile = cfg.customDir + "/minio_cred";
  accessKey = "nextcloud";


  nginxPrepareScript = pkgs.writeScript "nginx-prepare-files_nxtcld.sh" ''
    #!/bin/sh
    set -e
    cp ${sslCertFile} ${nginx_cert_path}
    cp ${sslKeyFile} ${nginx_key_path}
    chown nginx:sslCert ${nginx_cert_path} ${nginx_key_path}
    chmod 600 ${nginx_cert_path} ${nginx_key_path}
  '';

  nextcloudPrepareScript = pkgs.writeScript "nextcloud-prepare-files_nxtcld.sh" ''
    #!/bin/sh
    set -e
    cp ${cfg.passwordFilePath} /etc/nextcloud-admin-pass
    chown root:nextcloud /etc/nextcloud-admin-pass
    chmod 600 /etc/nextcloud-admin-pass
  '';

  conf = config.luxnix.generic-settings.network.nextcloud;



in
{
  options.roles.nextcloudHost = {
    enable = mkBoolOpt false "Enable NGINX";
    passwordFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
      description = "Path to the file containing the Nextcloud admin password";
    };
    customDir = mkOption {
      type = types.path;
      default = "/etc/nextcloud";
      description = "Path to the directory containing the Nextcloud configuration";
    };
    minioCredentialsFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/minio_cred";
      description = "Path to the file containing the Minio admin credentials";
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

    #FIXME Needs to be hardened
    # Make sure the nextcloud config dir exists and is owned by the right user


    users.users.nextcloud = {
      isSystemUser = true;
      group = "nextcloud";
      extraGroups = [ sslCertGroupName ];
    };

    # make group nextcloudutils and make sure nextcloud and nginx are in it
    users.groups.nextcloudutils = {
      members = [ "nextcloud" "nginx" ];
    };

    # make sure directories exist and are owned by the right user / group
    systemd.tmpfiles.rules = [
      "d /etc/nginx-host 0700 nginx nginx -"
      "d /etc/nextcloud 0770 nextcloud nextcloudutils -"
      "d /var/lib/nextcloud 0750 nextcloud nextcloud -"
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


    # environment.etc."noip-smtp-pass".text = "ReplaceThisWithYourSecret";

    services.postgresql.enable = true;

    services.nextcloud = {
      enable = true;
      https = false; # ssl is terminated by reverse proxy
      package = cfg.package;
      hostName = conf.domain;
      maxUploadSize = cfg.maxUploadSize;
      home = cfg.customDir;
      notify_push.enable = true;
      # datadir = is home by default
      appstoreEnable = true;


      # Applications
      # Available apps: https://github.com/NixOS/nixpkgs/blob/master/pkgs/servers/nextcloud/packages/nextcloud-apps.json
      extraAppsEnable = false;
      # extraApps = {
      #   inherit (ncApps) news contacts calendar tasks forms;
      #   inherit (ncApps) groupfolders deck notes polls;
      #   inherit (ncApps) music memories;

      #   ## Example of adding a custom app      
      #   # cookbook = pkgs.fetchNextcloudApp rec {
      #   #   url =
      #   #     "https://github.com/nextcloud/cookbook/releases/download/v0.10.2/Cookbook-0.10.2.tar.gz";
      #   #   sha256 = "sha256-XgBwUr26qW6wvqhrnhhhhcN4wkI+eXDHnNSm1HDbP6M=";
      #   # };

      # };

      # EXPECTS THAT ONLY NEXTCLOUD USES PSQL
      database.createLocally = true;

      # Maintenance
      autoUpdateApps.enable = true;
      configureRedis = true;

      config = {
        adminuser = "root";
        adminpassFile = "/etc/nextcloud-admin-pass"; # initial pwd for user "root"
        dbtype = "mysql";
        # dbhost = "127.0.0.1";

        objectstore.s3 = {
          enable = true;
          bucket = "nextcloud";
          autocreate = true;
          key = accessKey;
          secretFile = "${pkgs.writeText "secret" "test12345"}"; #FIXME
          hostname = "localhost";
          useSsl = false;
          port = 9000;
          usePathStyle = true;
          region = "us-east-1";
        };
        # Remove or comment the clamscan_path setting:
        # "files_antivirus.clamscan_path" = "${pkgs.clamav}/bin/clamscan";
        # Add ClamAV daemon socket setting:
        "files_antivirus.clamd_socket" = "/run/clamav/clamd.ctl";
      };

      phpOptions = {
        "opcache.interned_strings_buffer" = "32";
      };


      settings =
        let
          # see also: https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/config_sample_php_parameters.html
        in
        {
          "profile.enabled" = true;
          default_phone_region = "DE";
          trusted_domains = [ "localhost" "cloud.endo-reg.net" ];
          trusted_proxies = [
            config.luxnix.generic-settings.network.nginx.vpnIp
            config.luxnix.generic-settings.vpnIp
          ];
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


    services.clamav = {
      daemon.enable = true;
      daemon.settings = {
        DatabaseDirectory = "/var/lib/clamav";
        LocalSocket = "/run/clamav/clamd.ctl";
        PidFile = "/run/clamav/clamd.pid";
        User = "clamav";
        Foreground = true;
      };
      updater.enable = true;
      updater.interval = "hourly";
      scanner.enable = true;
      scanner.scanDirectories = [
        "/home"
        "/var/lib"
        "/tmp"
        "/etc"
        "/var/tmp"
      ];
      scanner.interval = "*-*-* 04:00:00";
    };

    environment.systemPackages = [ pkgs.minio-client cfg.package pkgs.clamav ];

    networking.firewall.allowedTCPPorts = [ 80 443 ];

  };
}
