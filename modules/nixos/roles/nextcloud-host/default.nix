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

  nextcloudPwdFile = "/etc/nextcloud-admin-pass";
  minioSecretFile = "/etc/minio-secret";

  # Remove the hardcoded credentials
  rootCredentialsFile = "/etc/minio-credentials";

  accessKey = "nextcloud";


  nginxPrepareScript = pkgs.writeShellScript "nginx-prepare-files_nxtcld.sh" ''
    #!${pkgs.bash}/bin/bash
    set -e
    cp ${sslCertFile} ${nginx_cert_path}
    cp ${sslKeyFile} ${nginx_key_path}
    chown nginx:${sslCertGroupName} ${nginx_cert_path} ${nginx_key_path}
    chmod 600 ${nginx_cert_path} ${nginx_key_path}
  '';

  nextcloudPrepareScript = pkgs.writeShellScript "nextcloud-prepare-files_nxtcld.sh" ''
    #!${pkgs.bash}/bin/bash
    set -e
    
    # Copy admin password
    cp ${cfg.passwordFilePath} ${nextcloudPwdFile}
    chown nextcloud:nextcloud ${nextcloudPwdFile}
    chmod 640 ${nextcloudPwdFile}
    
    # Copy minio credentials
    cp ${cfg.minioCredentialsFilePath} ${rootCredentialsFile}
    chown minio:minio ${rootCredentialsFile}
    chmod 600 ${rootCredentialsFile}
    
    # Extract and store the minio secret separately for nextcloud
    # Use a more reliable method to extract the password
    cat ${rootCredentialsFile} | grep MINIO_ROOT_PASSWORD | cut -d'=' -f2 > ${minioSecretFile}
    chown nextcloud:nextcloud ${minioSecretFile}
    chmod 600 ${minioSecretFile}
    
    echo "Credentials prepared successfully" > /tmp/nextcloud-prepare-log
  '';

  conf = config.luxnix.generic-settings.network.nextcloud;



