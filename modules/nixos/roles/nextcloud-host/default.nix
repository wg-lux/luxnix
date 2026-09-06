{
  config,
  lib,
  pkgs,
  ...
}:

# Useful documentation:
# https://github.com/helsinki-systems/nc4nix (Nextcloud4Nix)
# https://nixos.wiki/wiki/Nextcloud

# Safe maintenance operations documented in README.md
# Use 'nextcloud-maintenance' script for safe data reset operations

with lib;
with lib.luxnix;
let
  cfg = config.roles.nextcloudHost;

  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  sslCertGroupName = sensitiveServicesGroupName;

  nextcloudPwdFile = "/etc/nextcloud-admin-pass";

  # Nextcloud's S3 primary storage runs against a local single-node Garage
  # instance (MinIO was removed from nixpkgs in 26.05). The access-key ID is
  # not secret and is set per host; the matching secret key, the Garage RPC
  # secret, and the admin token are delivered together in one Vault file.
  s3SecretFile = "/etc/nextcloud-s3-secret";
  garageEnvFile = "/run/nextcloud-garage/garage.env";
  garageS3Port = 3900;
  garageRegion = "garage";

  # Safe maintenance script for resetting Nextcloud services
  nextcloudMaintenanceScript = pkgs.writeScriptBin "nextcloud-maintenance" ''
    #!${pkgs.zsh}/bin/zsh
    set -e

    show_help() {
      echo "Nextcloud Maintenance Script"
      echo "Usage: $0 [OPTION]"
      echo ""
      echo "Options:"
      echo "  --reset-psql       Reset PostgreSQL data (interactive confirmation required)"
      echo "  --reset-garage     Reset Garage object-store data (interactive confirmation required)"
      echo "  --reset-all        Reset all Nextcloud data (interactive confirmation required)"
      echo "  --show-psql-conf   Show PostgreSQL configuration"
      echo "  --help             Show this help message"
      echo ""
      echo "WARNING: Reset operations will permanently delete data!"
      echo "Make sure to backup your data before running any reset commands."
    }

    confirm_action() {
      local service="$1"
      local path="$2"
      echo "WARNING: This will permanently delete all $service data at $path"
      echo "This action cannot be undone!"
      echo -n "Are you sure you want to proceed? Type 'yes' to continue: "
      read confirmation
      if [ "$confirmation" != "yes" ]; then
        echo "Operation cancelled."
        exit 1
      fi
    }

    stop_services() {
      echo "Stopping services..."
      sudo systemctl stop nextcloud-setup.service nextcloud-cron.service nginx.service postgresql.service garage.service || true
    }

    start_services() {
      echo "Starting services..."
      sudo systemctl start postgresql.service garage.service nginx.service || true
    }

    reset_postgresql() {
      local psql_dir="/var/lib/postgresql/${config.services.postgresql.package.psqlSchema}"
      
      if [ ! -d "$psql_dir" ]; then
        echo "PostgreSQL data directory $psql_dir does not exist."
        return 0
      fi

      confirm_action "PostgreSQL" "$psql_dir"
      
      echo "Stopping services before PostgreSQL reset..."
      stop_services
      
      echo "Removing PostgreSQL data directory: $psql_dir"
      sudo rm -rf "$psql_dir"
      
      echo "PostgreSQL data has been reset. You will need to reconfigure the database."
      echo "Consider running: nixos-rebuild switch to reinitialize services."
    }

    reset_garage() {
      local garage_dir="/var/lib/garage"

      if [ ! -d "$garage_dir" ]; then
        echo "Garage data directory $garage_dir does not exist."
        return 0
      fi

      confirm_action "Garage" "$garage_dir"

      echo "Stopping services before Garage reset..."
      stop_services

      echo "Removing Garage data directory: $garage_dir"
      sudo rm -rf "$garage_dir"

      echo "Garage data has been reset. garage-bootstrap.service will re-apply"
      echo "the cluster layout, key, and bucket on the next start."
      echo "Consider running: nixos-rebuild switch to reinitialize services."
    }

    reset_all() {
      echo "This will reset ALL Nextcloud-related data!"
      confirm_action "ALL Nextcloud services" "/var/lib/postgresql and /var/lib/garage"

      reset_postgresql
      reset_garage

      echo "All Nextcloud data has been reset."
      echo "Run: nixos-rebuild switch to reinitialize all services."
    }

    show_psql_conf() {
      local psql_conf="/var/lib/postgresql/${config.services.postgresql.package.psqlSchema}/postgresql.conf"
      if [ -f "$psql_conf" ]; then
        sudo cat "$psql_conf"
      else
        echo "PostgreSQL configuration file not found at: $psql_conf"
        echo "PostgreSQL may not be initialized yet."
      fi
    }

    case "''${1:-}" in
      --reset-psql)
        reset_postgresql
        ;;
      --reset-garage)
        reset_garage
        ;;
      --reset-all)
        reset_all
        ;;
      --show-psql-conf)
        show_psql_conf
        ;;
      --help|"")
        show_help
        ;;
      *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
  '';

  # Runs before both garage.service and nextcloud-setup.service. Splits the
  # single delivered Vault file
  #   NEXTCLOUD_S3_SECRET_KEY=<64 hex>
  #   GARAGE_RPC_SECRET=<64 hex>
  #   GARAGE_ADMIN_TOKEN=<token>
  # into the S3 secret Nextcloud reads and the environment file systemd feeds
  # to Garage (read by systemd as root, so root-only is fine).
  nextcloudPrepareScript = pkgs.writeShellScript "nextcloud-prepare-files_nxtcld.sh" ''
    set -eu

    umask 077

    # Admin password
    install -o nextcloud -g nextcloud -m 0640 ${cfg.passwordFilePath} ${nextcloudPwdFile}

    creds=${cfg.garageCredentialsFilePath}
    get() { ${pkgs.gnugrep}/bin/grep -E "^$1=" "$creds" | ${pkgs.coreutils}/bin/head -n1 | ${pkgs.coreutils}/bin/cut -d= -f2-; }

    # S3 secret key for Nextcloud's object store
    printf '%s' "$(get NEXTCLOUD_S3_SECRET_KEY)" > ${s3SecretFile}
    chown nextcloud:nextcloud ${s3SecretFile}
    chmod 0600 ${s3SecretFile}

    # Environment file for garage.service
    install -d -m 0700 "$(${pkgs.coreutils}/bin/dirname ${garageEnvFile})"
    {
      printf 'GARAGE_RPC_SECRET=%s\n' "$(get GARAGE_RPC_SECRET)"
      printf 'GARAGE_ADMIN_TOKEN=%s\n' "$(get GARAGE_ADMIN_TOKEN)"
    } > ${garageEnvFile}
    chmod 0600 ${garageEnvFile}
  '';

  # Runs once after garage.service: applies the single-node cluster layout,
  # imports the deterministic S3 key, and creates the bucket. Every step is
  # guarded so the unit is idempotent and safe to re-run after `--reset-garage`.
  garageBootstrapScript = pkgs.writeShellScript "nextcloud-garage-bootstrap.sh" ''
    set -eu

    # GARAGE_RPC_SECRET / GARAGE_ADMIN_TOKEN for the CLI to reach the local RPC.
    set -a
    . ${garageEnvFile}
    set +a

    garage=${pkgs.garage_1}/bin/garage
    grep=${pkgs.gnugrep}/bin/grep
    key_id=${lib.escapeShellArg cfg.s3AccessKeyId}
    secret="$($grep -E '^NEXTCLOUD_S3_SECRET_KEY=' ${cfg.garageCredentialsFilePath} \
      | ${pkgs.coreutils}/bin/head -n1 | ${pkgs.coreutils}/bin/cut -d= -f2-)"

    # Wait for the local Garage RPC to answer.
    for _ in $(${pkgs.coreutils}/bin/seq 1 60); do
      "$garage" status >/dev/null 2>&1 && break
      sleep 1
    done

    # Single-node layout: assign this node a role and apply version 1, but only
    # while the applied layout is still version 0 (i.e. nothing assigned yet).
    if "$garage" layout show 2>/dev/null | $grep -qE 'layout version:[[:space:]]*0'; then
      node_id="$("$garage" node id -q 2>/dev/null | ${pkgs.coreutils}/bin/cut -d@ -f1)"
      "$garage" layout assign -z dc1 -c 100G "$node_id"
      "$garage" layout apply --version 1
    fi

    # Deterministic access key.
    if ! "$garage" key info "$key_id" >/dev/null 2>&1; then
      "$garage" key import --yes -n nextcloud "$key_id" "$secret"
    fi

    # Bucket and grant (both idempotent).
    "$garage" bucket create nextcloud >/dev/null 2>&1 || true
    "$garage" bucket allow --read --write --owner nextcloud --key "$key_id"
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
    garageCredentialsFilePath = mkOption {
      type = types.path;
      default = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_garage_credentials";
      description = ''
        Path to the delivered Vault file for the Nextcloud object store. It is
        an env-style file with three lines:
        NEXTCLOUD_S3_SECRET_KEY=<64 hex>, GARAGE_RPC_SECRET=<64 hex>,
        GARAGE_ADMIN_TOKEN=<token>.
      '';
    };

    s3AccessKeyId = mkOption {
      type = types.str;
      default = "GK00000000000000000000000000";
      description = ''
        S3 access-key ID Nextcloud presents to Garage. Not secret; set it per
        host. Must be a valid Garage key ID (GK followed by 24 hex characters)
        and must match the NEXTCLOUD_S3_SECRET_KEY in garageCredentialsFilePath.
      '';
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

  config = mkIf cfg.enable {
    roles.postgres.default.enable = mkForce false;
    roles.postgres.main.enable = mkForce false;
    # services.postgresql.enable = true;
    # add user nginx to nextcloud group
    users.users.nginx.extraGroups = [
      "nextcloud"
      sslCertGroupName
    ];
    # users.users.nextcloud.extraGroups = [ sslCertGroupName ];
    # users.groups.nextcloudutils.members = [ "nextcloud" "nginx" ];
    users.users.nextcloud = {
      isSystemUser = true;
      group = "nextcloud";
      extraGroups = [ sslCertGroupName ];
      home = cfg.customDir;
    };
    programs.zsh.shellAliases = {
      # Safe maintenance aliases that use the interactive maintenance script
      show-psql-conf = "nextcloud-maintenance --show-psql-conf";
      nextcloud-maintenance = "nextcloud-maintenance";
      # Interactive reset commands with confirmation prompts
      reset-psql-safe = "nextcloud-maintenance --reset-psql";
      reset-garage-safe = "nextcloud-maintenance --reset-garage";
      reset-nextcloud-all = "nextcloud-maintenance --reset-all";
    };

    networking.hosts = {
      "127.0.0.1" = [
        "cloud.endo-reg.net"
        "collabora.endo-reg.net"
      ];
      "::1" = [
        "cloud.endo-reg.net"
        "collabora.endo-reg.net"
      ];
    };

    environment.systemPackages = [
      cfg.package
      pkgs.clamav
      nextcloudMaintenanceScript
    ];
    networking.firewall.allowedTCPPorts = [
      80
      443
      3002
    ];

    services = {
      garage = {
        enable = true;
        package = pkgs.garage_1;
        environmentFile = garageEnvFile;
        settings = {
          metadata_dir = "/var/lib/garage/meta";
          data_dir = "/var/lib/garage/data";
          db_engine = "lmdb";
          replication_factor = 1;
          rpc_bind_addr = "127.0.0.1:3901";
          rpc_public_addr = "127.0.0.1:3901";
          s3_api = {
            s3_region = garageRegion;
            api_bind_addr = "127.0.0.1:${toString garageS3Port}";
            root_domain = ".s3.garage.internal";
          };
          admin.api_bind_addr = "127.0.0.1:3903";
        };
      };

      nextcloud-whiteboard-server = {
        enable = true;
        settings.NEXTCLOUD_URL = "http://cloud.endo-reg.net";
        secrets = [
          # TODO (nextcloud-host owner): move whiteboard JWT provisioning into
          # managed-secrets and document the matching Nextcloud app settings.
          # JWT_SECRET_KEY=SUPER_SECRET_KEY_VALUE
          # configure app via terminal or console:
          # nextcloud-occ config:app:set whiteboard collabBackendUrl --value="http://localhost:3002"
          # nextcloud-occ config:app:set whiteboard jwt_secret_key --value="test123"
          "/etc/nextcloud-jwt"
        ];
      };

      nextcloud = {
        enable = true;
        inherit (cfg) package;

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
            # garage-bootstrap.service guarantees the bucket exists and is
            # granted before nextcloud-setup runs.
            verify_bucket_exists = false;
            key = cfg.s3AccessKeyId;
            secretFile = s3SecretFile;
            hostname = "127.0.0.1";
            useSsl = false;
            port = garageS3Port;
            usePathStyle = true;
            region = garageRegion;
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
          trusted_domains = [
            "localhost"
            conf.domain
          ];

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
          mail_smtpport = 465;
          mail_smtpauth = true;
          mail_smtpauthtype = "LOGIN";
          # TODO (nextcloud-host owner): add a mail-domain option and migrate
          # inventory before removing this deployment-specific default.
          mail_domain = "endo-reg.net";

          oidc_login_provider_url = "https://keycloak.endo-reg.net/realms/master";
          oidc_login_end_session_redirect = true;
          oidc_login_logout_url = "https://cloud.endo-reg.net";
          oidc_login_auto_redirect = false;
          oidc_login_redir_fallback = true;
          oidc_login_button_text = "Login with Keycloak";
          oidc_login_hide_password_form = false; # Hide the change pwd form
          oidc_login_attributes = {
            id = "preferred_username";
            mail = "email";
            groups = "roles";
            login_filter = "realm_access_roles";
          };
          oidc_login_use_id_token = false; # Use ID Token instead of UserInfo
          oidc_login_disable_registration = true; # Disable registration
          oidc_create_groups = true; # Create groups

        };

        # Secret options which will be appended to Nextcloud’s config.php file (written as JSON, in the same form as
        # the services.nextcloud.settings option), for example
        # {"redis":{"password":"secret"}}.
        # default is null
        # TODO (nextcloud-host owner): expose this path and provision it through
        # managed-secrets before enabling this role on another host.
        secretFile = "/etc/nextcloud-secrets.json";

        # ###### Hosting ######
        https = true; # default = false;
        hostName = conf.domain; # "localhost"
        nginx = {
          # recommendedHttpHeaders = true; # default = true
          hstsMaxAge = 15552000; # default = 15552000;
        };

        # ###### Database ########
        database.createLocally = true;

        # Other relevant options
        inherit (cfg) maxUploadSize; # default = "2G"; (nextcloud default is 512M)
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

          # TODO (nextcloud-host owner): verify the CA file is used by an
          # outbound TLS integration, then retain it with a test or remove it.
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

          # TODO (nextcloud-host owner): split notify-push credentials only if
          # migration to a remote PostgreSQL instance requires another identity.
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

      nginx = {
        enable = true;
        recommendedProxySettings = true;
        recommendedTlsSettings = true;

        virtualHosts."collabora.endo-reg.net" = {
          locations."/" = {
            proxyPass = "http://[::1]:${toString config.services.collabora-online.port}";
            proxyWebsockets = true; # collabora uses websockets
          };
        };
      };

      # Add a post-install hook to fix permissions
      # systemd.services.nextcloud-setup = {
      #   serviceConfig = {
      #     ExecStartPost = "${pkgs.bash}/bin/bash -c 'chown -R nextcloud:nextcloud /var/lib/nextcloud/config && chmod -R 770 /var/lib/nextcloud/config'";
      #   };
      # };

      clamav = {
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
        scanner = {
          enable = true;
          scanDirectories = [
            "/home"
            "/var/lib"
            "/tmp"
            "/etc"
            "/var/tmp"
          ];
          interval = "*-*-* 04:00:00";
        };
      };
    };

    systemd = {
      tmpfiles.rules = map (dir: "d ${dir} 0750 nextcloud nextcloud - -") [
        "${cfg.customDir}"
        "${cfg.customDir}/config"
        "${cfg.customDir}/data"
        "${cfg.customDir}/store-apps"
      ];

      services = {
        # Split the delivered Vault file into the Garage env file and the
        # Nextcloud S3 secret. Must finish before Garage and Nextcloud start.
        nextcloud-prepare-files = {
          description = "Prepare credentials for Nextcloud and Garage";
          wantedBy = [ "multi-user.target" ];
          before = [
            "nextcloud-setup.service"
            "garage.service"
          ];
          after = [ "managed-secrets-setup.service" ];
          requires = [ "managed-secrets-setup.service" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            ExecStart = "${nextcloudPrepareScript}";
          };
        };

        garage = {
          after = [ "nextcloud-prepare-files.service" ];
          requires = [ "nextcloud-prepare-files.service" ];
        };

        # Apply the single-node layout, import the S3 key, and create the
        # bucket once Garage is up and before Nextcloud configures itself.
        garage-bootstrap = {
          description = "Bootstrap the Nextcloud Garage bucket and key";
          wantedBy = [ "multi-user.target" ];
          after = [
            "garage.service"
            "nextcloud-prepare-files.service"
          ];
          requires = [
            "garage.service"
            "nextcloud-prepare-files.service"
          ];
          before = [ "nextcloud-setup.service" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            ExecStart = "${garageBootstrapScript}";
          };
        };

        nextcloud-setup = {
          after = [ "garage-bootstrap.service" ];
          requires = [ "garage-bootstrap.service" ];
        };
      };
    };

  };
}
