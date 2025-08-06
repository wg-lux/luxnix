{ lib
, config
, pkgs
, ...
}:
with lib; let
  cfg = config.roles.managed-secrets;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  # Common secret files configuration
  secretFiles = {
    # PostgreSQL maintenance password
    maintenance_password = {
      path = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
      generator = "${pkgs.openssl}/bin/openssl rand -base64 32";
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "PostgreSQL maintenance user password";
    };

    # Django secret key for local instances
    django_secret_key = {
      path = "/etc/secrets/vault/django_secret_key";
      generator = "${pkgs.openssl}/bin/openssl rand -base64 50";
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Django SECRET_KEY for local API instances";
    };

    # Django secret key for central instances
    django_central_secret_key = {
      path = "/etc/secrets/vault/django_central_secret_key";
      generator = "${pkgs.openssl}/bin/openssl rand -base64 50";
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Django SECRET_KEY for central API instances";
    };

    # Nextcloud admin password
    nextcloud_admin_password = {
      path = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
      generator = "${pkgs.openssl}/bin/openssl rand -base64 32";
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Nextcloud admin password";
    };

    # MinIO credentials for Nextcloud
    nextcloud_minio_credentials = {
      path = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_minio_credentials";
      generator = ''
        MINIO_ROOT_USER="nextcloud"
        MINIO_ROOT_PASSWORD="$(${pkgs.openssl}/bin/openssl rand -base64 32)"
        echo "MINIO_ROOT_USER=$MINIO_ROOT_USER" > "$TARGET_FILE"
        echo "MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD" >> "$TARGET_FILE"
      '';
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "MinIO credentials for Nextcloud object storage";
      customScript = true;
    };
  };

  # Generate script for creating a secret file
  mkSecretScript = name: secretConfig: pkgs.writeShellScript "generate-${name}" ''
    set -euo pipefail
    
    SECRET_FILE="${secretConfig.path}"
    TARGET_FILE="$SECRET_FILE"
    
    echo "Checking secret: ${name} at $SECRET_FILE"
    
    if [ ! -f "$SECRET_FILE" ]; then
      echo "Generating ${secretConfig.description}..."
      mkdir -p "$(dirname "$SECRET_FILE")"
      
      ${if secretConfig.customScript or false then secretConfig.generator else ''
        ${secretConfig.generator} > "$SECRET_FILE"
      ''}
      
      # Set ownership and permissions
      chown ${secretConfig.owner}:${secretConfig.group} "$SECRET_FILE"
      chmod ${secretConfig.permissions} "$SECRET_FILE"
      
      echo "Generated ${secretConfig.description} at $SECRET_FILE"
    else
      echo "Secret already exists: ${secretConfig.description}"
      # Ensure correct permissions on existing files
      chown ${secretConfig.owner}:${secretConfig.group} "$SECRET_FILE"
      chmod ${secretConfig.permissions} "$SECRET_FILE"
    fi
  '';

  # Main secret generation script
  generateSecretsScript = pkgs.writeShellScript "generate-managed-secrets" ''
    set -euo pipefail
    
    echo "Starting managed secrets generation..."
    
    # Verify sensitive service group exists by checking /etc/group
    if ! grep -q "^${sensitiveServiceGroupName}:" /etc/group; then
      echo "ERROR: Group ${sensitiveServiceGroupName} does not exist"
      exit 1
    fi
    
    # Verify directories are accessible
    if [ ! -d "/etc/secrets" ] || [ ! -d "/etc/secrets/vault" ]; then
      echo "ERROR: Secret directories do not exist after creation"
      exit 1
    fi
    
    echo "Directory setup completed successfully"
    
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: config: ''
      ${mkSecretScript name config}
    '') (lib.filterAttrs (name: config: cfg.secrets.${name}.enable) secretFiles))}
    
    echo "Managed secrets generation completed successfully"
  '';

