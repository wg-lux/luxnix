{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.luxnix.openbao;
  localCfg = cfg.local;
  storage = config.luxnix.storage.operatorUnlocked or { };
  # Volume unlock depends on the local store only once the storage profile says so;
  # before that, enrollment can install and use the tool without a boot dependency.
  localRequired = (storage.enable or false) && (storage.unlockMethod or "") == "local-openbao";
  # Passphrase seal: the operator's boot passphrase unwraps the seal key; no TPM binding.
  passphraseSeal = localCfg.seal == "passphrase";
  stagedSealKey = "/run/luxnix-openbao-seal/seal.key";
  localClient = ../../../../lx_administration/storage/openbao_local.py;
  # Match the pinned upstream sandbox for both independently owned instances.
  hardening = {
    CapabilityBoundingSet = "";
    LimitCORE = 0;
    LockPersonality = true;
    MemorySwapMax = 0;
    MemoryZSwapMax = 0;
    PrivateUsers = "identity";
    ProcSubset = "pid";
    ProtectClock = true;
    ProtectControlGroups = true;
    ProtectHome = true;
    ProtectHostname = true;
    ProtectKernelLogs = true;
    ProtectKernelModules = true;
    ProtectKernelTunables = true;
    ProtectProc = "invisible";
    RestrictNamespaces = true;
    RestrictRealtime = true;
    SystemCallArchitectures = "native";
    SystemCallFilter = [
      "@system-service"
      "@resources"
      "~@privileged"
      "@chown"
    ];
    UMask = "0077";
  };
  # Rendered per unit: systemd exposes credentials under the loading unit's name.
  localSettings =
    unit:
    (pkgs.formats.json { }).generate "${unit}.json" {
      ui = false;
      api_addr = "http://127.0.0.1:8310";
      cluster_addr = "https://127.0.0.1:8311";
      storage.raft = {
        path = "/var/lib/openbao-local";
        node_id = config.networking.hostName;
      };
      # Raft 2.6 requires a TCP listener to create cluster addresses. This listener
      # exists only inside PrivateNetwork; all external clients use the Unix socket.
      listener.raft = {
        type = "tcp";
        address = "127.0.0.1:8310";
        cluster_address = "127.0.0.1:8311";
        tls_disable = true;
      };
      listener.local = {
        type = "unix";
        address = "/run/openbao-local/api.sock";
        socket_mode = "0600";
        socket_user = "openbao-local";
        socket_group = "openbao-local";
      };
      seal.static = {
        current_key_id = localCfg.sealKeyId;
        current_key = "file:///run/credentials/${unit}.service/seal.key";
      };
      audit = [
        {
          file.local = {
            description = "Local volume key audit";
            options.file_path = "/var/lib/openbao-local/audit.jsonl";
          };
        }
      ];
    };
  localRuntimePreflight = pkgs.writeShellScript "openbao-local-runtime-preflight" ''
    set -eu
    ulimit -c 0
    export PATH=${
      lib.makeBinPath [
        pkgs.systemd
        pkgs.util-linux
      ]
    }
    ${pkgs.python3}/bin/python ${../../../../lx_administration/secret_storage.py} --allow-runtime /run
  '';
  localPreflight = pkgs.writeShellScript "openbao-local-preflight" ''
    set -eu
    ${localRuntimePreflight}
    export PATH=${lib.makeBinPath [ pkgs.systemd ]}
    ${lib.optionalString (!passphraseSeal) "${pkgs.python3}/bin/python ${localClient} --platform-only"}
    ${lib.optionalString (!passphraseSeal)
      "exec ${pkgs.python3}/bin/python ${localClient} ${lib.escapeShellArg localCfg.sealCredentialFile}"
    }
  '';
  # ENC-21: refuse activation of an unlock profile the host cannot satisfy now,
  # instead of failing at the next boot. Live checks, never inventory facts.
  localActivationGate = pkgs.writeShellScript "openbao-local-activation-gate" ''
    set -eu
    ulimit -c 0
    fail() { echo "local OpenBao activation blocked: $1" >&2; exit 1; }
    [ -f /var/lib/openbao-local/raft/raft.db ] || fail not-enrolled
    [ ! -e /var/lib/openbao-bootstrap/pending-enrollment.cred ] || fail escrow-unconfirmed
    ${lib.optionalString passphraseSeal "[ -f /var/lib/openbao-bootstrap/seal-passphrase.json ] || fail seal-passphrase-missing"}
    ${localPreflight} || fail credential-not-tpm
    ${lib.optionalString passphraseSeal "${pkgs.python3}/bin/python ${localClient} --verify-seal || fail seal-passphrase-unverified"}
    ${pkgs.python3}/bin/python ${localClient} --seal ${localCfg.seal} \
      ${lib.escapeShellArg storage.openbaoUnlockCredential} || fail credential-not-tpm
    ${pkgs.systemd}/bin/systemd-run --wait --collect --quiet \
      --property=Type=oneshot --property=LimitCORE=0 \
      ${
        lib.optionalString (!passphraseSeal)
          "--property=${lib.escapeShellArg "LoadCredentialEncrypted=seal.key:${localCfg.sealCredentialFile}"}"
        + lib.optionalString passphraseSeal "--property=${lib.escapeShellArg "LoadCredential=seal.key:${stagedSealKey}"}"
      } \
      --property=${lib.escapeShellArg "LoadCredentialEncrypted=volume.unlock:${storage.openbaoUnlockCredential}"} \
      ${pkgs.coreutils}/bin/true || fail credential-rejected
  '';
  verifyStorage = pkgs.writeShellScript "verify-openbao-storage" ''
    export PATH=${lib.makeBinPath [ pkgs.util-linux ]}
    exec ${pkgs.python3}/bin/python ${../../../../lx_administration/secret_storage.py} "$@"
  '';
  localServiceConfig =
    unit:
    hardening
    // {
      Type = "notify";
      User = "openbao-local";
      Group = "openbao-local";
      ExecStart = "${lib.getExe pkgs.openbao} server -config ${localSettings unit}";
      LoadCredentialEncrypted = lib.optional (!passphraseSeal) "seal.key:${localCfg.sealCredentialFile}";
      LoadCredential = lib.optional passphraseSeal "seal.key:${stagedSealKey}";
      StateDirectory = "openbao-local";
      StateDirectoryMode = "0700";
      RuntimeDirectory = "openbao-local";
      RuntimeDirectoryMode = "0700";
      UMask = "0077";
      LimitCORE = 0;
      MemorySwapMax = 0;
      MemoryZSwapMax = 0;
      NoNewPrivileges = true;
      ProtectSystem = "strict";
      ProtectHome = true;
      PrivateTmp = true;
      PrivateNetwork = true;
      PrivateDevices = true;
      RestrictAddressFamilies = [
        "AF_UNIX"
        "AF_INET"
        "AF_INET6"
      ];
      TimeoutStartSec = "90s";
    };
  # Host side of the cataloged enrollment (lx_administration/storage/local_enrollment.py).
  enrollTool = pkgs.writeShellApplication {
    name = "luxnix-openbao-local";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.cryptsetup
      pkgs.systemd
    ];
    text = ''
      ulimit -c 0
      ${localRuntimePreflight}
      exec ${pkgs.python3}/bin/python3 -I ${../../../../lx_administration/storage/openbao_enroll.py} \
        --client ${localClient} \
        --hostname ${lib.escapeShellArg config.networking.hostName} \
        --seal ${localCfg.seal} \
        "$@"
    '';
  };
