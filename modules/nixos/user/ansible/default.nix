{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.ansible;
in {
  options.user.ansible = {
    enable = mkBoolOpt false "Enable Ansible Config + User";
  };

  config = mkIf cfg.enable {
    # users.users.ansible =
    #   {
    #     shell = pkgs.zsh;
    #     isSystemUser = true;
    #     createHome = true;
    #     home = "/home/ansible";
    #     group = "root";
    #     homeMode = "0750";
    #     uid = 400;
    #   };

    environment.systemPackages = with pkgs; [
      ansible
      ansible-lint
    ];

    luxnix.python.sw.enable = true;
    
  };
}