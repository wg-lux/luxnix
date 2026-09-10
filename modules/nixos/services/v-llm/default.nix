{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.vllm;

  serveArgs = [
    "serve"
    cfg.model
    "--host"
    cfg.host
    "--port"
    (toString cfg.port)
    "--download-dir"
    cfg.downloadDir
  ]
  ++ optional (cfg.tensorParallelSize != null) "--tensor-parallel-size"
  ++ optional (cfg.tensorParallelSize != null) (toString cfg.tensorParallelSize)
  ++ optional (cfg.maxModelLen != null) "--max-model-len"
  ++ optional (cfg.maxModelLen != null) (toString cfg.maxModelLen)
  ++ optional (cfg.gpuMemoryUtilization != null) "--gpu-memory-utilization"
  ++ optional (cfg.gpuMemoryUtilization != null) (toString cfg.gpuMemoryUtilization)
  ++ cfg.extraArgs;

  execStart = "${cfg.package}/bin/vllm ${escapeShellArgs serveArgs}";
in
{
  options.services.luxnix.vllm = {
    enable = mkBoolOpt false "Enable the host-based vLLM service.";

    package = mkPackageOpt pkgs.vllm "The nixpkgs vLLM package to run.";

    host = mkOpt types.str "0.0.0.0" "Host/IP for the vLLM OpenAI-compatible API.";

    port = mkOpt types.port 8000 "TCP port for the vLLM API.";

    model = mkOpt types.str "Qwen/Qwen2.5-1.5B-Instruct" "Model identifier passed to `vllm serve`.";

    openFirewall = mkBoolOpt false "Open the configured vLLM TCP port in the host firewall.";

    user = mkOpt types.str "vllm" "System user used to run the vLLM service.";

    group = mkOpt types.str "vllm" "System group used to run the vLLM service.";

    supplementaryGroups = mkOpt (types.listOf types.str) [
      "video"
      "render"
    ] "Supplementary groups for GPU access.";

    stateDir = mkOpt types.str "/var/lib/vllm" "Persistent state directory for the service.";

    cacheDir = mkOpt types.str "/var/cache/vllm" "Cache directory for Hugging Face and vLLM caches.";

    downloadDir = mkOpt types.str "/var/cache/vllm/models" "Model download directory passed to vLLM.";

    environment =
      mkOpt (types.attrsOf types.str) { }
        "Additional environment variables for the vLLM service.";

    environmentFile =
      mkOpt (types.nullOr types.path) null
        "Optional environment file for secrets like HF_TOKEN.";

    tensorParallelSize = mkOpt (types.nullOr types.int) null "Optional tensor parallel size.";

    maxModelLen = mkOpt (types.nullOr types.int) 262144 "Optional `--max-model-len` value.";

    gpuMemoryUtilization =
      mkOpt (types.nullOr types.float) 0.9
        "Optional `--gpu-memory-utilization` value.";

    extraArgs = mkOpt (types.listOf types.str) [ ] "Additional CLI arguments appended to `vllm serve`.";
  };

  config = mkIf cfg.enable {
    users.groups.${cfg.group} = { };

    users.users.${cfg.user} = {
      isSystemUser = true;
      inherit (cfg) group;
      home = cfg.stateDir;
      createHome = false;
      extraGroups = cfg.supplementaryGroups;
    };

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.cacheDir} 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.downloadDir} 0750 ${cfg.user} ${cfg.group} -"
    ];

    networking.firewall.allowedTCPPorts = optional cfg.openFirewall cfg.port;

    systemd.services.vllm = {
      description = "vLLM OpenAI-compatible inference server";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        HF_HOME = cfg.cacheDir;
        VLLM_CONFIG_ROOT = cfg.cacheDir;
        VLLM_CACHE_ROOT = cfg.cacheDir;
        XDG_CACHE_HOME = cfg.cacheDir;
      }
      // cfg.environment;

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.stateDir;
        ExecStart = execStart;
        Restart = "always";
        RestartSec = "10s";
        RuntimeDirectory = "vllm";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [
          cfg.stateDir
          cfg.cacheDir
          cfg.downloadDir
        ];
        LimitNOFILE = 1048576;
      }
      // optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = cfg.environmentFile;
      };
    };
  };
}
