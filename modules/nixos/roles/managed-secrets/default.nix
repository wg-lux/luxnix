{ lib
, config
, pkgs
, ...
}:
with lib; let
  cfg = config.roles.managed-secrets;
  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  # Generator for human-readable two-word passwords
  twoWordPasswordGenerator = pkgs.writeShellScript "generate-two-word-password" ''
    ${pkgs.python3}/bin/python3 - <<'PY'
import secrets

ADJECTIVES = """
acidic agile amber arctic astral aurora brisk bronze cobalt cosmic covert crimson crystal daring diamond dusty ember evergreen feral fluent fractal gentle glacial golden granite hazel hidden humble indigo ionic ivory jagged lucid lunar lush mellow molten mystic nimble obsidian oceanic opaline ozone pearly primrose quartz quick radiant rugged sable scarlet serene shadow silver spruce stellar subtle sunlit swift tactile tempered thunder titan tranquil verdant vibrant violet weathered zealous
""".split()

NOUNS = """
alchemy anchor archway aurora badger beacon birch canyon catalyst cedar cipher comet coral cosmos coyote cradle cygnus ember forge glacier halo harbor horizon iceberg isthmus ivy lantern lichen lotus lynx marble meander mesa meteor monsoon nebula obsidian orchard orion osprey oyster pebble phoenix prairie quasar ravine reef ripple rivulet saddle savanna sentinel skylark spear spire springtide summit tempest thicket thunder tide trail tundra valley vellum vortex willow windfall zephyr zodiac
""".split()

if not ADJECTIVES or not NOUNS:
    raise SystemExit("word lists must not be empty")

word_one = secrets.choice(ADJECTIVES)
word_two = secrets.choice(NOUNS)

