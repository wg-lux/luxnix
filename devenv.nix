{
  pkgs,
  lib,
  config,
  ...
}:
let
  pythonVersion = lib.removeSuffix "\n" (builtins.readFile ./.python-version);
  pythonPackageName = "python${builtins.replaceStrings [ "." ] [ "" ] pythonVersion}";
  python = pkgs.${pythonPackageName};
  uvPackage = pkgs.uv;

  baseEnv = {
    # --- Directories & Paths ---
    STORAGE_PERSISTING_HDD_ID = config.secretspec.secrets.STORAGE_PERSISTING_HDD_ID;
    HOME_DIR = config.secretspec.secrets.HOME_DIR;
    WORKING_DIR = config.secretspec.secrets.WORKING_DIR;
  };
  devenvUtils = import ./devenv/default.nix {
    inherit pkgs uvPackage;
  };
  devenvPackages = devenvUtils.packages;
in
{
  dotenv.enable = false;
  dotenv.disableHint = true;
  packages = devenvPackages;
  env = baseEnv // {
    LD_LIBRARY_PATH =
      lib.makeLibraryPath devenvPackages
      + ":/run/opengl-driver/lib:/run/opengl-driver-32/lib"
      + ":/usr/lib/wsl/lib"
      + ":/usr/lib/x86_64-linux-gnu"
      + ":/usr/lib";
  };

  languages.python = {
    enable = true;
    package = python;
    uv = {
      enable = true;
      package = uvPackage;
      sync.enable = true;
    };
  };

  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_22;
    npm.enable = true;
    npm.install.enable = true;
  };

  processes = devenvUtils.processes;
  tasks = devenvUtils.tasks;

  git-hooks.hooks = {
    ansible-lint.enable = true;
  };

  scripts = devenvUtils.scripts;

  enterShell = ''
    if command -v env-setup >/dev/null 2>&1; then
      env-setup
    fi

    # The Devenv sync task prepares this environment in a subprocess; activate
    # it in the caller's shell so Python tools resolve to the managed venv.
    source .devenv/state/venv/bin/activate

    if [ -f ".env.systemd" ]; then
      set -a
      source .env.systemd
      set +a
      echo "Loaded optional environment from .env.systemd."
    fi
  '';

  enterTest = "";
}
