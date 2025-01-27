{ pkgs, lib, config, inputs, ... }:
let
#
  packageDefs = import ./devenv/packages.nix { inherit pkgs; };
  buildInputs = packageDefs.buildInputs;
  tasks = import ./devenv/tasks.nix {
    inherit pkgs lib config inputs;
  };
  scripts = import ./devenv/scripts.nix {
    inherit pkgs lib config inputs;
  };
  processes = import ./devenv/processes.nix {inherit pkgs;};

in 
{
  packages = packageDefs.packages;

  # A dotenv file was found, while dotenv integration is currently not enabled.
  dotenv.enable = false;
  dotenv.disableHint = true;

  env = {
    LD_LIBRARY_PATH = "${
      with pkgs;
      lib.makeLibraryPath buildInputs
    }:/run/opengl-driver/lib:/run/opengl-driver-32/lib";
  };

  languages.python = {
    enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  tasks = tasks;

  scripts = scripts;

  processes = {
  };

  enterShell = ''
    . .devenv/state/venv/bin/activate
    uv pip install -e .
    # devenv tasks run "autoconf:initialize-vault"
    python -m unittest
    hello
  '';

  enterTest = ''
    nvcc -V
    python -m unittest
  '';
}
