{
  lib,
  pkgs,
  config,
  ...
}:
let
  cfg = config.roles.hetzner;
in
{
  options.roles.hetzner = {
    enable = lib.mkEnableOption "Enable common configuration for hetzner cloud servers";
  };

  config = lib.mkIf cfg.enable {
    users.users = {
      root.hashedPassword = "!"; # Disable root login
      root.openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzx1++LopfWjjt7ZQDtqBvtu89+7YsPnkC+18BV35Vt983ve2nB1ZyE0WN5Xl3jnBvZ/a+tYeWnArSh6+ywe97Jt9+YxdJRuf9F9JdiTAVKW4H9S1UwWb42rh4rM0yJoGL1dWpXRIu2e2kXDw3a4P4VYkqTeFhMSeovaLVDZ4sGCm2KkSr7SsrNs5Xydb34yOPLb7SyVd5hVYWnCqR3QEFFooShDETE83I9ThfW8JqWWpi1ApO9BJboj91pE4RwymsHcHgD4K/OP6ul/HMUPAGuJZjsgokhcb+1WK4dcTrtnRG8FHJaz2gcYL0wvIwncwPhxVLLDMXsWwxo8PO+eKJ hetzner-main"
    ];
    admin = {
      isNormalUser = true;
      extraGroups = [ "wheel" ];
      openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzx1++LopfWjjt7ZQDtqBvtu89+7YsPnkC+18BV35Vt983ve2nB1ZyE0WN5Xl3jnBvZ/a+tYeWnArSh6+ywe97Jt9+YxdJRuf9F9JdiTAVKW4H9S1UwWb42rh4rM0yJoGL1dWpXRIu2e2kXDw3a4P4VYkqTeFhMSeovaLVDZ4sGCm2KkSr7SsrNs5Xydb34yOPLb7SyVd5hVYWnCqR3QEFFooShDETE83I9ThfW8JqWWpi1ApO9BJboj91pE4RwymsHcHgD4K/OP6ul/HMUPAGuJZjsgokhcb+1WK4dcTrtnRG8FHJaz2gcYL0wvIwncwPhxVLLDMXsWwxo8PO+eKJ hetzner-main"
      ];
    };
  };
  };
}