print(f"{word_one}-{word_two}")
PY
  '';

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

    # Keycloak database password
    keycloak_host_password = {
      path = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
      generator = "${pkgs.openssl}/bin/openssl rand -base64 32";
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Keycloak database user password";
    };

    client_user_password = {
      path = "/etc/secrets/vault/SCRT_client_user_password";
      generator = twoWordPasswordGenerator;
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Client user 2-word password";
    };

    client_user_password_hash = {
      path = "/etc/secrets/vault/SCRT_client_user_password_hash";
      generator = ''
        PASSWORD_FILE="/etc/secrets/vault/SCRT_client_user_password"

        if [ ! -f "$PASSWORD_FILE" ]; then
          ${twoWordPasswordGenerator} > "$PASSWORD_FILE"
          chown root:${sensitiveServiceGroupName} "$PASSWORD_FILE"
          chmod 640 "$PASSWORD_FILE"
        fi

        PASSWORD="$(tr -d '\n' < "$PASSWORD_FILE")"
        ${pkgs.openssl}/bin/openssl passwd -6 "$PASSWORD" > "$TARGET_FILE"
      '';
      owner = "root";
      group = sensitiveServiceGroupName;
      permissions = "640";
      description = "Client user password hash";
      customScript = true;
    };
  };

  activeSecretFiles = lib.filterAttrs (name: _: cfg.secrets.${name}.enable) secretFiles;
  secretNames = lib.attrNames activeSecretFiles;
  secretNamesString = lib.concatStringsSep " " secretNames;
  secretPathAssignments = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: secret: ''SECRET_PATHS["${name}"]="${secret.path}"'') activeSecretFiles);
  secretDescriptionAssignments = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: secret: ''SECRET_DESCRIPTIONS["${name}"]="${secret.description}"'') activeSecretFiles);
  secretOwnerAssignments = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: secret: ''SECRET_OWNERS["${name}"]="${secret.owner}"'') activeSecretFiles);
  secretGroupAssignments = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: secret: ''SECRET_GROUPS["${name}"]="${secret.group}"'') activeSecretFiles);
  secretPermissionAssignments = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: secret: ''SECRET_PERMS["${name}"]="${secret.permissions}"'') activeSecretFiles);
  specificLinkedSecrets = {
    client_user_password = [ "client_user_password_hash" ];
    client_user_password_hash = [ "client_user_password" ];
  };
  secretLinkedAssignments = lib.concatStringsSep "\n" (
    map (name:
      let
  rawExtras = if specificLinkedSecrets ? ${name} then specificLinkedSecrets.${name} else [];
  extrasList = rawExtras;
        extras = lib.concatStringsSep " " extrasList;
      in ''SECRET_LINKED["${name}"]="${extras}"'')
      secretNames
  );

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
    '') activeSecretFiles)}
    
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
        set -euo pipefail

        SECRET_NAMES=(${secretNamesString})

        declare -A SECRET_PATHS
        ${secretPathAssignments}

        declare -A SECRET_DESCRIPTIONS
        ${secretDescriptionAssignments}

        declare -A SECRET_OWNERS
        ${secretOwnerAssignments}

        declare -A SECRET_GROUPS
        ${secretGroupAssignments}

        declare -A SECRET_PERMS
        ${secretPermissionAssignments}

        declare -A SECRET_LINKED
        ${secretLinkedAssignments}

        show_help() {
          cat <<'EOF'
LuxNix Secrets Management Tool
Usage: luxnix-secrets [COMMAND] [OPTIONS]

Commands:
  generate            Generate missing secrets (or a specific secret with --secret)
  regenerate          Force regenerate all secrets (or rotate a specific secret with --secret)
  rotate              Rotate a specific secret and its linked files
  list                List all managed secrets
  check               Check status of managed secrets
  show                Display the contents of a secret
  help                Show this help message

Options:
  --secret NAME       Target a specific secret
EOF
        }

        ensure_secret_name() {
          local name="$1"
          if [[ -z "$name" ]]; then
            echo "Error: --secret NAME is required for this operation." >&2
            exit 1
          fi
          if [[ -z "''${SECRET_PATHS[$name]+x}" ]]; then
            echo "Error: Unknown secret '$name'." >&2
            exit 1
          fi
        }

        list_secrets() {
          if [[ ''${#SECRET_NAMES[@]} -eq 0 ]]; then
            echo "No managed secrets are currently enabled."
            return
          fi

          echo "Managed Secrets:"
          echo "================"
          for name in "''${SECRET_NAMES[@]}"; do
            printf '• %s: %s\n' "$name" "''${SECRET_DESCRIPTIONS[$name]}"
            printf '  Path: %s\n' "''${SECRET_PATHS[$name]}"
            printf '  Owner: %s:%s (%s)\n\n' "''${SECRET_OWNERS[$name]}" "''${SECRET_GROUPS[$name]}" "''${SECRET_PERMS[$name]}"
          done
        }

        check_secrets() {
          local targets=("$@")
          if [[ ''${#targets[@]} -eq 0 ]]; then
            targets=("''${SECRET_NAMES[@]}")
          fi

          if [[ ''${#targets[@]} -eq 0 ]]; then
            echo "No managed secrets are currently enabled."
            return
          fi

          echo "Secret Status Check:"
          echo "===================="
          for name in "''${targets[@]}"; do
            ensure_secret_name "$name"
            local path="''${SECRET_PATHS[$name]}"
            if [[ -f "$path" ]]; then
              printf '✓ %s: EXISTS\n' "$name"
              ls -la "$path" | awk '{print "  " $1, $3, $4, $9}'
            else
              printf '✗ %s: MISSING\n' "$name"
            fi
          done
        }

        generate_all() {
          echo "Generating missing secrets..."
          sudo systemctl start managed-secrets-setup.service
        }

        show_secret() {
          local name="$1"
          local quiet="false"
          if [[ $# -ge 2 ]]; then
            quiet="$2"
          fi
          ensure_secret_name "$name"
          local path="''${SECRET_PATHS[$name]}"
          if [[ ! -f "$path" ]]; then
            echo "Secret '$name' does not exist at $path" >&2
            exit 1
          fi
          if [[ "$quiet" != "true" ]]; then
            printf '--- %s (%s) ---%s' "$name" "$path" "\n"
          fi
          sudo cat "$path"
          if [[ "$quiet" != "true" ]]; then
            printf '\n'
          fi
        }

        generate_command() {
          local name="$1"
          if [[ -z "$name" ]]; then
            generate_all
            return
          fi

          ensure_secret_name "$name"
          local path="''${SECRET_PATHS[$name]}"
          if [[ -f "$path" ]]; then
            echo "Secret '$name' already exists at $path"
            return
          fi

          generate_all

          if [[ -f "$path" ]]; then
            echo "Generated secret '$name'."
            show_secret "$name"
          else
            echo "Failed to generate secret '$name'." >&2
            exit 1
          fi
        }

        rotate_secret() {
          local name="$1"
          ensure_secret_name "$name"

          local to_rotate=("$name")
          if [[ -n "''${SECRET_LINKED[$name]}" ]]; then
            for linked in ''${SECRET_LINKED[$name]}; do
              if [[ -n "''${SECRET_PATHS[$linked]+x}" ]]; then
                to_rotate+=("$linked")
              fi
            done
          fi

          echo "The following secrets will be rotated:"
          for item in "''${to_rotate[@]}"; do
            printf '  - %s (%s)\n' "$item" "''${SECRET_PATHS[$item]}"
          done

          read -p "Type 'yes' to continue: " confirm
          if [[ "$confirm" != "yes" ]]; then
            echo "Operation cancelled."
            return
          fi

          for item in "''${to_rotate[@]}"; do
            sudo rm -f "''${SECRET_PATHS[$item]}"
          done

          sudo systemctl start managed-secrets-setup.service
          echo "Rotation finished."

          for item in "''${to_rotate[@]}"; do
            if [[ -f "''${SECRET_PATHS[$item]}" ]]; then
              show_secret "$item"
            fi
          done
        }

        regenerate_all() {
          if [[ ''${#SECRET_NAMES[@]} -eq 0 ]]; then
            echo "No managed secrets are currently enabled."
            return
          fi

          echo "Force regenerating all secrets..."
          echo "This will overwrite existing secrets!"
          read -p "Type 'yes' to continue: " confirm
          if [[ "$confirm" != "yes" ]]; then
            echo "Operation cancelled."
            return
          fi

          for name in "''${SECRET_NAMES[@]}"; do
            sudo rm -f "''${SECRET_PATHS[$name]}"
          done

          sudo systemctl start managed-secrets-setup.service
          echo "All secrets regenerated."
        }

        COMMAND="help"
        if [[ $# -gt 0 ]]; then
          COMMAND="$1"
          shift
        fi

        TARGET_SECRET=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --secret)
              TARGET_SECRET="$2"
              shift 2
              ;;
            --help|-h)
              show_help
              exit 0
              ;;
            *)
              echo "Unknown option: $1" >&2
              show_help
              exit 1
              ;;
          esac
        done

        case "$COMMAND" in
          generate)
            generate_command "$TARGET_SECRET"
            ;;
          regenerate)
            if [[ -n "$TARGET_SECRET" ]]; then
              rotate_secret "$TARGET_SECRET"
            else
              regenerate_all
            fi
            ;;
          rotate)
            rotate_secret "$TARGET_SECRET"
            ;;
          list)
            list_secrets
            ;;
          check)
            if [[ -n "$TARGET_SECRET" ]]; then
              check_secrets "$TARGET_SECRET"
            else
              check_secrets
            fi
            ;;
          show)
            show_secret "$TARGET_SECRET"
            ;;
          help|--help|-h)
            show_help
            ;;
          *)
            echo "Unknown command: $COMMAND" >&2
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