in
{
  options.roles.nextcloudHost = {
    enable = mkBoolOpt false "Enable Nextcloud";
    passwordFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
      description = "Path to the file containing the Nextcloud admin password";
    };
    customDir = mkOption {
      type = types.path;
      default = "/var/lib/nextcloud";
      description = "Path to the directory containing the Nextcloud configuration";
    };
    minioCredentialsFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_minio_credentials";
      description = "Path to the file containing the Minio admin credentials (format: MINIO_ROOT_USER=username\\nMINIO_ROOT_PASSWORD=password)";
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

    notifyPush = {
      enable = mkBoolOpt false "Enable Nextcloud Notify Push";
    };

    defaultPhoneRegion = mkOption {
      type = types.str;
      default = "DE";
      description = "Default phone region for Nextcloud";
    };
  };


  config = mkIf cfg.enable
    {
      roles.postgres.default.enable = mkForce false;
      roles.postgres.main.enable = mkForce false;
      # services.postgresql.enable = true;
      # add user nginx to nextcloud group
      users.users.nginx.extraGroups = [ "nextcloud" sslCertGroupName ];
      # users.users.nextcloud.extraGroups = [ sslCertGroupName ];
      # users.groups.nextcloudutils.members = [ "nextcloud" "nginx" ];
      users.users.nextcloud = {
        isSystemUser = true;
        group = "nextcloud";
        extraGroups = [ sslCertGroupName ];
        home = cfg.customDir;
      };
      programs.zsh.shellAliases = {
        show-psql-conf = "sudo cat /var/lib/postgresql/${config.services.postgresql.package.psqlSchema}/postgresql.conf";
        reset-psql = "sudo rm -rf /var/lib/postgresql/${config.services.postgresql.package.psqlSchema}"; #TODO Add to documentation
        reset-minio = "sudo rm -rf /var/lib/minio";
        reset-nextcloud = "sudo rm -rf ${cfg.customDir}";
      };

      # manually run 
      #TODO Check if actually necessary and add to docs
      # mc config host add minio http://localhost:9000 ${accessKey} ${secretKey} --api s3v4
      # mc mb minio/nextcloud
      services.minio = {
        enable = true;
        listenAddress = "127.0.0.1:9000";
        consoleAddress = "127.0.0.1:9001";
        inherit rootCredentialsFile;
      };

      environment.systemPackages = [ pkgs.minio-client cfg.package pkgs.clamav ];
      networking.firewall.allowedTCPPorts = [ 80 443 3002 ];

      # systemd.tmpfiles.rules = [
      #   "d /etc/nextcloud 0770 nextcloud nextcloud -"
      #   "d /var/lib/nextcloud 0770 nextcloud nextcloud -"
      #   "d /var/lib/nextcloud/config 0770 nextcloud nextcloud -"
      # ];

      systemd.tmpfiles.rules = map (dir: "d ${dir} 0750 nextcloud nextcloud - -") [
        "${cfg.customDir}"
        "${cfg.customDir}/config"
        "${cfg.customDir}/data"
        "${cfg.customDir}/store-apps"
      ] ++ [
        "d /var/lib/minio 0750 minio minio - -"
        "d /var/lib/minio/data 0750 minio minio - -"
        "d /var/lib/minio/config 0750 minio minio - -"
      ];

      services.nextcloud-whiteboard-server = {
        enable = true;
        settings.NEXTCLOUD_URL = "http://cloud.endo-reg.net";
        secrets = [
          #TODO Docs: Create manually, e.g.:
          # JWT_SECRET_KEY=SUPER_SECRET_KEY_VALUE
          # configure app via terminal or console:
          # nextcloud-occ config:app:set whiteboard collabBackendUrl --value="http://localhost:3002"
          # nextcloud-occ config:app:set whiteboard jwt_secret_key --value="test123"
          "/etc/nextcloud-jwt"
        ];
      };

      services.nextcloud = {
        enable = true;
        package = cfg.package;

        config = {
          dbuser = "nextcloud"; # default = "nextcloud";
          dbtype = "pgsql"; # default = "sqlite";
          dbname = "nextcloud"; # default = "nextcloud";

          # Username for the admin account.
          # The username is only set during the initial setup of Nextcloud! 
          # Since the username also acts as unique ID internally, it 
          # cannot be changed later!
          adminuser = "agl-admin"; # default = "root";

          # The full path to a file that contains the admin’s password. 
          # Must be readable by user nextcloud. The password is set only in the 
          # initial setup of Nextcloud by the 
          # systemd service nextcloud-setup.service.
          adminpassFile = nextcloudPwdFile; # default = "/etc/nextcloud-admin-pass";

          ## defaults to socket for sqlite and pgsql if createLocally is true
          # dbhost = "localhost"; # default = "localhost"; 
          # dbpassFile = ; # defualt is null
          objectstore.s3 = {
            enable = true;
            bucket = "nextcloud";
            autocreate = true;
            key = accessKey;
            secretFile = minioSecretFile;
            hostname = "localhost";
            useSsl = false;
            port = 9000;
            usePathStyle = true;
            region = "us-east-1";
          };

          # Configure ClamAV executable location:
          # "files_antivirus.clamscan_path" = "${pkgs.clamav}/bin/clamscan";
          # Add ClamAV daemon socket setting:
          # Set manually in UI:
          # "files_antivirus.clamd_socket" = "/run/clamav/clamd.ctl"; 
        };

        # Extra options which should be appended to 
        # Nextcloud’s config.php file.
        settings = {
          trusted_proxies = [
            config.luxnix.generic-settings.network.nginx.vpnIp
            config.luxnix.generic-settings.vpnIp
          ];
          trusted_domains = [ "localhost" conf.domain ];

          # The directory where the skeleton files are located. 
          # These files will be copied to the data directory of new users. 
          # Leave empty to not copy any skeleton files.
          skeleton_directory = "";

          # Force Nextcloud to always use HTTP or HTTPS i.e. for link generation. 
          # Nextcloud uses the currently used protocol by default, 
          # but when behind a reverse-proxy, it may use http for everything
          # although Nextcloud may be served via HTTPS.
          overwriteprotocol = "https"; # default = "" 
          overwritehost = conf.domain; # default = "";

          # 1 (info): Log activity such as user logins and file activities, 
          # plus warnings, errors, and fatal errors.
          loglevel = 1; # default = 2;
          log_type = "file"; # default = "file";

          # An ISO 3166-1 country code which replaces automatic 
          # phone-number detection without a country code.
          # As an example, with DE set as the default phone region,
          # the +49 prefix can be omitted for phone numbers.
          default_phone_region = cfg.defaultPhoneRegion; # default = "";


          # By default, the following properties are set to 
          # “Show to everyone” if this flag is enabled:
          # About
          # Full name
          # Headline
          # Organisation
          # Profile picture
          # Role
          # Twitter
          "profile.enabled" = true; # default = false;

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

          mail_smtpmode = "smtp";
          mail_smtpsecure = "ssl";
          mail_sendmailmode = "smtp";
          mail_smtpport = "465";
          mail_smtpauth = "1";
          mail_smtpauthtype = "LOGIN";
          mail_domain = "endo-reg.net";
        };

        # ###### Hosting ######
        https = true; # default = false;
        hostName = conf.domain; # "localhost"
        nginx = {
          recommendedHttpHeaders = true; # default = true
          hstsMaxAge = 15552000; # default = 15552000;
        };

        # ###### Database ########
        database.createLocally = true;

        # Other relevant options
        maxUploadSize = cfg.maxUploadSize; # default = "2G"; (nextcloud default is 512M)
        home = cfg.customDir; # default = "/var/lib/nextcloud";
        # datadir = config.services.nextcloud.home; # default
        enableImagemagick = true; # default = true;
        configureRedis = true;
        caching = {
          redis = true; # default = false
        };

        autoUpdateApps = {
          enable = true;
          startAt = "05:00:00"; # e.g., "Sun 14:00:00"
        };

        # Automatically enable the apps in services.nextcloud.extraApps
        # every time Nextcloud starts. If set to false, 
        # apps need to be enabled in the Nextcloud web user interface 
        # or with nextcloud-occ app:enable.
        appstoreEnable = true;
        extraAppsEnable = false; # default = true;

        # ###### PHP ######
        # phpExtraExtensions = all: [ all.pdlib all.bz2 ];

        phpOptions = {
          catch_workers_output = "yes";
          display_errors = "stderr";
          error_reporting = "E_ALL & ~E_DEPRECATED & ~E_STRICT";
          expose_php = "Off";
          "opcache.fast_shutdown" = "1";
          "opcache.interned_strings_buffer" = "16"; # default is 8
          "opcache.max_accelerated_files" = "10000";
          "opcache.memory_consumption" = "128";
          "opcache.revalidate_freq" = "1";

          # Not required as we use http after reverse proxy ? #TODO Verify
          "openssl.cafile" = "/etc/ssl/certs/ca-certificates.crt";
          output_buffering = "0";
          short_open_tag = "Off";
        };

        # Secret options which will be appended to Nextcloud’s config.php file (written as JSON, in the same form as 
        # the services.nextcloud.settings option), for example 
        # {"redis":{"password":"secret"}}.
        # default is null
        # secretFile = ;

        # Options for nextcloud’s PHP pool. See the documentation on 
        # php-fpm.conf for details on configuration directives
        # poolSettings = ;

        # Options for Nextcloud’s PHP pool. See the documentation on 
        # php-fpm.conf for details on configuration directives
        # poolConfig = ;


        ### Notify Push
        notify_push = {
          enable = cfg.notifyPush.enable;
          package = pkgs.nextcloud-notify_push;
          socketPath = "/run/nextcloud-notify_push/sock";
          logLevel = "error"; # one of "error", "warn", "info", "debug", "trace"
          dbuser = config.services.nextcloud.config.dbuser; # string
          dbtype = config.services.nextcloud.config.dbtype; # one of "sqlite", "pgsql", "mysql"

          # TODO when migrating to pgsql, separate pwd provision might make sense
          dbpassFile = config.services.nextcloud.config.dbpassFile; # path
          dbname = config.services.nextcloud.config.dbname;

          # Database host (+port) or socket path. 
          # If services.nextcloud.database.createLocally is true and
          # services.nextcloud.config.dbtype is either pgsql or mysql,
          # defaults to the correct Unix socket instead.
          # dbhost = config.services.nextcloud.config.dbhost;

          # Whether to add an entry to /etc/hosts for 
          # the configured nextcloud domain to point to 
          # localhost and add localhost to nextcloud’s trusted_proxies 
          # config option.
          # This is useful when nextcloud’s domain is not a 
          # static IP address and when the reverse proxy cannot
          # be bypassed because the backend connection is done via
          # unix socket.
          bendDomainToLocalhost = false; # default = false

        };

        #### Other Options ####
        fastcgiTimeout = 120; # default = 120;


      };

      ########################### COLLABORA ############################
      # Set in UI:
      #   wopi_url = "http://[::1]:${toString config.services.collabora-online.port}";
      # public_wopi_url = "https://collabora.example.com";
      # wopi_allowlist = lib.concatStringsSep "," [
      #   "127.0.0.1"
      #   "::1"
      # ];

      services.collabora-online = {
        enable = true;
        port = 9980; # default
        settings = {
          # Rely on reverse proxy for SSL
          ssl = {
            enable = false;
            termination = true;
          };

          # Listen on loopback interface only, and accept requests from ::1
          net = {
            listen = "loopback";
            post_allow.host = [ "::1" ];
          };

          # Restrict loading documents from WOPI Host nextcloud.example.com
          storage.wopi = {
            "@allow" = true;
            host = [ "cloud.endo-reg.net" ];
          };

          # Set FQDN of server
          server_name = "collabora.endo-reg.net";
        };
      };

      services.nginx = {
        enable = true;
        # I recommend these, but it's up to you
        recommendedProxySettings = true;
        recommendedTlsSettings = true;

        virtualHosts."collabora.endo-reg.net" = {
          locations."/" = {
            proxyPass = "http://[::1]:${toString config.services.collabora-online.port}";
            proxyWebsockets = true; # collabora uses websockets
          };
        };
      };

      networking.hosts = {
        "127.0.0.1" = [ "cloud.endo-reg.net" "collabora.endo-reg.net" ];
        "::1" = [ "cloud.endo-reg.net" "collabora.endo-reg.net" ];
      };


      # Add a post-install hook to fix permissions
      # systemd.services.nextcloud-setup = {
      #   serviceConfig = {
      #     ExecStartPost = "${pkgs.bash}/bin/bash -c 'chown -R nextcloud:nextcloud /var/lib/nextcloud/config && chmod -R 770 /var/lib/nextcloud/config'";
      #   };
      # };

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

      # Add systemd service to prepare files
      systemd.services.nextcloud-prepare-files = {
        description = "Prepare files for Nextcloud";
        wantedBy = [ "multi-user.target" ];
        before = [ "nextcloud-setup.service" "minio.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = "${nextcloudPrepareScript}";
        };
      };

      # Add post-install hook for minio
      systemd.services.minio = {
        after = [ "nextcloud-prepare-files.service" ];
        requires = [ "nextcloud-prepare-files.service" ];
      };

    };
}
