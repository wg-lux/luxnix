{
  config,
  lib,
  ...
}:
#CHANGEME 
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.authentik;
in {
  # options.services.luxnix.authentik = with types; {
  #   enable = mkBoolOpt false "Enable authentik host";
  # };

  # config = mkIf cfg.enable {
  #   # for prototyping
  #   environment.etc."authentik/env".text = ''
  #     authenik_env: |
  #       AUTHENTIK_SECRET_KEY=asdasd
  #       AUTHENTIK_EMAIL__PASSWORD=asdasd
  #     '';

  #   services = {
  #     authentik = {
  #       enable = true;
  #       environmentFile = "/etc/authentik/env";
  #       settings = {
  #         email = {
  #         # email settings
  #         };
  #         disable_startup_analytics = true;
  #         avatars = "initials";
  #       };
  #     };
  #   };

  # };
}
