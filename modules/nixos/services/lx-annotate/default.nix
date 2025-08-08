{ config, lib, pkgs, ... }:
with lib;
let
  cfg = config.services.luxnix.lxAnnotate;

  # Derive admin user & home (dynamic/scalable)
  adminName = config.user.admin.name or "admin";
  serviceUserName = adminName;
  serviceUserHome = "/home/${serviceUserName}";

  scriptName   = "runLxAnnotate";
  gitURL       = cfg.repository.url or "https://github.com/wg-lux/lx-annotate.git";
  repoDirName  = "lx-annotate";
  branchName   = cfg.repository.branch or "main";

  # Clone HERE, as requested
  repoDir   = "${serviceUserHome}/dev/${repoDirName}";
  configDir = "${serviceUserHome}/config";

  # Reuse the SAME DB/user/secret as endo-api
  dbName       = cfg.database.name or "endoregDbLocal";
  dbUser       = cfg.database.user or "endoregDbLocal";
  passwordFile = cfg.database.passwordFile or "/etc/secrets/vault/SCRT_local_password_maintenance_password";
  dbHost       = cfg.database.host or "localhost";
  dbPort       = toString (cfg.database.port or 5432);

  # Allow selecting a secret key file for lx-annotate (defaults to its own),
  # you can override to the endo one if you like.
  djangoSecretKeyFile = cfg.api.djangoSecretKeyFile or "/etc/secrets/vault/lx_annotate_django_secret_key";

  # Django local_settings.py (mirrors the endo approach)
  djangoConfigFile = pkgs.writeText "lx-annotate-local-settings.py" ''
    # Auto-generated Django configuration for lx-annotate (local)
    import os

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': '${dbName}',
            'USER': '${dbUser}',
            'PASSWORD': open('${passwordFile}').read().strip(),
            'HOST': '${dbHost}',
            'PORT': '${dbPort}',
            'OPTIONS': { 'sslmode': 'prefer' },
        }
    }

    # Secret key file (override via cfg.api.djangoSecretKeyFile)
    SECRET_KEY = open('${djangoSecretKeyFile}').read().strip()

    DEBUG = False
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
  '';

  runLxAnnotateScript = pkgs.writeShellScriptBin scriptName ''
    set -euo pipefail

    echo "Starting lx-annotate service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"
    echo "Target Directory: ${repoDir}"

    # Clone or update repository
    if [ ! -d ${repoDir} ]; then
      echo "Cloning repository..."
      git clone ${gitURL} ${repoDir}
      cd ${repoDir}
    else
      cd ${repoDir}
      ${if (cfg.repository.updateOnBoot or true) then ''
        echo "Updating repository..."
        git fetch origin || { echo "ERROR: Failed to fetch from origin"; exit 1; }
      '' else ''
        echo "Repository update disabled, using existing code"
      ''}
    fi

    # Checkout specified branch with proper remote tracking (same pattern as endo)
    echo "Checking out branch: ${branchName}"
    if git show-ref --verify --quiet refs/heads/${branchName}; then
      git checkout ${branchName} || { echo "ERROR: Failed to checkout local branch ${branchName}"; exit 1; }
    elif git show-ref --verify --quiet refs/remotes/origin/${branchName}; then
      git checkout -b ${branchName} origin/${branchName} || { echo "ERROR: Failed to create tracking branch for ${branchName}"; exit 1; }
    else
      echo "ERROR: Branch ${branchName} does not exist locally or on remote"
      git branch -r || echo "Could not list remote branches"
      exit 1
    fi

    ${if (cfg.repository.updateOnBoot or true) then ''
    # Update the current branch (same recovery as endo)
    echo "Updating branch ${branchName}..."
    git pull origin ${branchName} || {
      echo "WARNING: Failed to pull, trying hard reset to origin/${branchName}"
      git reset --hard origin/${branchName} || {
        echo "ERROR: Failed to update branch ${branchName}"
        exit 1
      }
    }
    '' else ""}

    # Ensure repo conf directory exists (same as endo)
    mkdir -p ${repoDir}/conf

    # Copy DB password from the vault to repo conf/db_pwd (same as endo)
    echo "Copying DB password from vault to ${repoDir}/conf/db_pwd"
    if [ -r "${passwordFile}" ]; then
      cp "${passwordFile}" ${repoDir}/conf/db_pwd
      chmod 600 ${repoDir}/conf/db_pwd
    else
      echo "ERROR: Cannot read ${passwordFile}. Check group membership and permissions."
      exit 1
    fi

    # Ensure service config directory exists (same layout as endo)
    echo "Ensuring config dir exists: ${configDir}"
    mkdir -p "${configDir}"

    # Write local_settings.py outside the repo and symlink it in (same as endo)
    echo "Writing Django local_settings.py and symlinking into repo"
    # Remove existing to avoid readonly/symlink weirdness
    if [ -f "${configDir}/local_settings.py" ]; then
      rm -f "${configDir}/local_settings.py" || true
    fi
    cp ${djangoConfigFile} "${configDir}/local_settings.py"
    ln -sf "${configDir}/local_settings.py" ${repoDir}/local_settings.py

    # Run repository config initialization (same as endo), to create conf/db.yaml
    echo "Running repository config initialization..."
    if command -v devenv >/dev/null 2>&1; then
      echo "Using devenv shell env-init-conf..."
      devenv shell env-init-conf || {
        echo "WARNING: env-init-conf failed, falling back to scripts/make_conf.py if present"
        if [ -f "scripts/make_conf.py" ]; then
          python scripts/make_conf.py || echo "WARNING: make_conf.py execution failed"
        fi
      }
    else
      echo "devenv not available, trying scripts/make_conf.py..."
      if [ -f "scripts/make_conf.py" ]; then
        python scripts/make_conf.py || echo "WARNING: make_conf.py execution failed"
      else
        echo "WARNING: scripts/make_conf.py not found"
      fi
    fi

    # Verify db.yaml like endo does
    if [ -f "${repoDir}/conf/db.yaml" ]; then
      echo "✓ Django configuration file created: ${repoDir}/conf/db.yaml"
    else
      echo "WARNING: ${repoDir}/conf/db.yaml was not created"
      ls -la "${repoDir}/conf/" 2>/dev/null || echo "Cannot access conf directory"
    fi

    echo "Starting application (devenv shell -- run-prod-server)..."
    exec devenv shell -- run-prod-server
  '';
