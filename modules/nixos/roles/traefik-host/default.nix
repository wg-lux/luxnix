{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.roles.traefikHost;
  hostVpnIp = config.luxnix.generic-settings.traefikHostIp;
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
      port = mkOpt types.port 9080 "Keycloak HTTP port";
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

    systemd.services.testPage = {
      description = "Simple test page service";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.busybox}/bin/busybox httpd -f -v -h /opt/test-page -p ${hostVpnIp}:8081";
      };
    };

    environment.etc."opt/test-page/index.html".text = ''
      <html>
        <body>
          <h1>Hello from test.endo-reg.net!</h1>
        </body>
      </html>
    '';

  };
}