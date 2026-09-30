# Purpose: Admit API work before limiting the shared background-worker slice.
{ ctx }:
with ctx;
let
  throttle = cfg.runtime.frontendRequestThrottle;
  directory = "/run/lx-annotate-request-throttle";
  socketUnit = "lx-annotate-request-throttle.socket";
  controllerUnit = "lx-annotate-request-throttle.service";
  runtimeCheck = pkgs.writeShellScript "lx-annotate-request-throttle-runtime-check" ''
    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage shell -c ${lib.escapeShellArg ''
      from django.conf import settings
      from lx_annotate.middleware.request_throttle import FrontendRequestThrottleMiddleware
      assert str(settings.LX_ANNOTATE_REQUEST_THROTTLE_DIRECTORY) == "${directory}", "Request throttle directory contract mismatch"
      assert "lx_annotate.middleware.request_throttle.FrontendRequestThrottleMiddleware" in settings.MIDDLEWARE, "Request throttle middleware missing"
    ''}
  '';
in
mkIf throttle.enable {
  systemd.tmpfiles.rules = [
    "d ${directory} 0750 root ${endoreg-service-group-name} - -"
    "f ${directory}/activity.lock 0640 root ${endoreg-service-group-name} - -"
  ];
  systemd.slices.lx-annotate-background = {
    description = "LX-Annotate compute-heavy background workers";
    sliceConfig = {
      CPUAccounting = true;
      IOAccounting = true;
      CPUWeight = 100;
      IOWeight = 100;
    };
  };
  systemd.sockets.lx-annotate-request-throttle = {
    description = "Local API resource-admission socket";
    wantedBy = [ "sockets.target" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    requires = [ "systemd-tmpfiles-setup.service" ];
    socketConfig = {
      ListenStream = "${directory}/control.sock";
      SocketUser = "root";
      SocketGroup = endoreg-service-group-name;
      SocketMode = "0660";
      RemoveOnStop = true;
      Backlog = 128;
    };
  };
  systemd.services.lx-annotate-request-throttle = {
    description = "Apply API activity and trailing-buffer resource limits";
    wantedBy = [ "multi-user.target" ];
    requires = [
      socketUnit
      "lx-annotate-background.slice"
    ];
    after = [
      socketUnit
      "lx-annotate-background.slice"
    ];
    unitConfig.StartLimitIntervalSec = 0;
    serviceConfig = {
      ExecStart = lib.escapeShellArgs [
        "${pkgs.python3}/bin/python"
        "${../../../../../scripts/frontend-request-throttle.py}"
        "--directory"
        directory
        "--user"
        endoreg-service-user-name
        "--systemctl"
        "${pkgs.systemd}/bin/systemctl"
        "--tail-seconds"
        (toString throttle.tailSeconds)
        "--cpu-quota"
        throttle.cpuQuota
        "--cpu-weight"
        (toString throttle.cpuWeight)
        "--io-weight"
        (toString throttle.ioWeight)
      ];
      Sockets = [ socketUnit ];
      Restart = "on-failure";
      RestartSec = "1s";
      User = "root";
      NoNewPrivileges = true;
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateTmp = true;
      RestrictAddressFamilies = [ "AF_UNIX" ];
      LogNamespace = lxAnnotateJournalNamespace;
    };
  };
  systemd.services.lx-annotate = {
    wants = [ controllerUnit ];
    requires = [ socketUnit ];
    after = [
      socketUnit
      controllerUnit
    ];
    serviceConfig.ExecStartPre = [ runtimeCheck ];
  };
}
