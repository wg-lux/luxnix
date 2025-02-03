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
    dashboardHost = mkOpt types.str "dashboard.traefik.local" "Hostname for the dashboard";
    allowedIPs = mkOpt (types.listOf types.str) ["127.0.0.1"] "IPs allowed to access the dashboard";
    bindIP = mkOpt types.str "0.0.0.0" "IP address to bind Traefik to";
    sslCertPath = mkOpt types.path config.luxnix.generic-settings.sslCertificatePath "Path to SSL certificate";
    sslKeyPath = mkOpt types.path config.luxnix.generic-settings.sslCertificateKeyPath "Path to SSL key";
    keycloak = {
      enable = mkBoolOpt false "Enable Keycloak routing";
      domain = mkOpt types.str "keycloak.endo-reg.net" "Keycloak domain";
      port = mkOpt types.str "9080" "Keycloak HTTP port";
    };
  };

  config = mkIf cfg.enable {
    services.luxnix.traefik = {
      enable = cfg.enable;
      dashboard = cfg.dashboard;
      insecure = cfg.insecure;
      staticConfigOptions = cfg.staticConfigOptions;
      dashboardHost = cfg.dashboardHost;
      allowedIPs = cfg.allowedIPs;
      bindIP = cfg.bindIP;
      sslCertPath = cfg.sslCertPath;
      sslKeyPath = cfg.sslKeyPath;
      keycloak = {
        enable = cfg.keycloak.enable;
        domain = cfg.keycloak.domain;
        port = cfg.keycloak.port;
      };
    };
  };
}