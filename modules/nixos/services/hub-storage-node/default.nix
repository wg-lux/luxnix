{
  config,
  lib,
  pkgs,
  ...
}:

let
  inherit (lib)
    all
    attrNames
    concatMapStringsSep
    concatStringsSep
    escapeShellArg
    hasPrefix
    length
    map
    mkEnableOption
    mkIf
    mkMerge
    mkOption
    types
    unique
    ;

  cfg = config.services.luxnix.hubStorage;
  nodeCfg = cfg.node;
  hubCfg = cfg.hubClient;
  inherit (import "${pkgs.path}/nixos/lib/utils.nix" { inherit config lib pkgs; }) escapeSystemdPath;
  nodeMountUnit = "${escapeSystemdPath nodeCfg.storage.mountPoint}.mount";
  nodeDeviceUnit = "${escapeSystemdPath nodeCfg.storage.encryptedDevice}.device";
  nodeRecipientPrivateIdentityFiles = unique (
    (lib.optional (nodeCfg.recipientPrivateIdentityFile != "") nodeCfg.recipientPrivateIdentityFile)
    ++ nodeCfg.recipientPrivateIdentityFiles
  );
  storageNodeSource = builtins.path {
    path = ../../../../lx_administration;
    name = "lx-administration-storage-node-source";
  };
  storageNodePython = pkgs.python3.withPackages (pythonPackages: [
    pythonPackages.cryptography
    pythonPackages.pydantic
    pythonPackages.pyyaml
    pythonPackages.ruamel-yaml
  ]);
  storageNodePackage = pkgs.runCommand "lx-hub-storage-node" { } ''
    mkdir -p "$out/bin" "$out/lib"
    cp -r ${storageNodeSource} "$out/lib/lx_administration"
    cat > "$out/bin/lx-hub-storage-node" <<'EOF'
    #!${pkgs.runtimeShell}
    unset PYTHONPATH PYTHONHOME
    export PYTHONNOUSERSITE=1
    exec ${storageNodePython}/bin/python -I -s -c \
      'import sys; sys.path.insert(0, "${placeholder "out"}/lib"); from lx_administration.storage.data_plane import main; main()' \
      "$@"
    EOF
    chmod 0555 "$out/bin/lx-hub-storage-node"
  '';

  storageNodeType = types.submodule (_: {
    options = {
      identity = mkOption {
        type = types.str;
        description = "Immutable storage-node identity expected in the peer certificate and application protocol.";
      };
      endpoint = mkOption {
        type = types.str;
        description = "Private HTTPS endpoint for this storage node.";
        example = "https://storage-01.aglnet:9443";
      };
      displayName = mkOption {
        type = types.str;
        description = "Operator-facing immutable storage-node display name.";
      };
      failureDomain = mkOption {
        type = types.str;
        description = "Failure domain used to prevent unsafe co-placement.";
      };
      residencyKey = mkOption {
        type = types.str;
        description = "Residency policy key accepted by this node.";
      };
      placementWeight = mkOption {
        type = types.ints.positive;
        default = 100;
      };
      artifactKinds = mkOption {
        type = types.listOf (
          types.enum [
            "anonymized_video"
            "processed_report"
            "video_hls"
            "streamable_video"
            "sidecar"
            "manifest"
          ]
        );
        description = "Processed artifact kinds this node is authorized to store.";
      };
      caCertificateFile = mkOption {
        type = types.str;
        description = "Root-owned CA bundle used to authenticate this storage node.";
      };
      clientCertificateFile = mkOption {
        type = types.str;
        description = "Root-owned hub client certificate presented to this storage node.";
      };
      clientKeyFile = mkOption {
        type = types.str;
        description = "Root-owned hub client key presented to this storage node.";
      };
      recipientPublicKeyFile = mkOption {
        type = types.str;
        description = "X25519 PEM public recipient key used by the hub to wrap per-transfer data-encryption keys for this node.";
      };
    };
  });

  nodeEnvironmentFile = "/run/lx-annotate-hub-storage-node/environment";
  hubEnvironmentFile = "/run/lx-annotate-hub-storage-client/environment";
  hubNodesFile = "/run/lx-annotate-hub-storage-client/nodes.json";
  hubNodesJson = pkgs.writeText "lx-annotate-hub-storage-nodes.json" (
    builtins.toJSON {
      schema_version = 1;
      deployment_role = "central_hub";
      nodes = map (node: {
        node_key = node.identity;
        display_name = node.displayName;
        failure_domain = node.failureDomain;
        residency_key = node.residencyKey;
        placement_weight = node.placementWeight;
        artifact_kinds = node.artifactKinds;
        inherit (node) endpoint;
        ca_certificate_file = node.caCertificateFile;
        client_certificate_file = node.clientCertificateFile;
        client_key_file = node.clientKeyFile;
        recipient_public_key_file = node.recipientPublicKeyFile;
      }) hubCfg.nodes;
    }
  );

  privateHubEndpoint =
    endpoint:
    builtins.match "^https://((10\\.[0-9.]+)|(192\\.168\\.[0-9.]+)|(172\\.(1[6-9]|2[0-9]|3[01])\\.[0-9.]+)|([A-Za-z0-9-]+\\.)+(intern|internal|aglnet)):[0-9]+/?$" endpoint
    != null;

  nodeContractScript = pkgs.writeShellScript "lx-annotate-hub-storage-node-contract" ''
    set -euo pipefail

    mount_point=${escapeShellArg nodeCfg.storage.mountPoint}
    encrypted_device=${escapeShellArg nodeCfg.storage.encryptedDevice}

    if ! ${pkgs.util-linux}/bin/mountpoint -q "$mount_point"; then
      echo "ERROR: protected storage is not mounted at $mount_point" >&2
      exit 1
    fi
    if ! ${pkgs.cryptsetup}/bin/cryptsetup status "$encrypted_device" >/dev/null 2>&1; then
      echo "ERROR: encrypted storage device is not active: $encrypted_device" >&2
      exit 1
    fi
    mount_source="$(${pkgs.util-linux}/bin/findmnt -nro SOURCE --target "$mount_point")"
    mount_device="''${mount_source%%\[*}"
    if [ "$(${pkgs.coreutils}/bin/readlink -f "$mount_device")" != "$(${pkgs.coreutils}/bin/readlink -f "$encrypted_device")" ]; then
      echo "ERROR: protected storage mount is not backed by the configured encrypted device" >&2
      exit 1
    fi

    for required_file in \
      ${escapeShellArg nodeCfg.tls.caCertificateFile} \
      ${escapeShellArg nodeCfg.tls.certificateFile} \
      ${escapeShellArg nodeCfg.tls.keyFile} \
      ${concatMapStringsSep " " escapeShellArg nodeRecipientPrivateIdentityFiles}; do
      if [ ! -s "$required_file" ]; then
        echo "ERROR: required storage-node identity file is absent or empty: $required_file" >&2
        exit 1
      fi
    done

    for private_file in \
      ${escapeShellArg nodeCfg.tls.keyFile} \
      ${concatMapStringsSep " " escapeShellArg nodeRecipientPrivateIdentityFiles}; do
      if [ "$(${pkgs.coreutils}/bin/stat -c %U "$private_file")" != "root" ] \
        || [ "$(${pkgs.coreutils}/bin/stat -c %G "$private_file")" != ${escapeShellArg nodeCfg.service.group} ] \
        || ! ${pkgs.findutils}/bin/find "$private_file" -maxdepth 0 -perm -0040 -print -quit | ${pkgs.gnugrep}/bin/grep -q . \
        || ${pkgs.findutils}/bin/find "$private_file" -maxdepth 0 -perm /0007 -print -quit | ${pkgs.gnugrep}/bin/grep -q .; then
        echo "ERROR: private identity material must be root-owned, group-readable by the service, and inaccessible to other users: $private_file" >&2
        exit 1
      fi
    done

    used_percent="$(${pkgs.coreutils}/bin/df --output=pcent "$mount_point" | ${pkgs.coreutils}/bin/tail -n 1 | ${pkgs.coreutils}/bin/tr -cd '0-9')"
    if [ -z "$used_percent" ] || [ "$used_percent" -ge ${toString nodeCfg.capacity.stopPercent} ]; then
      echo "ERROR: protected storage has reached the admission stop threshold" >&2
      exit 1
    fi

    ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g ${escapeShellArg nodeCfg.service.group} /run/lx-annotate-hub-storage-node
    environment_tmp="$(${pkgs.coreutils}/bin/mktemp /run/lx-annotate-hub-storage-node/environment.XXXXXX)"
    ${pkgs.coreutils}/bin/chown root:${escapeShellArg nodeCfg.service.group} "$environment_tmp"
    ${pkgs.coreutils}/bin/chmod 0640 "$environment_tmp"
    ${pkgs.coreutils}/bin/printf '%s\n' \
      ${escapeShellArg "HUB_STORAGE_SCHEMA_VERSION=1"} \
      ${escapeShellArg "HUB_STORAGE_DEPLOYMENT_ROLE=storage_node"} \
      ${escapeShellArg "HUB_STORAGE_NODE_ID=${nodeCfg.identity}"} \
      ${escapeShellArg "HUB_STORAGE_ROOT=${nodeCfg.storage.mountPoint}"} \
      ${escapeShellArg "HUB_STORAGE_ENCRYPTED_DEVICE=${nodeCfg.storage.encryptedDevice}"} \
      ${escapeShellArg "HUB_STORAGE_LISTEN_ADDRESS=${nodeCfg.network.listenAddress}"} \
      ${escapeShellArg "HUB_STORAGE_PORT=${toString nodeCfg.network.port}"} \
      ${escapeShellArg "HUB_STORAGE_ALLOWED_HUB_ADDRESSES=${concatStringsSep "," nodeCfg.network.allowedHubAddresses}"} \
      ${escapeShellArg "HUB_STORAGE_ALLOWED_HUB_IDENTITIES=${concatStringsSep "," nodeCfg.network.allowedHubIdentities}"} \
      ${escapeShellArg "HUB_STORAGE_HUB_IDENTITY_OPERATIONS=${builtins.toJSON nodeCfg.network.hubIdentityOperations}"} \
      ${escapeShellArg "HUB_STORAGE_TLS_CA_FILE=${nodeCfg.tls.caCertificateFile}"} \
      ${escapeShellArg "HUB_STORAGE_TLS_CERT_FILE=${nodeCfg.tls.certificateFile}"} \
      ${escapeShellArg "HUB_STORAGE_TLS_KEY_FILE=${nodeCfg.tls.keyFile}"} \
      ${escapeShellArg "HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILE=${nodeCfg.recipientPrivateIdentityFile}"} \
      ${escapeShellArg "HUB_STORAGE_RECIPIENT_PRIVATE_IDENTITY_FILES=${concatStringsSep "," nodeRecipientPrivateIdentityFiles}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_WARNING_PERCENT=${toString nodeCfg.capacity.warningPercent}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_STOP_PERCENT=${toString nodeCfg.capacity.stopPercent}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_RECOVERY_PERCENT=${toString nodeCfg.capacity.recoveryPercent}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_RESERVE_BYTES=${toString nodeCfg.capacity.reserveBytes}"} \
      ${escapeShellArg "HUB_STORAGE_MAX_OBJECT_BYTES=${toString nodeCfg.capacity.maxObjectBytes}"} \
      ${escapeShellArg "HUB_STORAGE_MAX_CONCURRENT_REQUESTS=${toString nodeCfg.service.maxConcurrentRequests}"} \
      ${escapeShellArg "HUB_STORAGE_REQUEST_TIMEOUT_SECONDS=${toString nodeCfg.service.requestTimeoutSeconds}"} \
      > "$environment_tmp"
    ${pkgs.coreutils}/bin/mv -f "$environment_tmp" ${escapeShellArg nodeEnvironmentFile}
  '';

  hubContractScript = pkgs.writeShellScript "lx-annotate-hub-storage-client-contract" ''
    set -euo pipefail

    ${concatMapStringsSep "\n" (storageNode: ''
      for required_file in \
        ${escapeShellArg storageNode.caCertificateFile} \
        ${escapeShellArg storageNode.clientCertificateFile} \
        ${escapeShellArg storageNode.clientKeyFile} \
        ${escapeShellArg storageNode.recipientPublicKeyFile}; do
        if [ ! -s "$required_file" ]; then
          echo "ERROR: required hub credential for ${storageNode.identity} is absent or empty: $required_file" >&2
          exit 1
        fi
      done
      if [ "$(${pkgs.coreutils}/bin/stat -c %U ${escapeShellArg storageNode.clientKeyFile})" != "root" ] \
        || [ "$(${pkgs.coreutils}/bin/stat -c %G ${escapeShellArg storageNode.clientKeyFile})" != ${escapeShellArg hubCfg.serviceGroup} ] \
        || ! ${pkgs.findutils}/bin/find ${escapeShellArg storageNode.clientKeyFile} -maxdepth 0 -perm -0040 -print -quit | ${pkgs.gnugrep}/bin/grep -q . \
        || ${pkgs.findutils}/bin/find ${escapeShellArg storageNode.clientKeyFile} -maxdepth 0 -perm /0007 -print -quit | ${pkgs.gnugrep}/bin/grep -q .; then
        echo "ERROR: hub client key for ${storageNode.identity} must be root-owned, group-readable by ${hubCfg.serviceGroup}, and inaccessible to other users" >&2
        exit 1
      fi
    '') hubCfg.nodes}

    ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g ${escapeShellArg hubCfg.serviceGroup} /run/lx-annotate-hub-storage-client
    ${pkgs.coreutils}/bin/install -d -m 0700 -o ${escapeShellArg hubCfg.serviceUser} -g ${escapeShellArg hubCfg.serviceGroup} ${escapeShellArg hubCfg.balancing.stagingDirectory}
    ${pkgs.coreutils}/bin/install -m 0640 -o root -g ${escapeShellArg hubCfg.serviceGroup} ${hubNodesJson} ${hubNodesFile}
    environment_tmp="$(${pkgs.coreutils}/bin/mktemp /run/lx-annotate-hub-storage-client/environment.XXXXXX)"
    ${pkgs.coreutils}/bin/chown root:${escapeShellArg hubCfg.serviceGroup} "$environment_tmp"
    ${pkgs.coreutils}/bin/chmod 0640 "$environment_tmp"
    ${pkgs.coreutils}/bin/printf '%s\n' \
      ${escapeShellArg "HUB_STORAGE_SCHEMA_VERSION=1"} \
      ${escapeShellArg "HUB_STORAGE_DEPLOYMENT_ROLE=central_hub"} \
      ${escapeShellArg "HUB_STORAGE_NODES_FILE=${hubNodesFile}"} \
      ${escapeShellArg "ENDOREG_ENABLE_HUB_TRANSFERS=1"} \
      ${escapeShellArg "ENDOREG_ENABLE_STORAGE_BALANCING=${if hubCfg.balancing.enable then "1" else "0"}"} \
      ${escapeShellArg "ENDOREG_STORAGE_RESIDENCY_KEY=${hubCfg.balancing.residencyKey}"} \
      ${escapeShellArg "HUB_STORAGE_STAGING_DIRECTORY=${hubCfg.balancing.stagingDirectory}"} \
      ${escapeShellArg "HUB_STORAGE_POLICY_VERSION=${hubCfg.balancing.policyVersion}"} \
      ${escapeShellArg "HUB_STORAGE_TELEMETRY_MAX_AGE_SECONDS=${toString hubCfg.balancing.telemetryMaxAgeSeconds}"} \
      ${escapeShellArg "HUB_STORAGE_SAFETY_MARGIN_BYTES=${toString hubCfg.balancing.safetyMarginBytes}"} \
      ${escapeShellArg "HUB_STORAGE_RESERVATION_TTL_SECONDS=${toString hubCfg.balancing.reservationTtlSeconds}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_PRESSURE_BASIS_POINTS=${toString hubCfg.balancing.capacityPressureBasisPoints}"} \
      ${escapeShellArg "HUB_STORAGE_CAPACITY_TARGET_BASIS_POINTS=${toString hubCfg.balancing.capacityTargetBasisPoints}"} \
      ${escapeShellArg "HUB_STORAGE_MINIMUM_FILESYSTEM_HEADROOM_BYTES=${toString hubCfg.balancing.minimumFilesystemHeadroomBytes}"} \
      ${escapeShellArg "HUB_STORAGE_MAX_WORK_ITEMS=${toString hubCfg.balancing.maxWorkItems}"} \
      > "$environment_tmp"
    ${pkgs.coreutils}/bin/mv -f "$environment_tmp" ${escapeShellArg hubEnvironmentFile}
  '';