in
{
  options.roles.managed-secrets = {
    enable = mkOption {
      type = types.bool;
      default = true;
      description = "Enable automatic management of common secret files";
    };

    secrets = mkOption {
      type = types.attrsOf (types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Enable generation of this secret";
          };
          
          forceRegenerate = mkOption {
            type = types.bool;
            default = false;
            description = "Force regeneration of this secret even if it exists";
          };
        };
      });
      default = lib.mapAttrs (name: config: { enable = true; forceRegenerate = false; }) secretFiles;
      description = "Configuration for individual secrets";
    };

    # Additional secrets can be defined by users
    customSecrets = mkOption {
      type = types.attrsOf (types.submodule {
        options = {
          path = mkOption {
            type = types.str;
            description = "Full path to the secret file";
          };
          
          generator = mkOption {
            type = types.str;
            description = "Command to generate the secret content";
            example = "${pkgs.openssl}/bin/openssl rand -base64 32";
          };
          
          owner = mkOption {
            type = types.str;
            default = "root";
            description = "File owner";
          };
          
          group = mkOption {
            type = types.str;
            default = sensitiveServiceGroupName;
            description = "File group";
          };
          
          permissions = mkOption {
            type = types.str;
            default = "640";
            description = "File permissions (octal)";
          };
          
          description = mkOption {
            type = types.str;
            description = "Description of the secret";
          };
          
          customScript = mkOption {
            type = types.bool;
            default = false;
            description = "Whether the generator is a custom script (uses TARGET_FILE variable)";
          };
        };
      });
      default = {};
      description = "Additional custom secrets to manage";
    };

    runOnBoot = mkOption {
      type = types.bool;
      default = true;
      description = "Whether to run secret generation on system boot";
    };

    runBefore = mkOption {
      type = types.listOf types.str;
      default = [ "postgresql.service" "nextcloud-setup.service" "endo-api-boot.service" ];
      description = "Services that should wait for secret generation";
    };
  };

  config = mkIf cfg.enable {
    # Ensure the sensitive service group exists
    users.groups.${sensitiveServiceGroupName} = {};

    # Create systemd service for secret management
    systemd.services.managed-secrets-setup = {
      description = "Generate and manage system secrets";
      wantedBy = [ "multi-user.target" ];
      before = cfg.runBefore;
      after = [ "local-fs.target" "systemd-tmpfiles-setup.service" ];
      wants = [ "local-fs.target" ];
      requires = [ "systemd-tmpfiles-setup.service" ];
      
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = generateSecretsScript;
      };
    };

    # Create tmpfiles rules to ensure directory structure
    systemd.tmpfiles.rules = [
      # Create base secrets directory with proper permissions
      "d /etc/secrets 0750 root ${sensitiveServiceGroupName} - -"
      # Create vault subdirectory with proper permissions  
      "d /etc/secrets/vault 0750 root ${sensitiveServiceGroupName} - -"
    ];

    # Add a maintenance command for manual secret management
    environment.systemPackages = [
      (pkgs.writeScriptBin "luxnix-secrets" ''
        #!${pkgs.bash}/bin/bash
        set -e

        show_help() {
          echo "LuxNix Secrets Management Tool"
          echo "Usage: $0 [COMMAND] [OPTIONS]"
          echo ""
          echo "Commands:"
          echo "  generate    Generate all missing secrets"
          echo "  regenerate  Force regenerate all secrets"
          echo "  list        List all managed secrets"
          echo "  check       Check status of all secrets"
          echo "  help        Show this help message"
          echo ""
          echo "Options:"
          echo "  --secret NAME   Target specific secret only"
        }

        list_secrets() {
          echo "Managed Secrets:"
          echo "=================="
          ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: config: ''
            echo "• ${name}: ${config.description}"
            echo "  Path: ${config.path}"
            echo "  Owner: ${config.owner}:${config.group} (${config.permissions})"
            echo ""
          '') secretFiles)}
        }

        check_secrets() {
          echo "Secret Status Check:"
          echo "==================="
          ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: config: ''
            if [ -f "${config.path}" ]; then
              echo "✓ ${name}: EXISTS"
              ls -la "${config.path}" | awk '{print "  " $1, $3, $4, $9}'
            else
              echo "✗ ${name}: MISSING"
            fi
          '') secretFiles)}
        }

        case "''${1:-help}" in
          generate)
            echo "Generating missing secrets..."
            sudo systemctl start managed-secrets-setup.service
            ;;
          regenerate)
            echo "Force regenerating all secrets..."
            echo "This will overwrite existing secrets!"
            read -p "Are you sure? (type 'yes' to continue): " confirm
            if [ "$confirm" = "yes" ]; then
              ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: config: ''
                sudo rm -f "${config.path}"
              '') secretFiles)}
              sudo systemctl start managed-secrets-setup.service
            else
              echo "Operation cancelled."
            fi
            ;;
          list)
            list_secrets
            ;;
          check)
            check_secrets
            ;;
          help|--help|-h)
            show_help
            ;;
          *)
            echo "Unknown command: $1"
            show_help
            exit 1
            ;;
        esac
      '')
    ];

    # Add shell aliases for convenience
    programs.zsh.shellAliases = {
      secrets-check = "luxnix-secrets check";
      secrets-generate = "luxnix-secrets generate";
      secrets-list = "luxnix-secrets list";
    };
  };
}
