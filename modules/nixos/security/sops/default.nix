{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.security.sops;

  # CHANGEME Enable sops
in
{
  options.security.sops = with types; {
    enable = mkBoolOpt false "Whether to enable sop for secrets management.";
  };

  config = mkIf cfg.enable {
    sops = {
      defaultSopsFile = ../../secrets.yaml;
      defaultSopsFormat = "yaml";
      age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];

      # TODO: Deploy SOPS keys and enable
      # secrets = {
      #   client_user_password_hash = {
      #     path = "/etc/secrets/vault/SCRT_client_user_password_hash";
      #     owner = "root";
      #     group = "root";
      #     mode = "0400";
      #     neededForUsers = true;
      #   };

      #   nextcloud_host_password = mkIf config.roles.nextcloudHost.enable {
      #     path = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
      #     owner = "root";
      #     group = "root";
      #     mode = "0400";
      #   };
      #};
    };
  };
}
