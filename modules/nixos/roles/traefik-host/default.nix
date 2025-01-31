{config, lib, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.roles.traefikHost;
in {
  options.roles.traefikHost = {
    enable = mkBoolOpt false "Enable traefik";
    dashboard = mkBoolOpt true "Enable traefik dashboard";
    insecure = mkBoolOpt false "Allow insecure configurations";
    staticConfigOptions = mkOpt types.attrs {} "Additional static configuration options";
  };

  config = mkIf cfg.enable {
    services.luxnix.traefik = {
      enable = cfg.enable;
      dashboard = cfg.dashboard;
      insecure = cfg.insecure;
      staticConfigOptions = cfg.staticConfigOptions;
    };
  };
}