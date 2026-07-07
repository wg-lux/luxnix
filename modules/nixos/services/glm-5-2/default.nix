{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.glm52;

  modelFile =
    if cfg.modelFile != null then
      cfg.modelFile
    else
      "${cfg.modelDir}/${cfg.quant}/GLM-5.2-${cfg.quant}-00001-of-00006.gguf";

  pathDirsFrom =
    base: path:
    let
      baseSlash = "${base}/";
      relativePath = removePrefix baseSlash path;
      pathParts = filter (part: part != "") (splitString "/" relativePath);
      folded =
        foldl'
          (
            acc: part:
            let
              next = "${acc.current}/${part}";
            in
            {
              current = next;
              dirs = acc.dirs ++ [ next ];
            }
          )
          {
            current = base;
            dirs = [ base ];
          }
          pathParts;
    in
    if path == base then
      [ base ]
    else if hasPrefix baseSlash path then
      folded.dirs
    else
      [ path ];

  storageDirs = unique ((pathDirsFrom cfg.stateDir cfg.modelDir) ++ [ cfg.cacheDir ]);

  thinkingArgs =
    if cfg.thinkingMode == "default" then
      [ ]
    else
      [
        "--chat-template-kwargs"
        (builtins.toJSON (
          if cfg.thinkingMode == "off" then
            { enable_thinking = false; }
          else
            { reasoning_effort = cfg.thinkingMode; }
        ))
      ];

  serverArgs = [
    "--host"
    cfg.host
    "--port"
    (toString cfg.port)
    "--model"
    modelFile
    "--temp"
    (toString cfg.temperature)
    "--top-p"
    (toString cfg.topP)
    "--min-p"
    (toString cfg.minP)
  ]
  ++ optionals (cfg.alias != null) [
    "--alias"
    cfg.alias
  ]
  ++ optionals (cfg.contextSize != null) [
    "--ctx-size"
    (toString cfg.contextSize)
  ]
  ++ optionals (cfg.gpuLayers != null) [
    "--n-gpu-layers"
    (toString cfg.gpuLayers)
  ]
  ++ optionals (cfg.threads != null) [
    "--threads"
    (toString cfg.threads)
  ]
  ++ optionals (cfg.parallel != null) [
    "--parallel"
    (toString cfg.parallel)
  ]
  ++ optionals (cfg.cacheTypeK != null) [
    "--cache-type-k"
    cfg.cacheTypeK
  ]
  ++ optionals (cfg.cacheTypeV != null) [
    "--cache-type-v"
    cfg.cacheTypeV
  ]
  ++ thinkingArgs
  ++ cfg.extraArgs;

  downloadArgs = [
    "download"
    cfg.huggingFaceRepo
    "--local-dir"
    cfg.modelDir
    "--include"
    "*${cfg.quant}*"
  ]
  ++ cfg.downloadExtraArgs;

  checkModel = pkgs.writeShellScript "glm-5-2-check-model" ''
    set -euo pipefail

    if [ ! -r ${escapeShellArg modelFile} ]; then
      echo "GLM-5.2 model file is missing or unreadable: ${modelFile}" >&2
      echo "Run: systemctl start glm-5-2-download.service" >&2
      exit 1
    fi
  '';

  downloadModel = pkgs.writeShellScript "glm-5-2-download" ''
    set -euo pipefail

    mkdir -p ${escapeShellArg cfg.modelDir}
    exec ${escapeShellArgs ([ "${cfg.huggingFaceHubPackage}/bin/hf" ] ++ downloadArgs)}
  '';

  prepareStorage = pkgs.writeShellScript "glm-5-2-prepare-storage" ''
    set -euo pipefail

    for dir in ${escapeShellArgs storageDirs}; do
      install -d -o ${escapeShellArg cfg.user} -g ${escapeShellArg cfg.group} -m 0750 "$dir"
    done
  '';

  serverExec = escapeShellArgs ([ "${cfg.package}/bin/llama-server" ] ++ serverArgs);
  downloadUnit = "glm-5-2-download.service";
in
{
  options.services.luxnix.glm52 = {
    enable = mkBoolOpt false "Enable the GLM-5.2 llama.cpp inference service.";

    package = inputs.nixpkgs-unstable.legacyPackages.${pkgs.system}.llama-cpp; "llama.cpp package used for `llama-server`.";

    huggingFaceHubPackage = mkPackageOpt pkgs.python313Packages.huggingface-hub "Python package providing the `hf` CLI used by the download unit.";

    user = mkOpt types.str "glm-5-2" "System user used to run GLM-5.2 services.";

    group = mkOpt types.str "glm-5-2" "System group used to run GLM-5.2 services.";

    supplementaryGroups = mkOpt (types.listOf types.str) [
      "video"
      "render"
    ] "Supplementary groups for GPU device access.";

    host = mkOpt types.str "0.0.0.0" "Host/IP for the llama.cpp HTTP server.";

    port = mkOpt types.port 8088 "TCP port for the llama.cpp HTTP server.";

    openFirewall = mkBoolOpt false "Open the configured GLM-5.2 TCP port globally.";

    autoStart = mkBoolOpt true "Start the GLM-5.2 server at boot when the model file exists.";

    autoDownload = mkBoolOpt false "Automatically run the large Hugging Face download unit at boot.";

    stateDir = mkOpt types.str "/var/lib/glm-5-2" "Persistent state directory.";

    cacheDir = mkOpt types.str "/var/cache/glm-5-2" "Cache directory for Hugging Face and llama.cpp.";

    huggingFaceRepo =
      mkOpt types.str "unsloth/GLM-5.2-GGUF"
        "Hugging Face repository used by the download unit.";

    quant = mkOpt types.str "UD-IQ2_M" "GLM-5.2 GGUF quantization to download and run.";

    modelDir =
      mkOpt types.str "/var/lib/glm-5-2/models/unsloth/GLM-5.2-GGUF"
        "Local directory where the Hugging Face repository is downloaded.";

    modelFile =
      mkOpt (types.nullOr types.str) null
        "Explicit GGUF model file. Defaults to the first split for the configured quant.";

    alias = mkOpt (types.nullOr types.str) "glm-5.2" "Optional model alias exposed by llama-server.";

    temperature = mkOpt types.float 1.0 "Default sampling temperature.";

    topP = mkOpt types.float 0.95 "Default top-p sampling value.";

    minP = mkOpt types.float 0.01 "Default min-p sampling value.";

    contextSize = mkOpt (types.nullOr types.int) null "Optional llama.cpp context size.";

    gpuLayers = mkOpt (types.nullOr types.int) null "Optional number of layers to offload to GPU.";

    threads = mkOpt (types.nullOr types.int) null "Optional llama.cpp CPU thread count.";

    parallel = mkOpt (types.nullOr types.int) null "Optional llama.cpp parallel sequence count.";

    cacheTypeK = mkOpt (types.nullOr types.str) null "Optional K cache quantization type.";

    cacheTypeV = mkOpt (types.nullOr types.str) null "Optional V cache quantization type.";

    thinkingMode = mkOpt (types.enum [
      "default"
      "high"
      "max"
      "off"
    ]) "default" "GLM-5.2 reasoning mode passed through llama.cpp chat template kwargs.";

    extraArgs = mkOpt (types.listOf types.str) [ ] "Extra arguments appended to `llama-server`.";

    downloadExtraArgs = mkOpt (types.listOf types.str) [ ] "Extra arguments appended to `hf download`.";

    environment =
      mkOpt (types.attrsOf types.str) { }
        "Additional environment variables for the server.";

    studio = {
      enable = mkBoolOpt false "Enable optional Unsloth Studio service.";

      package = mkPackageOpt pkgs.python314Packages.unsloth "Python package providing the `unsloth` CLI.";

      host = mkOpt types.str "0.0.0.0" "Host/IP for Unsloth Studio.";

      port = mkOpt types.port 8888 "TCP port for Unsloth Studio.";

      openFirewall = mkBoolOpt false "Open the configured Unsloth Studio TCP port globally.";

      autoStart = mkBoolOpt true "Start Unsloth Studio at boot.";

      extraArgs = mkOpt (types.listOf types.str) [ ] "Extra arguments appended to `unsloth studio`.";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      users.groups.${cfg.group} = { };

      users.users.${cfg.user} = {
        isSystemUser = true;
        group = cfg.group;
        home = cfg.stateDir;
        createHome = false;
        extraGroups = cfg.supplementaryGroups;
      };

      systemd.tmpfiles.rules = concatMap (dir: [
        "d ${dir} 0750 ${cfg.user} ${cfg.group} -"
        "z ${dir} 0750 ${cfg.user} ${cfg.group} -"
      ]) storageDirs;

      networking.firewall.allowedTCPPorts = optional cfg.openFirewall cfg.port;

      systemd.services.glm-5-2-download = {
        description = "Download GLM-5.2 GGUF from Hugging Face";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = optional cfg.autoDownload "multi-user.target";

        environment = {
          HF_HOME = cfg.cacheDir;
          HF_XET_CACHE = "${cfg.cacheDir}/xet";
          XDG_CACHE_HOME = cfg.cacheDir;
        };

        serviceConfig = {
          Type = "oneshot";
          User = cfg.user;
          Group = cfg.group;
          WorkingDirectory = cfg.stateDir;
          ExecStartPre = "+${prepareStorage}";
          ExecStart = downloadModel;
          TimeoutStartSec = "infinity";
          PrivateTmp = true;
          ReadWritePaths = [
            cfg.stateDir
            cfg.cacheDir
            cfg.modelDir
          ];
        };
      };

      systemd.services.glm-5-2 = {
        description = "GLM-5.2 llama.cpp inference server";
        after = [ "network-online.target" ] ++ optional cfg.autoDownload downloadUnit;
        wants = [ "network-online.target" ] ++ optional cfg.autoDownload downloadUnit;
        requires = optional cfg.autoDownload downloadUnit;
        wantedBy = optional cfg.autoStart "multi-user.target";
        unitConfig.ConditionPathExists = modelFile;

        environment = {
          LLAMA_CACHE = cfg.modelDir;
          HF_HOME = cfg.cacheDir;
          XDG_CACHE_HOME = cfg.cacheDir;
        }
        // cfg.environment;

        serviceConfig = {
          Type = "exec";
          User = cfg.user;
          Group = cfg.group;
          WorkingDirectory = cfg.stateDir;
          ExecStartPre = [
            "+${prepareStorage}"
            checkModel
          ];
          ExecStart = serverExec;
          Restart = "on-failure";
          RestartSec = "10s";
          RuntimeDirectory = "glm-5-2";
          SupplementaryGroups = cfg.supplementaryGroups;
          NoNewPrivileges = true;
          PrivateTmp = true;
          ProtectSystem = "strict";
          ProtectHome = true;
          ReadWritePaths = [
            cfg.stateDir
            cfg.cacheDir
            cfg.modelDir
          ];
          LimitNOFILE = 1048576;
        };
      };
    }

    (mkIf cfg.studio.enable {
      networking.firewall.allowedTCPPorts = optional cfg.studio.openFirewall cfg.studio.port;

      systemd.services.glm-5-2-unsloth-studio = {
        description = "Unsloth Studio for GLM-5.2";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = optional cfg.studio.autoStart "multi-user.target";

        environment = {
          HF_HOME = cfg.cacheDir;
          XDG_CACHE_HOME = cfg.cacheDir;
        }
        // cfg.environment;

        serviceConfig = {
          Type = "exec";
          User = cfg.user;
          Group = cfg.group;
          WorkingDirectory = cfg.stateDir;
          ExecStart = escapeShellArgs (
            [
              "${cfg.studio.package}/bin/unsloth"
              "studio"
              "-H"
              cfg.studio.host
              "-p"
              (toString cfg.studio.port)
            ]
            ++ cfg.studio.extraArgs
          );
          Restart = "on-failure";
          RestartSec = "10s";
          SupplementaryGroups = cfg.supplementaryGroups;
          PrivateTmp = true;
          ReadWritePaths = [
            cfg.stateDir
            cfg.cacheDir
            cfg.modelDir
          ];
        };
      };
    })
  ]);
}
