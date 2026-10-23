{
  config,
  inputs,
  lib,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.winapps;
  # Must match CONTAINER_NAME in the WinApps client.
  containerName = "WinApps";
  userHome = config.users.users.${cfg.user}.home;
in
{
  options.services.luxnix.winapps = {
    enable = mkBoolOpt false "Run the WinApps Windows container (dockur/windows) as a systemd service";
    image = mkOpt types.str "ghcr.io/dockur/windows:6.06" "Pinned dockur/windows image";
    user =
      mkOpt types.str config.user.admin.name
        "User whose home is shared with Windows as \\\\host.lan\\Data";
    version = mkOpt types.str "11" "Windows version installed by dockur/windows";
    cpuCores = mkOpt types.ints.positive 4 "CPU cores allocated to the Windows VM";
    ramSize = mkOpt types.str "4G" "RAM allocated to the Windows VM";
    diskSize = mkOpt types.str "64G" "Size of the Windows system disk (sparse)";
    stateDir = mkOpt types.path "/var/lib/winapps" "Host directory holding the Windows disk image";
    username = mkOpt types.str "MyWindowsUser" "Local Windows account created on first install";
    # Default matches the IMGW compose.yaml; the value is stored in the Nix store.
    password =
      mkOpt types.str "MyWindowsPassword"
        "Password of the local Windows account (ignored when environmentFile is set)";
    environmentFile =
      mkOpt (types.nullOr types.path) null
        "Runtime env file (e.g. a SOPS secret) providing USERNAME and PASSWORD";
    autoStart = mkBoolOpt true "Start the Windows container at boot";
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion = config.users.users ? ${cfg.user};
        message = "services.luxnix.winapps.user '${cfg.user}' is not a declared user.";
      }
    ];

    virtualisation.oci-containers.backend = "podman";
    virtualisation.oci-containers.containers.${containerName} = {
      inherit (cfg) image autoStart;
      environment = {
        VERSION = cfg.version;
        CPU_CORES = toString cfg.cpuCores;
        RAM_SIZE = cfg.ramSize;
        DISK_SIZE = cfg.diskSize;
        HOME = userHome;
      }
      // optionalAttrs (cfg.environmentFile == null) {
        USERNAME = cfg.username;
        PASSWORD = cfg.password;
      };
      environmentFiles = optional (cfg.environmentFile != null) cfg.environmentFile;
      # RDP and the VNC web console stay on loopback.
      ports = [
        "127.0.0.1:8006:8006"
        "127.0.0.1:3389:3389/tcp"
        "127.0.0.1:3389:3389/udp"
      ];
      volumes = [
        "${cfg.stateDir}:/storage"
        "${userHome}:/shared"
        # Post-install script applying the RDPApps registry changes.
        "${inputs.winapps}/oem:/oem:ro"
      ];
      # Privileged is required by the IMGW fork to pass HOME through to the VM.
      privileged = true;
      capabilities.NET_ADMIN = true;
      devices = [
        "/dev/kvm"
        "/dev/net/tun"
      ];
      # Give Windows time to shut down cleanly before podman kills it.
      extraOptions = [ "--stop-timeout=120" ];
    };

    systemd.services."podman-${containerName}".serviceConfig.TimeoutStopSec = mkForce 180;

    systemd.tmpfiles.rules = [ "d ${cfg.stateDir} 0700 root root - -" ];
  };
}
