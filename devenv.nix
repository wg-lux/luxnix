{ pkgs, lib, config, inputs, ... }:
let
  buildInputs = with pkgs; [
    python311Full
    stdenv.cc.cc
    tesseract
    glib
    openssh
    openssl
    black
    nixpkgs-fmt
  ];

in 
{

  # A dotenv file was found, while dotenv integration is currently not enabled.
  dotenv.enable = false;
  dotenv.disableHint = true;

  packages = with pkgs; [
    cudaPackages.cuda_nvcc
    age
    openssh
    stdenv.cc.cc
    tesseract
    sops
    openssl
    black
    nixpkgs-fmt #TODO WILL BE DEPRECATED SOON ->  nixfmt
  ];

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

  tasks = {

    "autoconf:generate-hostinfo" = {
      description = "Generate conf/hostinfo.json; Generates hostinfo @ ./docs/hostinfo\
       (summary markdown; html split by host)";
      exec = "./scripts/ansible-cmdb.sh";
      # after = [ "autoconf:setup-symlinks"];
    };

    "autoconf:finished" = {
      description = "Start the finalize task";
      exec = "echo 'Starting finalize task'";
      after = [ "autoconf:generate-hostinfo"];
    };
  };

  scripts = {
    hello.exec = "${pkgs.uv}/bin/uv run python hello.py";
    utest.exec = "${pkgs.uv}/bin/uv run python -m unittest";
    initialize-luxnix-repo.exec = ''
      direnv allow
      touch .repo_initialized
    '';

    hi.exec = "${pkgs.uv}/bin/uv run python lx_administration/ansible/hostinfo.py";
    
    
    init-server-ssh.exec = "./tmux/init-server-ssh.sh";
    kill-server-ssh.exec = "tmux kill-session -t ssh-servers";
    conn-server-ssh.exec = "tmux attach-session -t ssh-servers";
  };

  processes = {
  };

  enterShell = ''
    . .devenv/state/venv/bin/activate
    hello
  '';

  enterTest = ''
    nvcc -V
    python -m unittest
  '';
}