in
{
  options.luxnix.openbao = {
    enable = lib.mkEnableOption "isolated OpenBao hub backend";
    local = {
      enable = lib.mkEnableOption "independent local OpenBao (enrollment required)";
      seal = lib.mkOption {
        type = lib.types.enum [
          "tpm"
          "passphrase"
        ];
        default = "tpm";
        description = "tpm: TPM/PCR 7-sealed key, requires Secure Boot. passphrase: the operator's boot passphrase unwraps the escrowed seal key.";
      };
      sealCredentialFile = lib.mkOption {
        type = lib.types.str;
        default = "/var/lib/openbao-bootstrap/seal.cred";
        description = "Root-owned systemd encrypted credential, explicit TPM-only with PCR 7.";
      };
      sealKeyId = lib.mkOption {
        type = lib.types.strMatching "[A-Za-z0-9_-]+";
        default = "local-v1";
        description = "Permanent identifier of the independently escrowed seal key.";
      };
    };
    apiAddress = lib.mkOption {
      type = lib.types.str;
      default = "https://127.0.0.1:8300";
      description = "Pinned HTTPS endpoint advertised to clients; separate from existing Vault.";
    };
    bindAddress = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1:8300";
      description = "Explicit listener address; firewall access is managed separately.";
    };
    tlsCertificateFile = lib.mkOption {
      type = lib.types.str;
      default = "/etc/secrets/openbao/server.pem";
      description = "Runtime PEM certificate, including its intermediate chain.";
    };
    tlsKeyFile = lib.mkOption {
      type = lib.types.str;
      default = "/etc/secrets/openbao/server-key.pem";
      description = "Runtime TLS private key on encrypted or volatile storage.";
    };
  };

  config = lib.mkMerge [
    (lib.mkIf cfg.enable {
      assertions = [
        {
          assertion = lib.hasPrefix "https://" cfg.apiAddress;
          message = "OpenBao requires an HTTPS API address.";
        }
        {
          assertion = builtins.hasAttr "/var/lib/openbao" config.fileSystems;
          message = "OpenBao requires a separate encrypted mount or bind at /var/lib/openbao.";
        }
        {
          assertion = lib.all (p: lib.hasPrefix "/" p && !(lib.hasPrefix "/nix/store/" p)) [
            cfg.tlsCertificateFile
            cfg.tlsKeyFile
          ];
          message = "OpenBao TLS files must be absolute runtime paths outside the Nix store.";
        }
      ];
      services.openbao = {
        enable = true;
        settings = {
          ui = false;
          audit = [
            {
              file.release = {
                description = "Volume release audit";
                options.file_path = "/var/lib/openbao/audit.jsonl";
              };
            }
          ];
          api_addr = cfg.apiAddress;
          cluster_addr = "https://127.0.0.1:8301";
          storage.raft = {
            path = "/var/lib/openbao";
            node_id = config.networking.hostName;
          };
          listener.release = {
            type = "tcp";
            address = cfg.bindAddress;
            cluster_address = "127.0.0.1:8301";
            tls_disable = false;
            tls_disable_client_certs = false;
            tls_min_version = "tls12";
            tls_cert_file = "/run/credentials/openbao.service/server.pem";
            tls_key_file = "/run/credentials/openbao.service/server-key.pem";
          };
        };
      };
      users.users.openbao = {
        isSystemUser = true;
        group = "openbao";
      };
      users.groups.openbao = { };
      systemd.services.openbao = {
        requires = [ "var-lib-openbao.mount" ];
        after = [ "var-lib-openbao.mount" ];
        bindsTo = [ "var-lib-openbao.mount" ];
        unitConfig.AssertPathIsMountPoint = "/var/lib/openbao";
        serviceConfig = hardening // {
          DynamicUser = lib.mkForce false;
          LoadCredential = [
            "server.pem:${cfg.tlsCertificateFile}"
            "server-key.pem:${cfg.tlsKeyFile}"
          ];
          ExecStartPre = [
            "+${verifyStorage} /var/lib/openbao"
            "+${verifyStorage} --allow-runtime ${lib.escapeShellArg cfg.tlsKeyFile}"
          ];
          TimeoutStartSec = "90s";
        };
      };
    })
    (lib.mkIf localCfg.enable {
      assertions = [
        {
          assertion =
            lib.hasPrefix "/var/lib/openbao-bootstrap/" localCfg.sealCredentialFile
            && !(lib.hasInfix ".." localCfg.sealCredentialFile);
          message = "Local OpenBao bootstrap must be outside operator-unlocked storage.";
        }
      ];
      security.tpm2.enable = lib.mkIf (!passphraseSeal) true;
      users.groups.openbao-local = { };
      users.users.openbao-local = {
        isSystemUser = true;
        group = "openbao-local";
      };
      system.preSwitchChecks = lib.mkIf localRequired {
        openbaoLocalPreflight = "${localActivationGate}";
      };
      environment.systemPackages = [ enrollTool ];
      systemd.services = {
        openbao-local-preflight = {
          after = [ "swap.target" ];
          before = [ "openbao-local.service" ];
          serviceConfig = {
            Type = "oneshot";
            ExecStart = localPreflight;
            TimeoutStartSec = "40s";
            LimitCORE = 0;
          };
        };
        # Boot prompt before the login screen; enrollment stages the key over SSH instead.
        openbao-local-seal-key = lib.mkIf passphraseSeal {
          description = "Ask the boot passphrase for local OpenBao";
          path = [ pkgs.systemd ];
          unitConfig.DefaultDependencies = false;
          requires = [ "openbao-local-preflight.service" ];
          after = [
            "local-fs.target"
            "swap.target"
            "openbao-local-preflight.service"
          ];
          before = [
            "display-manager.service"
            "plymouth-quit.service"
            "plymouth-quit-wait.service"
          ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            UMask = "0077";
            LimitCORE = 0;
            MemorySwapMax = 0;
            MemoryZSwapMax = 0;
            TimeoutStartSec = "infinity";
            ExecStart = "${pkgs.python3}/bin/python ${localClient} --stage-seal";
          };
        };
        openbao-local = {
          description = "Independent local OpenBao";
          # Before the storage profile switches, only enrollment starts the service.
          wantedBy = lib.optional localRequired "multi-user.target";
          requires = [
            "openbao-local-preflight.service"
          ]
          ++ lib.optional passphraseSeal "openbao-local-seal-key.service";
          after = [
            "openbao-local-preflight.service"
          ]
          ++ lib.optional passphraseSeal "openbao-local-seal-key.service";
          conflicts = [ "openbao-local-initialize.service" ];
          restartIfChanged = false;
          unitConfig.AssertPathExists = "/var/lib/openbao-local/raft/raft.db";
          serviceConfig = localServiceConfig "openbao-local";
        };
        # Started only by `luxnix-openbao-local initialize`; never on boot and never
        # over existing state, so a missing store is not silently replaced.
        openbao-local-initialize = {
          description = "One-time initialization of local OpenBao (enrollment only)";
          requires = [ "openbao-local-preflight.service" ];
          after = [ "openbao-local-preflight.service" ];
          conflicts = [ "openbao-local.service" ];
          restartIfChanged = false;
          unitConfig.AssertPathExists = "!/var/lib/openbao-local/raft/raft.db";
          serviceConfig = localServiceConfig "openbao-local-initialize";
        };
      };
    })
  ];
}