in
{
  options.services.luxnix.hubStorage = {
    node = {
      enable = mkEnableOption "the LX-Annotate protected storage-node data plane";
      identity = mkOption {
        type = types.str;
        default = "";
        description = "Immutable identity for this storage node.";
      };
      storage = {
        mountPoint = mkOption {
          type = types.str;
          default = "/mnt/lx-annotate-storage";
          description = "Dedicated persistent encrypted filesystem; the service never falls back to root storage.";
        };
        encryptedDevice = mkOption {
          type = types.str;
          default = "";
          example = "/dev/mapper/lx-annotate-storage";
          description = "Active dm-crypt/LUKS mapping backing mountPoint.";
        };
      };
      network = {
        listenAddress = mkOption {
          type = types.str;
          default = "127.0.0.1";
          description = "Private address on which the storage-node application listens.";
        };
        port = mkOption {
          type = types.port;
          default = 9443;
          description = "Mutually authenticated HTTPS storage-node port.";
        };
        interface = mkOption {
          type = types.addCheck types.str (value: builtins.match "^[A-Za-z0-9_.-]+$" value != null);
          default = "";
          example = "tun0";
          description = "Private/VPN firewall interface on which the service port is reachable.";
        };
        allowedHubAddresses = mkOption {
          type = types.listOf (
            types.addCheck types.str (value: builtins.match "^([0-9]{1,3}\\.){3}[0-9]{1,3}$" value != null)
          );
          default = [ ];
          description = "Hub source addresses authorized by the storage-node application in addition to mTLS identity checks.";
        };
        allowedHubIdentities = mkOption {
          type = types.listOf (
            types.addCheck types.str (value: value != "" && builtins.match "^[^,]{1,253}$" value != null)
          );
          default = [ ];
          example = [ "spiffe://endoreg/hub/primary" ];
          description = "Exact DNS or URI subjectAltName values authorized in hub mTLS client certificates; certificate common names are never used.";
        };
        hubIdentityOperations = mkOption {
          type = types.attrsOf (
            types.listOf (
              types.enum [
                "health"
                "capacity"
                "inventory"
                "store"
                "fetch_ciphertext"
                "fetch_plaintext"
                "verify"
                "delete"
              ]
            )
          );
          default = { };
          example = {
            "spiffe://endoreg/hub/primary" = [
              "health"
              "capacity"
              "inventory"
              "store"
              "fetch_plaintext"
              "verify"
              "delete"
            ];
          };
          description = "Least-privilege storage operations authorized for each exact hub certificate SAN.";
        };
      };
      tls = {
        caCertificateFile = mkOption {
          type = types.str;
          default = "";
        };
        certificateFile = mkOption {
          type = types.str;
          default = "";
        };
        keyFile = mkOption {
          type = types.str;
          default = "";
        };
      };
      recipientPrivateIdentityFile = mkOption {
        type = types.str;
        default = "";
        description = "Root-owned X25519 PEM private recipient identity used only to unwrap per-transfer data-encryption keys; never an application master key.";
      };
      recipientPrivateIdentityFiles = mkOption {
        type = types.listOf types.str;
        default = [ ];
        description = "Current and retiring root-owned X25519 private identities accepted during an envelope-key rotation window.";
      };
      capacity = {
        warningPercent = mkOption {
          type = types.ints.between 1 99;
          default = 75;
        };
        stopPercent = mkOption {
          type = types.ints.between 2 100;
          default = 90;
        };
        recoveryPercent = mkOption {
          type = types.ints.between 0 98;
          default = 70;
        };
        reserveBytes = mkOption {
          type = types.ints.positive;
          default = 10737418240;
        };
        maxObjectBytes = mkOption {
          type = types.ints.positive;
          default = 1099511627776;
          description = "Hard per-request ciphertext size limit enforced before accepting a request body.";
        };
      };
      service = {
        command = mkOption {
          type = types.str;
          default = "${storageNodePackage}/bin/lx-hub-storage-node";
          description = "Absolute packaged storage data-plane command; may be overridden by a reviewed application package.";
        };
        user = mkOption {
          type = types.str;
          default = "lx-storage-node";
        };
        group = mkOption {
          type = types.str;
          default = "lx-storage-node";
        };
        maxConcurrentRequests = mkOption {
          type = types.ints.between 1 256;
          default = 16;
          description = "Maximum concurrent accepted storage-node requests.";
        };
        requestTimeoutSeconds = mkOption {
          type = types.ints.between 1 3600;
          default = 120;
          description = "Per-connection storage request read/write timeout.";
        };
      };
      janitor = {
        minimumAgeSeconds = mkOption {
          type = types.ints.positive;
          default = 86400;
        };
        maxEntries = mkOption {
          type = types.ints.positive;
          default = 10000;
          description = "Maximum filesystem entries inspected by one janitor run.";
        };
      };
    };

    hubClient = {
      enable = mkEnableOption "the central-hub storage-node client contract";
      nodes = mkOption {
        type = types.listOf storageNodeType;
        default = [ ];
        description = "Authorized protected storage nodes. No implicit local fallback is provided.";
      };
      serviceGroup = mkOption {
        type = types.str;
        default = "endoreg-service";
        description = "Group allowed to read the generated non-secret node contract and credential path environment.";
      };
      serviceUser = mkOption {
        type = types.str;
        default = "endoreg-service-user";
        description = "LX-Annotate service user owning plaintext envelope staging.";
      };
      balancing = {
        enable = mkEnableOption "scheduled storage placement, rotation, and cleanup workers";
        residencyKey = mkOption {
          type = types.str;
          default = "";
          description = "Residency policy applied to automatic processed-media publication; an empty value leaves publication fail-closed without affecting existing services.";
        };
        stagingDirectory = mkOption {
          type = types.str;
          default = "/var/lib/lx-annotate/hub-storage-staging";
        };
        policyVersion = mkOption {
          type = types.str;
          default = "hub-storage-policy-v1";
        };
        telemetryMaxAgeSeconds = mkOption {
          type = types.ints.positive;
          default = 120;
        };
        safetyMarginBytes = mkOption {
          type = types.ints.positive;
          default = 10737418240;
        };
        reservationTtlSeconds = mkOption {
          type = types.ints.positive;
          default = 900;
        };
        capacityPressureBasisPoints = mkOption {
          type = types.ints.between 1 10000;
          default = 8500;
        };
        capacityTargetBasisPoints = mkOption {
          type = types.ints.between 1 9999;
          default = 7000;
        };
        minimumFilesystemHeadroomBytes = mkOption {
          type = types.ints.positive;
          default = 10737418240;
        };
        maxWorkItems = mkOption {
          type = types.ints.positive;
          default = 2;
        };
      };
    };
  };

  config = mkMerge [
    (mkIf nodeCfg.enable {
      assertions = [
        {
          assertion = nodeCfg.identity != "";
          message = "hubStorage.node.identity must be set";
        }
        {
          assertion = nodeCfg.storage.encryptedDevice != "";
          message = "hubStorage.node.storage.encryptedDevice must be set";
        }
        {
          assertion = nodeCfg.network.interface != "";
          message = "hubStorage.node.network.interface must name a private interface";
        }
        {
          assertion = nodeCfg.network.listenAddress != "0.0.0.0" && nodeCfg.network.listenAddress != "::";
          message = "hubStorage.node must not bind a wildcard/public address";
        }
        {
          assertion = nodeCfg.network.allowedHubAddresses != [ ];
          message = "hubStorage.node.network.allowedHubAddresses must not be empty";
        }
        {
          assertion = nodeCfg.network.allowedHubIdentities != [ ];
          message = "hubStorage.node.network.allowedHubIdentities must not be empty";
        }
        {
          assertion =
            builtins.sort builtins.lessThan (attrNames nodeCfg.network.hubIdentityOperations)
            == builtins.sort builtins.lessThan nodeCfg.network.allowedHubIdentities
            && all (operations: operations != [ ]) (builtins.attrValues nodeCfg.network.hubIdentityOperations);
          message = "hubStorage.node.network.hubIdentityOperations must authorize every allowed hub identity and no others";
        }
        {
          assertion =
            nodeCfg.tls.caCertificateFile != ""
            && nodeCfg.tls.certificateFile != ""
            && nodeCfg.tls.keyFile != "";
          message = "hubStorage.node requires CA, certificate, and key paths for mTLS";
        }
        {
          assertion = nodeRecipientPrivateIdentityFiles != [ ];
          message = "hubStorage.node requires at least one recipient private identity";
        }
        {
          assertion = length nodeRecipientPrivateIdentityFiles <= 3;
          message = "hubStorage.node permits at most three overlapping recipient identities during rotation";
        }
        {
          assertion = all (path: hasPrefix "/" path) (
            [
              nodeCfg.storage.mountPoint
              nodeCfg.storage.encryptedDevice
              nodeCfg.tls.caCertificateFile
              nodeCfg.tls.certificateFile
              nodeCfg.tls.keyFile
            ]
            ++ nodeRecipientPrivateIdentityFiles
          );
          message = "hubStorage.node storage, mTLS, and recipient paths must be absolute";
        }
        {
          assertion =
            nodeCfg.capacity.recoveryPercent < nodeCfg.capacity.warningPercent
            && nodeCfg.capacity.warningPercent < nodeCfg.capacity.stopPercent;
          message = "hubStorage.node capacity thresholds must satisfy recovery < warning < stop";
        }
        {
          assertion = hasPrefix "/" nodeCfg.service.command;
          message = "hubStorage.node.service.command must be an absolute executable path";
        }
      ];

      users.groups.${nodeCfg.service.group} = { };
      users.users.${nodeCfg.service.user} = {
        isSystemUser = true;
        group = nodeCfg.service.group;
      };

      networking.firewall.extraInputRules = ''
        iifname "${nodeCfg.network.interface}" ip saddr { ${concatStringsSep ", " nodeCfg.network.allowedHubAddresses} } tcp dport ${toString nodeCfg.network.port} accept
      '';

      systemd = {
        services = {
          lx-annotate-hub-storage-node-contract = {
            description = "Validate encrypted storage and storage-node identity contract";
            requiredBy = [ "lx-annotate-hub-storage-node.service" ];
            before = [ "lx-annotate-hub-storage-node.service" ];
            unitConfig.RequiresMountsFor = [ nodeCfg.storage.mountPoint ];
            bindsTo = [
              nodeMountUnit
              nodeDeviceUnit
            ];
            after = [
              nodeMountUnit
              nodeDeviceUnit
            ];
            serviceConfig = {
              Type = "oneshot";
              ExecStart = nodeContractScript;
            };
          };

          lx-annotate-hub-storage-node = {
            description = "LX-Annotate protected storage node";
            wantedBy = [ "multi-user.target" ];
            after = [
              "network-online.target"
              nodeMountUnit
              nodeDeviceUnit
              "lx-annotate-hub-storage-node-contract.service"
            ];
            bindsTo = [
              nodeMountUnit
              nodeDeviceUnit
            ];
            requires = [ "lx-annotate-hub-storage-node-contract.service" ];
            wants = [ "network-online.target" ];
            unitConfig.RequiresMountsFor = [ nodeCfg.storage.mountPoint ];
            environment.HUB_STORAGE_ENVIRONMENT_FILE = nodeEnvironmentFile;
            serviceConfig = {
              User = nodeCfg.service.user;
              Group = nodeCfg.service.group;
              EnvironmentFile = nodeEnvironmentFile;
              ExecStart = nodeCfg.service.command;
              Restart = "on-failure";
              NoNewPrivileges = true;
              PrivateTmp = true;
              ProtectHome = true;
              ProtectSystem = "strict";
              PrivateDevices = true;
              ProtectKernelModules = true;
              ProtectKernelTunables = true;
              RestrictAddressFamilies = [
                "AF_UNIX"
                "AF_INET"
                "AF_INET6"
              ];
              ReadWritePaths = [ nodeCfg.storage.mountPoint ];
              UMask = "0077";
            };
          };

          lx-annotate-hub-storage-node-janitor = {
            description = "Reconcile stale storage-node crash artifacts";
            after = [
              nodeMountUnit
              nodeDeviceUnit
              "lx-annotate-hub-storage-node-contract.service"
            ];
            requires = [ "lx-annotate-hub-storage-node-contract.service" ];
            unitConfig.RequiresMountsFor = [ nodeCfg.storage.mountPoint ];
            bindsTo = [
              nodeMountUnit
              nodeDeviceUnit
            ];
            serviceConfig = {
              Type = "oneshot";
              User = nodeCfg.service.user;
              Group = nodeCfg.service.group;
              EnvironmentFile = nodeEnvironmentFile;
              ExecStart = "${nodeCfg.service.command} janitor --minimum-age-seconds ${toString nodeCfg.janitor.minimumAgeSeconds} --max-entries ${toString nodeCfg.janitor.maxEntries}";
              NoNewPrivileges = true;
              PrivateTmp = true;
              ProtectHome = true;
              ProtectSystem = "strict";
              PrivateDevices = true;
              ProtectKernelModules = true;
              ProtectKernelTunables = true;
              RestrictAddressFamilies = [ "AF_UNIX" ];
              ReadWritePaths = [ nodeCfg.storage.mountPoint ];
              UMask = "0077";
            };
          };
        };

        timers.lx-annotate-hub-storage-node-janitor = {
          description = "Daily storage-node crash-artifact reconciliation";
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnCalendar = "daily";
            Persistent = true;
            RandomizedDelaySec = "30m";
            Unit = "lx-annotate-hub-storage-node-janitor.service";
          };
        };
      };
    })

    (mkIf hubCfg.enable {
      assertions = [
        {
          assertion = config.services.luxnix.lxAnnotateLocal.hub.enable;
          message = "hubStorage.hubClient requires lxAnnotateLocal.hub.enable";
        }
        {
          assertion = config.services.luxnix.lxAnnotateLocal.runtime.deploymentRole == "central_hub";
          message = "hubStorage.hubClient is valid only for deploymentRole central_hub";
        }
        {
          assertion = hubCfg.nodes != [ ];
          message = "hubStorage.hubClient.nodes must not be empty";
        }
        {
          assertion = length (unique (map (node: node.identity) hubCfg.nodes)) == length hubCfg.nodes;
          message = "hubStorage.hubClient node identities must be unique";
        }
        {
          assertion = all (
            node:
            node.identity != ""
            && node.displayName != ""
            && node.failureDomain != ""
            && node.residencyKey != ""
            && node.artifactKinds != [ ]
            && length (unique node.artifactKinds) == length node.artifactKinds
            && privateHubEndpoint node.endpoint
          ) hubCfg.nodes;
          message = "every hub storage node needs an identity and a host-only private HTTPS endpoint with an explicit port";
        }
        {
          assertion = all (
            node:
            all (path: hasPrefix "/" path) [
              node.caCertificateFile
              node.clientCertificateFile
              node.clientKeyFile
              node.recipientPublicKeyFile
            ]
          ) hubCfg.nodes;
          message = "hub storage-node credential and recipient paths must be absolute";
        }
        {
          assertion = hasPrefix "/" hubCfg.balancing.stagingDirectory;
          message = "hub storage balancing stagingDirectory must be absolute";
        }
        {
          assertion =
            hubCfg.balancing.capacityTargetBasisPoints < hubCfg.balancing.capacityPressureBasisPoints;
          message = "hub storage balancing capacity target must be lower than pressure";
        }
      ];

      systemd.services = {
        lx-annotate-hub-storage-client-contract = {
          description = "Validate central-hub storage-node identities and credential paths";
          requiredBy = lib.optionals hubCfg.balancing.enable [ "lx-annotate.service" ];
          before = lib.optionals hubCfg.balancing.enable [ "lx-annotate.service" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            ExecStart = hubContractScript;
          };
        };

        lx-annotate = mkMerge [
          {
            environment.ENDOREG_ENABLE_STORAGE_BALANCING = if hubCfg.balancing.enable then "1" else "0";
          }
          (mkIf hubCfg.balancing.enable {
            after = [ "lx-annotate-hub-storage-client-contract.service" ];
            requires = [ "lx-annotate-hub-storage-client-contract.service" ];
            environment.HUB_STORAGE_ENVIRONMENT_FILE = hubEnvironmentFile;
            serviceConfig.EnvironmentFile = lib.mkAfter [ hubEnvironmentFile ];
          })
        ];
        lx-annotate-celery-hub-transfer-worker = mkMerge [
          {
            environment.ENDOREG_ENABLE_STORAGE_BALANCING = if hubCfg.balancing.enable then "1" else "0";
          }
          (mkIf hubCfg.balancing.enable {
            after = [ "lx-annotate-hub-storage-client-contract.service" ];
            requires = [ "lx-annotate-hub-storage-client-contract.service" ];
            serviceConfig.EnvironmentFile = lib.mkAfter [ hubEnvironmentFile ];
          })
        ];
        lx-annotate-celery-beat = mkMerge [
          {
            environment.ENDOREG_ENABLE_STORAGE_BALANCING = if hubCfg.balancing.enable then "1" else "0";
          }
          (mkIf hubCfg.balancing.enable {
            after = [ "lx-annotate-hub-storage-client-contract.service" ];
            requires = [ "lx-annotate-hub-storage-client-contract.service" ];
            serviceConfig.EnvironmentFile = lib.mkAfter [ hubEnvironmentFile ];
          })
        ];
      };
    })
  ];
}
