{
  config,
  lib,
  inputs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.security.sops;
in {
  options.security.sops = with types; {
    enable = mkBoolOpt false "Whether to enable sop for secrets management.";
  };

  imports = with inputs; [
    sops-nix.homeManagerModules.sops
  ];

  config = mkIf cfg.enable {
    sops = {
      age = {
        generateKey = true;
        keyFile = "/home/${config.luxnix.user.admin.name}/.config/sops/age/keys.txt";
        sshKeyPaths = ["/home/${config.luxnix.user.admin.name}/.ssh/id_ed25519"];
      };

      defaultSymlinkPath = "/run/user/1000/secrets";
      defaultSecretsMountPoint = "/run/user/1000/secrets.d";
    };
  };
}