in
{
  options.services.luxnix.lxAnnotate = {
    enable = mkEnableOption "Enable lx-annotate Service";

    api = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          djangoSecretKeyFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/lx_annotate_django_secret_key";
            description = "Path to Django SECRET_KEY file for lx-annotate.";
          };
        };
      });
      default = null;
      description = "API configuration for lx-annotate.";
    };

    database = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          host = mkOption { type = types.str;  default = "localhost"; };
          port = mkOption { type = types.port; default = 5432; };
          name = mkOption { type = types.str;  default = "endoregDbLocal"; };
          user = mkOption { type = types.str;  default = "endoregDbLocal"; };
          passwordFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
          };
        };
      });
      default = null;
      description = "Database configuration options (defaults match endo-api).";
    };

    repository = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          url = mkOption { type = types.str; default = "https://github.com/wg-lux/lx-annotate.git"; };
          branch = mkOption { type = types.str; default = "main"; };
          updateOnBoot = mkOption { type = types.bool; default = true; };
        };
      });
      default = null;
      description = "Repository configuration options.";
    };
  };

  config = mkIf cfg.enable {

    # Make sure the directories we write to actually exist and are owned by the service user
    systemd.tmpfiles.rules = [
      # /home/<admin>/dev for repo clone
      "d ${serviceUserHome}/dev 0755 ${serviceUserName} ${serviceUserName} - -"
      # /home/<admin>/config for local_settings.py
      "d ${configDir} 0755 ${serviceUserName} ${serviceUserName} - -"
    ];

    systemd.services."lx-annotate" = {
      description = "Clone or pull lx-annotate and run prod server";
      wantedBy = [ "multi-user.target" ];

      # We share endo's DB user/secret, so wait for that password setup and secrets
      after = [
        "postgres-endoreg-setup.service"
        "managed-secrets-setup.service"
        "systemd-tmpfiles-setup.service"
      ];
      requires = [
        "postgres-endoreg-setup.service"
        "managed-secrets-setup.service"
        "systemd-tmpfiles-setup.service"
      ];

      serviceConfig = {
        Type = "exec";
        User = serviceUserName;
        Environment = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin";
        ExecStart = "${runLxAnnotateScript}/bin/${scriptName}";
        Restart = "on-failure";
        RestartSec = "10s";
        MemoryMax = "2G";
        CPUQuota = "200%";
      };
    };
  };
}
