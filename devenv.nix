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
    inherit (config.secretspec.secrets)
      STORAGE_PERSISTING_HDD_ID
      HOME_DIR
      WORKING_DIR
      ;
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
  # Do not set a shell-wide LD_LIBRARY_PATH here. Nix executables carry the
  # exact runtime paths of the libraries they were built against. Prepending
  # the development package closure can make host tools load a newer libmount
  # or libselinux alongside the host's older glibc, causing ABI errors before
  # the program reaches main(). Tools that genuinely need an additional
  # runtime library should be wrapped individually instead.
  env = baseEnv;

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
    # npm.install.enable runs `npm clean-install` on every shell entry and then
    # writes node_modules/package-lock.json.checksum. Our package-lock.json has
    # zero dependencies, so `npm ci` succeeds without creating node_modules and
    # the checksum write fails with "No such file or directory", hanging shell
    # startup. Re-enable once package.json declares real dependencies.
    npm.install.enable = false;
  };

  inherit (devenvUtils) processes tasks;

  git-hooks.hooks = {
    ansible-lint.enable = true;
    nix-quality = {
      enable = true;
      name = "nix-quality";
      entry = "${pkgs.uv}/bin/uv run python scripts/nix-quality.py";
      files = "\\.nix$|^flake\\.lock$|^nix-quality\\.yml$|^scripts/nix-quality\\.py$|^(homes|lib|modules|overlays|packages|shells|systems|tests/nixtest|topology)/";
      pass_filenames = false;
    };
  };

  inherit (devenvUtils) scripts;

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
