{
  pkgs,
  lib,
  config,
  inputs,
  baseBuildInputs,
  ...
}:
let
  appName = "lx_annotate";
  DEPLOYMENT_MODE = "prod";
  python = pkgs.python312;
  nodejs = pkgs.nodejs_22;
  uvPackage = pkgs.uv;
  languages.python.enable = true;
  languages.python.uv.enable = true;
  languages.javascript.enable = true;
  languages.javascript.package = nodejs;

  devTasks = import ./devenv/devTasks/default.nix {
    inherit config pkgs lib;
    env = baseEnv;
  };
  isDev = if config.secretspec.secrets.DJANGO_ENV == "development" then true else false;

  processes = import ./devenv/processes.nix { inherit pkgs; };

  baseEnv = {
    # --- Directories & Paths ---
    STORAGE_PERSISTING_HDD_ID = config.secretspec.secrets.STORAGE_PERSISTING_HDD_ID;
    HOME_DIR = config.secretspec.secrets.HOME_DIR;
    WORKING_DIR = config.secretspec.secrets.WORKING_DIR;

  };
  devenv_utils = import ./devenv/default.nix {
    pkgs = pkgs;
    lib = lib;
    uvPackage = uvPackage;
    isDev = isDev;
    env = baseEnv;
  };
  commonShellHook = ''
    export PATH="$PATH:$(yarn global bin)"
  '';

  runtimePackages = with pkgs; [
    stdenv.cc.cc
    uvPackage
    libglvnd # Add libglvnd for libGL.so.1
    glib
    zlib
    git
    secretspec
    libxcb
    nixd
    nixfmt
  ];
  _module.args.buildInputs = baseBuildInputs;
  SYNC_CMD = "uv sync";
  nixpkgs.config.allowUnfree = true;

in
{

  dotenv.enable = false;
  dotenv.disableHint = true;
  packages = devenv_utils.buildInputs ++ runtimePackages;
  env = baseEnv // {
    LD_LIBRARY_PATH =
      lib.makeLibraryPath (runtimePackages)
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

  processes = devenv_utils.processes;
  containers = devenv_utils.containers;

  git-hooks.hooks = {
    ansible-lint.enable = true;
  };

  scripts = devenv_utils.scripts;

  enterShell = ''
    if command -v env-setup >/dev/null 2>&1; then
      env-setup
    fi
    # Ensure dependencies are synced using uv
    # Check if venv exists. If not, run sync verbosely. If it exists, sync quietly.
    SYNC_STAMP=".devenv/state/.uv-sync.stamp"
    LOCK_HASH="$(sha256sum uv.lock pyproject.toml 2>/dev/null | sha256sum | cut -d' ' -f1)"

    if [ ! -f "$SYNC_STAMP" ] || [ "$(cat "$SYNC_STAMP")" != "$LOCK_HASH" ]; then
      echo "uv deps changed -> syncing..."
      $SYNC_CMD || echo "Warning: uv sync failed."
      echo "$LOCK_HASH" > "$SYNC_STAMP"
    else
      echo "uv deps unchanged -> skip sync"
    fi


    echo "Exporting environment variables from .env.systemd file..."
    echo "Note: In dev mode you can set defaults in secretspec.toml or source them from local env by enabling the env source in your config.yaml for secretspec."
    if [ -f ".env.systemd" ]; then
      set -a
      source .env.systemd
      set +a
      echo ".env.systemd file loaded successfully."
    else
      echo "Note: .env.systemd not found. Defaults apply."
    fi
    # Activate Python virtual environment managed by uv inside of devenv
    ACTIVATED=false
    if [ -f ".devenv/state/venv/bin/activate" ]; then
      source .devenv/state/venv/bin/activate
      ACTIVATED=true
      echo "Virtual environment activated."
    else
      echo "Warning: uv virtual environment activation script not found. Run 'devenv task run env:clean' and re-enter shell."
    fi
  '';

  enterTest = "";
}
