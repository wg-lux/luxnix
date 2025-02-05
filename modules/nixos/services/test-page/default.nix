{config, lib, pkgs, ...}: 

with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.testPage;

  vpnIp = config.luxnix.generic-settings.vpnIp;
in {
  options.services.luxnix.testPage = {
    enable = mkBoolOpt false "Enable httpd test page";
    port = mkOption {
      type = types.int;
      default = 8081;
      description = "Port to bind the test page to";
    };

  };

  config = mkIf cfg.enable {
    systemd.services.testPage = {
      description = "Simple test page service";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.busybox}/bin/busybox httpd -f -v -h /etc/opt/test-page -p 0.0.0.0:${toString cfg.port}";
      };
    };

    # allow firewall access to the test page
    networking.firewall.allowedTCPPorts = [ 80 8081 ];

    environment.etc."opt/test-page/index.html".text = ''
      <html>
        <body>
          <h1>Hello from test.endo-reg.net!</h1>
        </body>
      </html>
    '';

  };
}