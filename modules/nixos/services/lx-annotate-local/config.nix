args@{
  config,
  inputs,
  lib,
  pkgs,
  cfg,
  sslCfg,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib)
    mkAfter
    mkBefore
    mkDefault
    mkForce
    mkIf
    mkMerge
    optionalAttrs
    optionalString
    ;

  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-user-home
    endoreg-service-group-name
    ;
  inherit (runtime.paths)
    runtimeRootPath
    repoDir
    runtimeDataRootPath
    runtimeStorageRootPath
    runtimeIoImportRootPath
    runtimeWatcherVideoDirPath
    runtimeWatcherReportDirPath
    runtimeWatcherPreanonymizedDirPath
    runtimeSapImportDirPath
    runtimeSapImportProcessedDirPath
    runtimeSapImportFailedDirPath
    runtimeMoverStagingDirPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeStaticRootPath
    runtimeWheelRootPath
    runtimeWheelVenvPath
    envDataDir
    envConfDir
    sslKeyPath
    sslCertPath
    publicSslCertificatePath
    hubRootPath
    ;
  inherit (runtime.runtime)
    useWheelRuntime
    pythonInterpreter
    wheelFilePath
    packageVersion
    managedEncryptedDataServiceName
    encryptionServiceUnits
    ;
  inherit (runtime.defaults)
    defaultSslCertificatePath
    defaultSslKeyPath
    processedReportDirName
    processedVideoDirName
    ;
  boolString = value: if value then "true" else "false";

  endoregDbSource = inputs.endoreg-db;
  lxAnnotateSource = inputs.lx-annotate;
  endoregDbProject =
    (builtins.fromTOML (builtins.readFile "${endoregDbSource}/pyproject.toml")).project;
  lxAnnotateProject =
    (builtins.fromTOML (builtins.readFile "${lxAnnotateSource}/pyproject.toml")).project;
  endoregDbVersion = endoregDbProject.version;
  lxAnnotateEndoregDbDependencies = builtins.filter (
    dependency: lib.hasPrefix "endoreg-db==" dependency
  ) lxAnnotateProject.dependencies;
  lxAnnotateEndoregDbVersion =
    if builtins.length lxAnnotateEndoregDbDependencies == 1 then
      lib.removePrefix "endoreg-db==" (builtins.head lxAnnotateEndoregDbDependencies)
    else
      null;
  endoregDbRevision = endoregDbSource.rev or "unversioned";
  lxAnnotateRevision = lxAnnotateSource.rev or "unversioned";
  featureRegistryManifest = pkgs.writeText "endoreg-feature-registry-manifest.json" (
    builtins.toJSON {
      schemaVersion = 1;
      validationScope = "schema-policy-location-cross-registry";
      endoregDb = {
        sourceDeclaredVersion = endoregDbVersion;
        revision = endoregDbRevision;
      };
      lxAnnotate = {
        version = lxAnnotateProject.version;
        revision = lxAnnotateRevision;
        runtimeEndoregDbVersion = lxAnnotateEndoregDbVersion;
      };
    }
  );
  featureRegistryPython = pkgs.python312.withPackages (pythonPackages: [
    pythonPackages.django
    pythonPackages.pydantic
    pythonPackages.pyyaml
  ]);
  featureRegistryValidator = pkgs.writeText "validate-endoreg-feature-registry.py" ''
    import runpy
    import sys
    import types
    from pathlib import Path

    tracker_path = sys.argv[1]

    def unavailable_file_mutation(*_args, **_kwargs):
        raise RuntimeError("feature-registry validation attempted a mutating file operation")

    utils_module = types.ModuleType("endoreg_db.utils")
    utils_module.__path__ = []
    filesystem_module = types.ModuleType("endoreg_db.utils.filesystem")
    filesystem_module.__path__ = []
    file_operations_module = types.ModuleType(
        "endoreg_db.utils.filesystem.file_operations"
    )
    for name in (
        "advisory_file_lock",
        "atomic_create_file",
        "atomic_move_file",
        "atomic_write_file",
        "safe_unlink_file",
    ):
        setattr(file_operations_module, name, unavailable_file_mutation)

    sys.modules["endoreg_db.utils"] = utils_module
    sys.modules["endoreg_db.utils.filesystem"] = filesystem_module
    sys.modules["endoreg_db.utils.filesystem.file_operations"] = file_operations_module
    tracker = runpy.run_path(tracker_path, run_name="endoreg_feature_registry")
    tracking_directory = Path(tracker_path).resolve().parent
    policy = tracker["load_policy"](tracking_directory)
    feature_paths = tracker["_feature_paths"](tracking_directory)
    features = tuple(tracker["load_feature_file"](path) for path in feature_paths)
    for path, feature in zip(feature_paths, features, strict=True):
        tracker["_validate_feature_location"](
            feature,
            path=path,
            directory=tracking_directory,
        )
    tracker["_validate_registry"](
        policy,
        features,
        source_exists=lambda _source: True,
    )
    print(
        f"OK: {len(features)} feature definitions passed immutable schema, "
        "policy, location, and cross-registry validation."
    )
  '';
  endoregFeatureRegistry = pkgs.runCommand "endoreg-feature-registry-${endoregDbVersion}" { } ''
    export PYTHONPATH=${endoregDbSource}
    ${featureRegistryPython}/bin/python ${featureRegistryValidator} \
      ${endoregDbSource}/feature-tracking/tracker.py

    registry_root="$out/share/endoreg-feature-registry"
    mkdir -p "$registry_root"
    cp -R ${endoregDbSource}/feature-tracking/. "$registry_root/"
    cp ${featureRegistryManifest} "$registry_root/manifest.json"
  '';
  featureRegistryPath = "${endoregFeatureRegistry}/share/endoreg-feature-registry";
  featureRegistryGuardUnit = "lx-annotate-feature-registry-guard.service";

  hubTransferProxyExtraConfig = ''
    # The shared virtual host also serves browser traffic, so client
    # certificates are requested at server scope and enforced only here.
    # Reject before reading or proxying a transfer request body.
    if ($ssl_client_verify != SUCCESS) {
      return 403;
    }

    proxy_http_version 1.1;

    # Stream large multipart uploads to Django instead of buffering the
    # complete file in Nginx temporary storage.
    proxy_request_buffering off;
    proxy_buffering off;

    # A processed video transfer may take considerably longer than an
    # ordinary browser/API request.
    proxy_connect_timeout 60s;
    proxy_read_timeout 21600s;
    proxy_send_timeout 21600s;
    send_timeout 21600s;

    # Explicit reverse-proxy contract used by Django.
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Real-IP $remote_addr;

    # Never trust an incoming value for this header. Replace it with the
    # result of Nginx client-certificate verification.
    proxy_set_header X-Client-Cert-Verified $ssl_client_verify;
  '';

  streamableExternalStorageRoot = cfg.runtime.streamableServing.externalStorageRoot;
  streamableExternalStorageEnabled = streamableExternalStorageRoot != null;
  videoStreamProxyExtraConfig = ''
    proxy_set_header Range $http_range;
    proxy_set_header If-Range $http_if_range;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
  '';
  wheelhousePath =
    if cfg.runtime.wheelhousePath == null then "" else toString cfg.runtime.wheelhousePath;
  wheelDependencyOverrides = cfg.runtime.wheelDependencyOverrides;
  wheelDependencyOverrideArgs = lib.concatStringsSep " " wheelDependencyOverrides;
  wheelDependencyOverrideHash = builtins.hashString "sha256" (
    lib.concatStringsSep "\n" wheelDependencyOverrides
  );
  terminologyRegistryPath = cfg.runtime.terminology.registryPath;
  terminologyRegistryDir = builtins.dirOf terminologyRegistryPath;
  terminologyImportRoot = cfg.runtime.terminology.importRoot;
  terminologyInitialBundle = cfg.runtime.terminology.initialBundle;
  terminologyPathStaysInsideEncryptedData =
    path:
    lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" path
    && lib.all (segment: segment != "." && segment != "..") (lib.splitString "/" path);
  terminologyInitialBundleArgs =
    if terminologyInitialBundle == null then
      ""
    else
      lib.escapeShellArgs (
        [
          "--module"
          terminologyInitialBundle.moduleName
          "--version"
          terminologyInitialBundle.version
          "--input-dir"
          (toString terminologyInitialBundle.inputDirectory)
        ]
        ++ lib.optionals (terminologyInitialBundle.medicalField != null) [
          "--medical-field"
          terminologyInitialBundle.medicalField
        ]
        ++ [ "--activate" ]
      );
  wheelRuntimePackage = pkgs.runCommand "lx-annotate-wheel-runtime-${packageVersion}" { } ''
    mkdir -p "$out/bin" "$out/libexec" "$out/share/lx-annotate"
    ln -s ${lib.escapeShellArg runtimeStaticRootPath} "$out/share/lx-annotate/staticfiles"

    cat > "$out/libexec/lx-annotate-wheel-runtime-lib" <<'EOF'
    set -euo pipefail

    export PATH="${
      lib.makeBinPath [
        pkgs.coreutils
        pkgs.findutils
        pkgs.gnused
        pkgs.rsync
        pkgs.util-linux
      ]
    }:''${PATH:-}"

    lx_annotate_wheel_read_required_secret() {
      local path="$1"
      local label="$2"
      local value=""

      if [ -z "$path" ]; then
        echo "ERROR: $label file path is empty." >&2
        exit 1
      fi
      if [ ! -r "$path" ]; then
        echo "ERROR: Unable to read $label from $path." >&2
        exit 1
      fi

      value="$(tr -d '\r\n' < "$path")"
      if [ -z "$value" ]; then
        echo "ERROR: $label file is empty: $path" >&2
        exit 1
      fi

      printf '%s' "$value"
    }

    lx_annotate_wheel_read_keycloak_secret() {
      local path="$1"
      local line=""
      local value=""

      if [ -z "$path" ]; then
        return 0
      fi
      if [ ! -r "$path" ]; then
        echo "ERROR: Unable to read OIDC_RP_CLIENT_SECRET from $path." >&2
        exit 1
      fi

      while IFS= read -r line || [ -n "$line" ]; do
        line="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$line" ] && continue
        case "$line" in
          \#*) continue ;;
          export\ *) line="$(printf '%s' "$line" | sed -E 's/^export[[:space:]]+//')" ;;
        esac
        case "$line" in
          DJANGO_KEYCLOAK_CLIENT_SECRET=*|KEYCLOAK_CLIENT_SECRET=*|OIDC_RP_CLIENT_SECRET=*)
            value="''${line#*=}"
            value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^"//; s/"$//')"
            break
            ;;
        esac
      done < "$path"

      if [ -z "$value" ]; then
        value="$(tr -d '\r\n' < "$path")"
      fi

      printf '%s' "$value"
    }

    lx_annotate_wheel_export_secret_env() {
      local secret_key_file="''${DJANGO_SECRET_KEY_FILE:-}"
      local db_password_file="''${DJANGO_DB_PASSWORD_FILE:-}"
      local keycloak_secret_file="''${DJANGO_KEYCLOAK_CLIENT_SECRET_FILE:-}"

      if [ -z "''${DJANGO_SECRET_KEY:-}" ] && [ -n "$secret_key_file" ]; then
        export DJANGO_SECRET_KEY
        DJANGO_SECRET_KEY="$(lx_annotate_wheel_read_required_secret "$secret_key_file" "DJANGO_SECRET_KEY")"
      fi

      if [ -z "''${DJANGO_DB_PASSWORD:-}" ] && [ -n "$db_password_file" ]; then
        export DJANGO_DB_PASSWORD
        DJANGO_DB_PASSWORD="$(lx_annotate_wheel_read_required_secret "$db_password_file" "DJANGO_DB_PASSWORD")"
      fi
      if [ -n "''${DJANGO_DB_PASSWORD:-}" ]; then
        export DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD"
      fi

      if [ -z "''${OIDC_RP_CLIENT_SECRET:-}" ] && [ -n "$keycloak_secret_file" ]; then
        export OIDC_RP_CLIENT_SECRET
        OIDC_RP_CLIENT_SECRET="$(lx_annotate_wheel_read_keycloak_secret "$keycloak_secret_file")"
      fi
      if [ -n "''${OIDC_RP_CLIENT_SECRET:-}" ]; then
        export DJANGO_KEYCLOAK_CLIENT_SECRET="$OIDC_RP_CLIENT_SECRET"
      fi
    }

    lx_annotate_wheel_ensure() {
      local wheel_path=${lib.escapeShellArg wheelFilePath}
      local wheelhouse_path=${lib.escapeShellArg wheelhousePath}
      local python_bin=${lib.escapeShellArg pythonInterpreter}
      local expected_package_version=${lib.escapeShellArg packageVersion}
      local wheel_hash=""
      local wheelhouse_hash="no-wheelhouse"
      local wheel_dependency_overrides=${lib.escapeShellArg wheelDependencyOverrideArgs}
      local wheel_dependency_overrides_hash=${lib.escapeShellArg wheelDependencyOverrideHash}
      local pip_install_args=""
      local wheel_install_stamp_file=${lib.escapeShellArg "${runtimeRootPath}/.wheel-install.sha256"}
      local wheel_install_lock_file=${lib.escapeShellArg "${runtimeRootPath}/.wheel-install.lock"}
      local installed_hash=""
      local canonical_wheel_name=""
      local staged_wheel_path=""
      local install_hash=""
      local installed_package_version=""
      local wheel_installer_revision="wheel-console-contract-v6-version-verified"
      local venv_created="false"
      local pip_cache_dir=${lib.escapeShellArg "${runtimeRootPath}/pip-cache"}

      if [ -z "$wheel_path" ]; then
        echo "ERROR: services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set in wheel mode." >&2
        exit 1
      fi
      if [ -z "$expected_package_version" ]; then
        echo "ERROR: services.luxnix.lxAnnotateLocal.runtime.packageVersion must be set in wheel mode." >&2
        exit 1
      fi

      install -d -m 0750 \
        ${lib.escapeShellArg runtimeRootPath} \
        ${lib.escapeShellArg runtimeWheelRootPath} \
        ${lib.escapeShellArg runtimeWheelVenvPath} \
        "$pip_cache_dir" \
        ${lib.escapeShellArg envConfDir} \
        ${lib.escapeShellArg envDataDir}
      install -d -m 0775 ${lib.escapeShellArg runtimeStaticRootPath} ${lib.escapeShellArg "${runtimeStaticRootPath}/.vite"}

      wheel_hash="$(sha256sum "$wheel_path" | cut -d ' ' -f1)"
      canonical_wheel_name="$(basename "$wheel_path" | sed -E 's/^[a-z0-9]{32}-//')"
      staged_wheel_path=${lib.escapeShellArg runtimeRootPath}'/'"$canonical_wheel_name"

      if [ -n "$wheelhouse_path" ]; then
        if [ ! -d "$wheelhouse_path" ]; then
          echo "ERROR: Configured runtime.wheelhousePath does not exist: $wheelhouse_path" >&2
          exit 1
        fi
        wheelhouse_hash="$(
          (
            find "$wheelhouse_path" -maxdepth 1 -type f \( -name '*.whl' -o -name '*.tar.gz' -o -name '*.zip' \) -print0 \
              | sort -z \
              | xargs -0 -r sha256sum
          ) | sha256sum | cut -d ' ' -f1
        )"
        pip_install_args="--no-index --find-links $wheelhouse_path"
      fi

      install_hash="$(
        printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
          "$wheel_hash" \
          "$wheelhouse_hash" \
          "$wheel_dependency_overrides_hash" \
          "$python_bin" \
          "$expected_package_version" \
          "$wheel_installer_revision" \
          | sha256sum \
          | cut -d ' ' -f1
      )"

      exec 9>"$wheel_install_lock_file"
      flock 9

      if [ ! -x ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/python"} ]; then
        "$python_bin" -m venv ${lib.escapeShellArg runtimeWheelVenvPath}
        venv_created="true"
      fi

      installed_hash="$(cat "$wheel_install_stamp_file" 2>/dev/null || true)"
      if [ "$venv_created" = "true" ] || [ "$install_hash" != "$installed_hash" ]; then
        install -m 0640 "$wheel_path" "$staged_wheel_path"
        export PIP_CACHE_DIR="$pip_cache_dir"
        export PIP_DISABLE_PIP_VERSION_CHECK=1
        # shellcheck disable=SC2086
        ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/pip"} install --upgrade $pip_install_args "$staged_wheel_path"
        ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/pip"} install --force-reinstall --no-deps "$staged_wheel_path"
        if [ -n "$wheel_dependency_overrides" ]; then
          # shellcheck disable=SC2086
          ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/pip"} install --upgrade --no-deps $pip_install_args $wheel_dependency_overrides
        fi
      fi

      if ! installed_package_version="$(${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/python"} -c 'from importlib.metadata import version; print(version("lx-annotate"))')"; then
        echo "ERROR: Installed wheel does not expose lx-annotate package metadata." >&2
        exit 1
      fi
      if [ "$installed_package_version" != "$expected_package_version" ]; then
        echo "ERROR: Installed lx-annotate version $installed_package_version does not match configured runtime.packageVersion $expected_package_version." >&2
        exit 1
      fi
      if [ "$venv_created" = "true" ] || [ "$install_hash" != "$installed_hash" ]; then
        printf '%s\n' "$install_hash" > "$wheel_install_stamp_file"
        chmod 0640 "$wheel_install_stamp_file" 2>/dev/null || true
      fi

      flock -u 9
      exec 9>&-

      export PATH=${lib.escapeShellArg "${runtimeWheelVenvPath}/bin"}":$PATH"
      export LX_ANNOTATE_WHEEL_VENV=${lib.escapeShellArg runtimeWheelVenvPath}
      export LX_ANNOTATE_WHEEL_APP_ROOT=${lib.escapeShellArg runtimeWheelRootPath}
      export WHEEL_INSTALL_HASH="$install_hash"
    }

    lx_annotate_wheel_sync_static() {
      local package_static_dir=""

      package_static_dir="$(${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/python"} - <<'PY'
    from pathlib import Path
    import lx_annotate

    package_root = Path(lx_annotate.__file__).resolve().parent
    for candidate in (package_root / "staticfiles", package_root / "static"):
        if candidate.exists():
            print(candidate)
            break
    PY
    )"

      if [ -z "$package_static_dir" ] || [ ! -d "$package_static_dir" ]; then
        echo "ERROR: No packaged static assets found in installed lx-annotate wheel." >&2
        exit 1
      fi

      rsync -a --delete "$package_static_dir"/ ${lib.escapeShellArg "${runtimeStaticRootPath}/"}
      if [ ! -f ${lib.escapeShellArg "${runtimeStaticRootPath}/.vite/manifest.json"} ]; then
        echo "ERROR: Installed lx-annotate wheel does not provide .vite/manifest.json." >&2
        exit 1
      fi
      find ${lib.escapeShellArg runtimeStaticRootPath} -type d -exec chmod 0750 {} +
      find ${lib.escapeShellArg runtimeStaticRootPath} -type f -exec chmod 0640 {} +
    }
    EOF
    chmod +x "$out/libexec/lx-annotate-wheel-runtime-lib"

    cat > "$out/bin/lx-annotate-runtime-ensure" <<EOF
    #!${pkgs.bash}/bin/bash
    set -euo pipefail
    source "$out/libexec/lx-annotate-wheel-runtime-lib"
    lx_annotate_wheel_ensure
    EOF
    chmod +x "$out/bin/lx-annotate-runtime-ensure"

    make_entrypoint() {
      local name="$1"
      local target="$2"
      local sync_static="$3"
      cat > "$out/bin/$name" <<EOF
    #!${pkgs.bash}/bin/bash
    set -euo pipefail
    source "$out/libexec/lx-annotate-wheel-runtime-lib"
    lx_annotate_wheel_ensure
    lx_annotate_wheel_export_secret_env
    if [ "$sync_static" = "1" ]; then
      lx_annotate_wheel_sync_static
    fi
    if [ ! -x ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin"}/"$target" ]; then
      echo "ERROR: Installed lx-annotate wheel does not expose console script: $target" >&2
      exit 1
    fi
    exec ${lib.escapeShellArg "${runtimeWheelVenvPath}/bin"}/"$target" "\$@"
    EOF
      chmod +x "$out/bin/$name"
    }

    make_entrypoint lx-annotate-web lx-annotate-web 1
    make_entrypoint lx-annotate-server lx-annotate-web 1
    make_entrypoint lx-annotate-manage lx-annotate-manage 0
    make_entrypoint lx-annotate-migrate lx-annotate-migrate 0
    make_entrypoint lx-annotate-load-base-data lx-annotate-load-base-data 0
    make_entrypoint lx-annotate-worker lx-annotate-worker 0
    make_entrypoint lx-annotate-celery lx-annotate-celery 0
    make_entrypoint lx-annotate-watch lx-annotate-watch 0
    make_entrypoint lx-annotate-export-frames lx-annotate-export-frames 0
    make_entrypoint lx-annotate-import-sap lx-annotate-import-sap 0
    make_entrypoint lx-dtypes-kb-registry lx-dtypes-kb-registry 0
    make_entrypoint lx-dtypes-prototype-kb-smoke lx-dtypes-prototype-kb-smoke 0
  '';
  effectiveRuntimePackage = if useWheelRuntime then wheelRuntimePackage else cfg.runtime.package;
  effectivePackageVersion =
    if useWheelRuntime then
      packageVersion
    else
      cfg.runtime.package.version or cfg.runtime.packageVersion;
  packageStaticRoot =
    if useWheelRuntime then
      runtimeStaticRootPath
    else
      "${cfg.runtime.package}/share/lx-annotate/staticfiles";
  envSystemdFilePath = "${runtimeRootPath}/.env.systemd";
  ffmpegStreamThrottleWorkerUnit = "lx-annotate-celery-ffmpeg-worker.service";
  ffmpegStreamThrottleStateFile = "/run/lx-annotate/ffmpeg-stream-throttle.state";
  ffmpegStreamThrottleNormalProfile = {
    cpuQuota =
      if cfg.runtime.ffmpegStreamThrottle.normal.cpuQuota == null then
        cfg.runtime.workerPools.ffmpeg.cpuQuota
      else
        cfg.runtime.ffmpegStreamThrottle.normal.cpuQuota;
    cpuWeight =
      if cfg.runtime.ffmpegStreamThrottle.normal.cpuWeight == null then
        cfg.runtime.workerPools.ffmpeg.cpuWeight
      else
        cfg.runtime.ffmpegStreamThrottle.normal.cpuWeight;
    ioWeight = cfg.runtime.ffmpegStreamThrottle.normal.ioWeight;
  };

  vaultClientHubPkiEnabled = lib.attrByPath [
    "luxnix"
    "vault"
    "client"
    "hubPki"
    "enable"
  ] false config;
  externalPostgresConfigured = cfg.runtime.externalServices.postgresHost != null;
  externalRedisConfigured = cfg.runtime.externalServices.redisUrl != null;
  localPostgresSetupUnits = lib.optionals (!externalPostgresConfigured) [
    "postgres-endoreg-setup.service"
  ];
  localPostgresServiceUnits = lib.optionals (!externalPostgresConfigured) [ "postgresql.service" ];
  localRedisServiceUnits = lib.optionals (!externalRedisConfigured) [ "redis-lx-annotate.service" ];
  dataRecoveryServiceUnits = lib.optionals cfg.dataRecovery.enable [
    "lx-annotate-data-recovery.service"
  ];
  hlsBackfillServiceUnits = lib.optionals cfg.hlsBackfill.enable [
    "lx-annotate-hls-backfill.service"
  ];
  hubNodeProvisioningServiceUnits = lib.optionals cfg.hub.nodeProvisioning.enable [
    "lx-annotate-hub-node-provisioning.service"
  ];
  managedSecretsSetupUnits =
    lib.optionals (lib.attrByPath [ "roles" "managed-secrets" "enable" ] false config)
      [
        "managed-secrets-setup.service"
      ];

  isLocalPostgresHost =
    host: host == "localhost" || host == "127.0.0.1" || host == "::1" || host == cfg.django.hostname;
  isLocalRedisUrl =
    url:
    url != null
    && (lib.hasInfix "localhost" url || lib.hasInfix "127.0.0.1" url || lib.hasInfix "[::1]" url);
  brokerUrlUsesSecureTransport =
    url: url != null && (lib.hasPrefix "rediss:" url || lib.hasPrefix "amqps:" url);
  runtimeLibraryPackages = [
    pkgs.stdenv.cc.cc.lib
    pkgs.libglvnd
    pkgs.zlib
    pkgs.glib
    pkgs.libxcb
  ];
  # CUDA/NVENC load the real host driver from NixOS' OpenGL driver profile.
  runtimeHostDriverLibraryPaths = [
    "/run/opengl-driver/lib"
    "/run/opengl-driver-32/lib"
  ];
  runtimeLdLibraryPath = lib.concatStringsSep ":" (
    runtimeHostDriverLibraryPaths
    ++ [
      (lib.makeLibraryPath (runtimeLibraryPackages ++ [ pkgs.ffmpeg ]))
    ]
  );
  envContract = import ./scripts/env.nix (
    args
    // {
      inherit
        effectivePackageVersion
        packageStaticRoot
        runtimeLdLibraryPath
        ;
    }
  );
  inherit (envContract)
    celeryBrokerUrl
    celeryWorkerResourceEnv
    commonEnv
    llmInferenceWorkerEnv
    ;
  hubOidcMiddlewarePolicy = pkgs.writeTextDir "sitecustomize.py" ''
    import importlib.util
    import json
    import os
    import sys

    if importlib.util.find_spec("endoreg_db") is not None:
        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE",
            "lx_annotate.settings.settings_prod",
        )
        from endoreg_db.authz import middleware

        hub_transfer_prefix = "/api/media/hub/transfers/"
        public_prefixes = getattr(middleware, "PUBLIC_PREFIXES", None)
        if not isinstance(public_prefixes, tuple):
            raise RuntimeError("endoreg_db OIDC middleware PUBLIC_PREFIXES contract is unavailable")
        if hub_transfer_prefix not in public_prefixes:
            middleware.PUBLIC_PREFIXES = (*public_prefixes, hub_transfer_prefix)
        print(json.dumps({
            "event": "hub.oidc_middleware_policy_installed",
            "path_prefix": hub_transfer_prefix,
        }, sort_keys=True), file=sys.stderr)
  '';
  commonExtraEnv =
    commonEnv
    // {
      ENDOREG_FEATURE_REGISTRY_PATH = featureRegistryPath;
      ENDOREG_FEATURE_REGISTRY_REVISION = endoregDbRevision;
      ENDOREG_FEATURE_REGISTRY_SOURCE_VERSION = endoregDbVersion;
      ENDOREG_RUNTIME_ENDOREG_DB_VERSION = lxAnnotateEndoregDbVersion;
    }
    // lib.optionalAttrs cfg.hub.transferApi.enable {
      PYTHONPATH = toString hubOidcMiddlewarePolicy;
    };

  encryptedDataMountUnitConfig = {
    RequiresMountsFor = [
      envDataDir
    ]
    ++ lib.optional streamableExternalStorageEnabled runtimeStreamableVideoRootPath;
  };
  appReadWritePaths = [
    endoreg-service-user-home
    envDataDir
    envConfDir
    runtimeRootPath
    runtimeStaticRootPath
    runtimeWheelRootPath
    runtimeWheelVenvPath
    cfg.runtime.modelTrainingStagingRoot
    "/var/endoreg-service-user/lx-annotate"
  ];

  serviceUserIoAccessLinkPath = "${endoreg-service-user-home}/lx-annotate-io";
  desktopPreanonymizedLinkTarget = "${serviceUserIoAccessLinkPath}/preanonymized_import";
  desktopSapImportLinkTarget = "${serviceUserIoAccessLinkPath}/sap_import";

  lxAnnotateTranscodeVideoCommand = "${effectiveRuntimePackage}/bin/lx-annotate-manage transcode_video";
  lxAnnotateFileMoverTranscodeCommand = "${lxAnnotateTranscodeVideoCommand} --input-dir \"$1\" --filename \"$2\" --output-dir \"$3\" --overwrite --json";
  lxAnnotateFileMoverTranscodeEnv = ''
    ${envContract.commonShellExportText}
    export LD_LIBRARY_PATH="${runtimeLdLibraryPath}:''${LD_LIBRARY_PATH:-}"
  '';

  hubNodeProvisioningData = pkgs.writeText "lx-annotate-hub-nodes.json" (
    builtins.toJSON (
      map (
        node:
        node
        // {
          sharedSecretFile = if node.sharedSecretFile == null then null else toString node.sharedSecretFile;
        }
      ) cfg.hub.nodeProvisioning.nodes
    )
  );
  hubNodeProvisioningPython = pkgs.writeText "lx-annotate-provision-hub-nodes.py" ''
    import json
    from pathlib import Path

    from django.db import transaction
    from endoreg_db.models import Center, NetworkNode

    topology = json.loads(Path(${builtins.toJSON (toString hubNodeProvisioningData)}).read_text(encoding="utf-8"))

    with transaction.atomic():
        for spec in topology:
            center = None
            center_key = spec.get("centerKey")
            if center_key:
                center = Center.objects.filter(center_key=center_key).first()
                if center is None:
                    raise RuntimeError(f"Required Center.center_key is missing: {center_key}")

            node, created = NetworkNode.objects.update_or_create(
                node_key=spec["nodeKey"],
                defaults={
                    "display_name": spec["displayName"],
                    "role": spec["role"],
                    "base_url": spec.get("baseUrl", ""),
                    "is_active": True,
                    "owning_center": center,
                },
            )

            secret_changed = False
            secret_file = spec.get("sharedSecretFile")
            if secret_file:
                secret_path = Path(secret_file)
                if not secret_path.is_file():
                    raise RuntimeError(f"Required NetworkNode secret file is missing: {secret_path}")
                secret = secret_path.read_text(encoding="utf-8").strip()
                if not secret:
                    raise RuntimeError(f"Required NetworkNode secret file is empty: {secret_path}")
                if not node.check_shared_secret(secret):
                    node.set_shared_secret(secret)
                    node.save(update_fields=["shared_secret_hash", "updated_at"])
                    secret_changed = True

            print(json.dumps({
                "event": "hub.node_provisioned",
                "node_key": node.node_key,
                "role": node.role,
                "created": created,
                "secret_changed": secret_changed,
            }, sort_keys=True))
  '';
  hubNodeProvisioningScript = pkgs.writeShellScript "lx-annotate-provision-hub-nodes" ''
    set -euo pipefail
    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage shell < ${hubNodeProvisioningPython}
  '';

  mkWorker =
    {
      pool,
      queues,
      hostname,
      unitName ? null,
      mode ? "always",
      environment ? { },
      cudaVisibleDevices ? null,
      onCalendar ? null,
      randomizedDelaySec ? null,
      persistentTimer ? null,
      runtimeMaxSec ? null,
      timeoutStopSec ? null,
      after ? [ ],
      wants ? [ ],
      requires ? [ ],
    }:
    {
      inherit
        queues
        hostname
        mode
        environment
        after
        wants
        requires
        ;
      concurrency = pool.concurrency;
      maxTasksPerChild = pool.maxTasksPerChild;
      serviceConfig = {
        MemoryHigh = pool.memoryHigh;
        MemoryMax = pool.memoryMax;
        CPUQuota = pool.cpuQuota;
        CPUWeight = pool.cpuWeight;
        IOWeight = pool.ioWeight;
        Nice = pool.nice;
        OOMScoreAdjust = pool.oomScoreAdjust;
      };
    }
    // optionalAttrs (unitName != null) {
      inherit unitName;
    }
    // optionalAttrs (cudaVisibleDevices != null) {
      inherit cudaVisibleDevices;
    }
    // optionalAttrs (onCalendar != null) {
      inherit onCalendar;
    }
    // optionalAttrs (randomizedDelaySec != null) {
      inherit randomizedDelaySec;
    }
    // optionalAttrs (persistentTimer != null) {
      inherit persistentTimer;
    }
    // optionalAttrs (runtimeMaxSec != null) {
      inherit runtimeMaxSec;
    }
    // optionalAttrs (timeoutStopSec != null) {
      inherit timeoutStopSec;
    };

  postValidationWorkerEnv = { };
  inferenceWorkerEnv = { };
  trainingWorkerEnv = { };
  appServiceBaseAfter = [
    "network.target"
    "lx-annotate-runtime-env.service"
    featureRegistryGuardUnit
    "systemd-tmpfiles-setup.service"
  ]
  ++ localRedisServiceUnits
  ++ localPostgresServiceUnits
  ++ localPostgresSetupUnits
  ++ managedSecretsSetupUnits
  ++ encryptionServiceUnits;
  appServiceBaseWants = [
    "lx-annotate-runtime-env.service"
    featureRegistryGuardUnit
  ]
  ++ localRedisServiceUnits
  ++ localPostgresServiceUnits
  ++ localPostgresSetupUnits
  ++ managedSecretsSetupUnits
  ++ encryptionServiceUnits;
  appServiceBaseRequires = [
    "lx-annotate-runtime-env.service"
    featureRegistryGuardUnit
  ]
  ++ managedSecretsSetupUnits
  ++ encryptionServiceUnits;
  lxAnnotateJournalNamespace = "lx-annotate";
  mkLxAnnotateAppService =
    {
      description,
      after ? [ ],
      wants ? [ ],
      requires ? [ ],
      before ? [ ],
      wantedBy ? [ "multi-user.target" ],
      environment ? { },
      serviceConfig ? { },
      unitConfig ? { },
      restartTriggers ? [ effectiveRuntimePackage ],
    }:
    {
      inherit
        description
        before
        wantedBy
        restartTriggers
        ;
      after = appServiceBaseAfter ++ after;
      wants = appServiceBaseWants ++ wants;
      requires = appServiceBaseRequires ++ requires;
      unitConfig = encryptedDataMountUnitConfig // unitConfig;
      environment = commonExtraEnv // environment;
      serviceConfig = {
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
        WorkingDirectory = runtimeDataRootPath;
        EnvironmentFile = envSystemdFilePath;
        LogNamespace = lxAnnotateJournalNamespace;
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = appReadWritePaths;
      }
      // serviceConfig;
    };
  loadBaseDataServiceScript = pkgs.writeShellScript "lx-annotate-load-base-data-service" ''
    set -euo pipefail
    exec ${effectiveRuntimePackage}/bin/lx-annotate-load-base-data
  '';
  terminologyBootstrapScript = pkgs.writeShellScript "lx-annotate-terminology-bootstrap" ''
    set -euo pipefail

    registry_path=${lib.escapeShellArg terminologyRegistryPath}

    if [ ! -e "$registry_path" ]; then
      ${
        if terminologyInitialBundle == null then
          ''
            if ! ${effectiveRuntimePackage}/bin/lx-dtypes-kb-registry add-current \
              "$registry_path" \
              --activate; then
              echo "WARNING: the default terminology bundle shipped in the wheel environment could not be registered; LX-Annotate remains available without terminology features." >&2
              exit 0
            fi
          ''
        else
          ''
            if ! ${effectiveRuntimePackage}/bin/lx-dtypes-kb-registry add \
              "$registry_path" \
              ${terminologyInitialBundleArgs}; then
              echo "WARNING: the configured initial terminology bundle could not be installed; frontend setup remains available." >&2
              exit 0
            fi
          ''
      }
    fi

    active_module="$(${pkgs.jq}/bin/jq -er '.active.module_name | select(type == "string" and length > 0)' "$registry_path")" || {
      echo "WARNING: terminology registry has no valid active module; frontend setup remains available." >&2
      exit 0
    }
    active_version="$(${pkgs.jq}/bin/jq -er '.active.version | select(type == "string" and length > 0)' "$registry_path")" || {
      echo "WARNING: terminology registry has no valid active version; frontend setup remains available." >&2
      exit 0
    }
    if ! ${pkgs.jq}/bin/jq -e \
      --arg module "$active_module" \
      --arg version "$active_version" \
      '.modules[$module][$version] != null' \
      "$registry_path" >/dev/null; then
      echo "WARNING: active terminology identity is not registered; frontend setup remains available." >&2
      exit 0
    fi

    if ! LX_DTYPES_KB_REGISTRY="$registry_path" \
      ${effectiveRuntimePackage}/bin/lx-dtypes-prototype-kb-smoke \
        --module "$active_module" \
        --version "$active_version" >/dev/null; then
      echo "WARNING: active terminology bundle did not pass startup validation; annotation remains available and the bundle can be replaced from the frontend." >&2
      exit 0
    fi
  '';
  sapImportServiceScript = pkgs.writeShellScript "lx-annotate-sap-import-service" ''
    set -euo pipefail

    sap_drop_dir=${lib.escapeShellArg runtimeSapImportDirPath}
    sap_processed_dir=${lib.escapeShellArg runtimeSapImportProcessedDirPath}
    sap_failed_dir=${lib.escapeShellArg runtimeSapImportFailedDirPath}
    sap_output_dir=${lib.escapeShellArg runtimeWatcherPreanonymizedDirPath}

    for required_dir in "$sap_drop_dir" "$sap_processed_dir" "$sap_failed_dir" "$sap_output_dir"; do
      if [ ! -d "$required_dir" ]; then
        echo "ERROR: required SAP intake directory is missing: $required_dir" >&2
        exit 1
      fi
    done

    wait_for_stable_zip() {
      local file_path="$1"
      local previous_size="-1"
      local stable_checks=0
      local current_size=""

      for _ in $(${pkgs.coreutils}/bin/seq 1 6); do
        if [ ! -f "$file_path" ]; then
          return 1
        fi
        current_size="$(${pkgs.coreutils}/bin/stat -c %s "$file_path" 2>/dev/null || echo -1)"
        if [ "$current_size" = "$previous_size" ]; then
          stable_checks=$((stable_checks + 1))
          if [ "$stable_checks" -ge 2 ]; then
            return 0
          fi
        else
          stable_checks=0
          previous_size="$current_size"
        fi
        ${pkgs.coreutils}/bin/sleep 5
      done
      return 1
    }

    shopt -s nullglob
    for zip_path in "$sap_drop_dir"/*.zip; do
      zip_name="$(${pkgs.coreutils}/bin/basename "$zip_path")"
      if ! wait_for_stable_zip "$zip_path"; then
        echo "SAP import zip did not become stable in time: $zip_path" >&2
        continue
      fi

      if ${effectiveRuntimePackage}/bin/lx-annotate-import-sap "$zip_path" --output_dir "$sap_output_dir"; then
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_processed_dir/$zip_name"
      else
        echo "SAP import failed for $zip_path" >&2
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_failed_dir/$zip_name"
      fi
    done
  '';
  maintenanceWorkerPool = cfg.runtime.workerPools.maintenance // {
    inherit (cfg.runtime.workerLimits) memoryHigh memoryMax cpuQuota;
  };
  workerConfigs = {
    maintenance = mkWorker {
      unitName = "lx-annotate-celery-worker";
      hostname = "maintenance";
      queues = [
        "maintenance"
        "default"
      ];
      pool = maintenanceWorkerPool;
      environment = postValidationWorkerEnv;
    };
    hub-transfer = mkWorker {
      unitName = "lx-annotate-celery-hub-transfer-worker";
      hostname = "hub-transfer";
      queues = [ "hub_transfer" ];
      pool = cfg.runtime.workerPools.hubTransfer;
      mode = if cfg.hub.outboundTransfer.enable then "always" else "manual";
      environment = postValidationWorkerEnv;
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      requires =
        lib.optionals vaultClientHubPkiEnabled [
          "luxnix-vault-issue-hub-client-certificate.service"
        ]
        ++ hubNodeProvisioningServiceUnits;
    };
    pipeline = mkWorker {
      unitName = "lx-annotate-celery-pipeline-worker";
      hostname = "pipeline";
      queues = [ "pipeline" ];
      pool = cfg.runtime.workerPools.pipeline;
      environment = postValidationWorkerEnv;
    };
    frame-extraction = mkWorker {
      unitName = "lx-annotate-celery-frame-extraction-worker";
      hostname = "frame-extraction";
      queues = [ "frame_extraction" ];
      pool = cfg.runtime.workerPools.frameExtraction;
      mode =
        if cfg.runtime.frameExtractionWorker.mode == "maintenance-window" then
          "timer"
        else
          cfg.runtime.frameExtractionWorker.mode;
      environment = postValidationWorkerEnv;
      onCalendar = cfg.runtime.frameExtractionWorker.onCalendar;
      randomizedDelaySec = cfg.runtime.frameExtractionWorker.randomizedDelaySec;
      persistentTimer = cfg.runtime.frameExtractionWorker.persistentTimer;
      runtimeMaxSec = cfg.runtime.frameExtractionWorker.runtimeMaxSec;
      timeoutStopSec = cfg.runtime.frameExtractionWorker.timeoutStopSec;
    };
    ffmpeg = mkWorker {
      unitName = "lx-annotate-celery-ffmpeg-worker";
      hostname = "ffmpeg-media";
      queues = [ "ffmpeg_media" ];
      pool = cfg.runtime.workerPools.ffmpeg;
      mode = cfg.runtime.ffmpegWorker.mode;
      timeoutStopSec = cfg.runtime.ffmpegWorker.timeoutStopSec;
      environment = postValidationWorkerEnv;
    };
    inference = mkWorker {
      unitName = "lx-annotate-celery-inference-worker";
      hostname = "inference";
      queues = [ "inference" ];
      pool = cfg.runtime.workerPools.inference;
      mode = cfg.runtime.inferenceWorker.mode;
      environment = inferenceWorkerEnv;
      cudaVisibleDevices = cfg.runtime.inferenceWorker.cudaVisibleDevices;
    };
    training = mkWorker {
      unitName = "lx-annotate-celery-training-worker";
      hostname = "model-training";
      queues = [ "model_training" ];
      pool = cfg.runtime.workerPools.training;
      mode = cfg.runtime.trainingWorker.mode;
      environment = trainingWorkerEnv;
      cudaVisibleDevices = cfg.runtime.trainingWorker.cudaVisibleDevices;
    };
    llm-inference = mkWorker {
      unitName = "lx-annotate-celery-llm-inference-worker";
      hostname = "llm-inference";
      queues = [ "llm_inference" ];
      pool = cfg.runtime.workerPools.llmInference;
      mode = cfg.runtime.llmInferenceWorker.mode;
      environment = llmInferenceWorkerEnv;
      after = [ "ollama.service" ];
      wants = [ "ollama.service" ];
      requires = [ "ollama.service" ];
    };
  };
  alwaysWorkerServiceUnits = lib.mapAttrsToList (_: workerCfg: "${workerCfg.unitName}.service") (
    lib.filterAttrs (_: workerCfg: workerCfg.mode == "always") workerConfigs
  );
  mkWorkerService =
    name: workerCfg:
    let
      queueArg = lib.concatStringsSep "," workerCfg.queues;
      workerArgs = [
        "--hostname=${workerCfg.hostname}@%%h"
        "--queues=${queueArg}"
        "--concurrency=${toString workerCfg.concurrency}"
        "--prefetch-multiplier=1"
      ]
      ++ lib.optionals (workerCfg.maxTasksPerChild != null) [
        "--max-tasks-per-child=${toString workerCfg.maxTasksPerChild}"
      ];
      cudaVisibleDevices = workerCfg.cudaVisibleDevices or null;
      workerEnvironment =
        workerCfg.environment
        // {
          CELERY_LOG_LEVEL = "INFO";
          OMP_NUM_THREADS = "1";
          OPENBLAS_NUM_THREADS = "1";
          MKL_NUM_THREADS = "1";
          NUMEXPR_NUM_THREADS = "1";
          MALLOC_ARENA_MAX = "2";
        }
        // celeryWorkerResourceEnv
        // lib.optionalAttrs (cudaVisibleDevices != null) {
          CUDA_VISIBLE_DEVICES = cudaVisibleDevices;
        };
      runtimeMaxSec = workerCfg.runtimeMaxSec or null;
      timeoutStopSec = workerCfg.timeoutStopSec or "45min";
    in
    lib.nameValuePair workerCfg.unitName (mkLxAnnotateAppService {
      description = "LX-Annotate Celery worker ${name}";
      wantedBy = lib.optionals (workerCfg.mode == "always") [ "multi-user.target" ];
      after = [
        "lx-annotate-load-base-data.service"
        "lx-annotate-master-key-check.service"
        "lx-annotate-preflight.service"
      ]
      ++ workerCfg.after;
      wants = [
        "lx-annotate-load-base-data.service"
        "lx-annotate-preflight.service"
      ]
      ++ workerCfg.wants;
      requires = [
        "lx-annotate-load-base-data.service"
        "lx-annotate-master-key-check.service"
        "lx-annotate-preflight.service"
      ]
      ++ workerCfg.requires;
      environment = workerEnvironment;
      serviceConfig = {
        ExecStart = lib.escapeShellArgs (
          [ "${effectiveRuntimePackage}/bin/lx-annotate-worker" ] ++ workerArgs
        );
        Restart = if workerCfg.mode == "always" then "on-failure" else "no";
        RestartSec = "5s";
        TimeoutStopSec = timeoutStopSec;
      }
      // lib.optionalAttrs (runtimeMaxSec != null) {
        RuntimeMaxSec = runtimeMaxSec;
      }
      // workerCfg.serviceConfig;
    });
  workerServices = lib.listToAttrs (lib.mapAttrsToList mkWorkerService workerConfigs);
  mkTimer = unitName: timerCfg: {
    description = timerCfg.description;
    wantedBy = [ "timers.target" ];
    timerConfig = {
      Unit = "${unitName}.service";
      OnCalendar = timerCfg.onCalendar;
      RandomizedDelaySec = timerCfg.randomizedDelaySec;
      Persistent = timerCfg.persistent;
    };
  };
  workerTimers = lib.listToAttrs (
    lib.mapAttrsToList (
      name: workerCfg:
      lib.nameValuePair workerCfg.unitName (
        lib.mkIf (workerCfg.mode == "timer") (
          mkTimer workerCfg.unitName {
            description = "Schedule LX-Annotate Celery worker ${name}";
            inherit (workerCfg) onCalendar randomizedDelaySec;
            persistent = workerCfg.persistentTimer;
          }
        )
      )
    ) workerConfigs
  );
  ffmpegStreamThrottleScript = pkgs.writeShellScript "lx-annotate-ffmpeg-stream-throttle" ''
    set -euo pipefail

    worker_unit=${lib.escapeShellArg ffmpegStreamThrottleWorkerUnit}
    state_file=${lib.escapeShellArg ffmpegStreamThrottleStateFile}
    tmp_file=""
    trap 'if [ -n "$tmp_file" ]; then ${pkgs.coreutils}/bin/rm -f "$tmp_file"; fi' EXIT

    if ! ${pkgs.systemd}/bin/systemctl is-active --quiet "$worker_unit"; then
      echo "FFmpeg worker $worker_unit is inactive; skipping stream throttle reconciliation."
      ${pkgs.coreutils}/bin/rm -f "$state_file"
      exit 0
    fi

    mode_output="$(${effectiveRuntimePackage}/bin/lx-annotate-manage ffmpeg_stream_throttle_state --mode-only)"
    mode=""
    while IFS= read -r mode_line; do
      case "$mode_line" in
        streaming|normal)
          mode="$mode_line"
          ;;
      esac
    done <<EOF
    $mode_output
    EOF

    if [ -z "$mode" ]; then
      echo "ERROR: ffmpeg stream throttle did not report a valid mode. Raw output follows:" >&2
      printf '%s\n' "$mode_output" >&2
      exit 1
    fi

    case "$mode" in
      streaming)
        cpu_quota=${lib.escapeShellArg cfg.runtime.ffmpegStreamThrottle.streaming.cpuQuota}
        cpu_weight=${lib.escapeShellArg (toString cfg.runtime.ffmpegStreamThrottle.streaming.cpuWeight)}
        io_weight=${lib.escapeShellArg (toString cfg.runtime.ffmpegStreamThrottle.streaming.ioWeight)}
        ;;
      normal)
        cpu_quota=${lib.escapeShellArg ffmpegStreamThrottleNormalProfile.cpuQuota}
        cpu_weight=${lib.escapeShellArg (toString ffmpegStreamThrottleNormalProfile.cpuWeight)}
        io_weight=${lib.escapeShellArg (toString ffmpegStreamThrottleNormalProfile.ioWeight)}
        ;;
      *)
        echo "ERROR: unexpected ffmpeg stream throttle mode: $mode" >&2
        exit 1
        ;;
    esac

    desired="$mode:$cpu_quota:$cpu_weight:$io_weight"
    previous="$(${pkgs.coreutils}/bin/cat "$state_file" 2>/dev/null || true)"
    if [ "$previous" = "$desired" ]; then
      echo "FFmpeg stream throttle already reconciled: $desired"
      exit 0
    fi

    ${pkgs.systemd}/bin/systemctl set-property --runtime "$worker_unit" \
      CPUQuota="$cpu_quota" \
      CPUWeight="$cpu_weight" \
      IOWeight="$io_weight"

    state_dir="$(${pkgs.coreutils}/bin/dirname "$state_file")"
    ${pkgs.coreutils}/bin/install -d -m 0755 "$state_dir"
    tmp_file="$state_file.tmp.$$"
    printf '%s\n' "$desired" > "$tmp_file"
    ${pkgs.coreutils}/bin/mv -f "$tmp_file" "$state_file"
    tmp_file=""

    echo "Applied FFmpeg stream throttle mode=$mode cpu_quota=$cpu_quota cpu_weight=$cpu_weight io_weight=$io_weight"
  '';
  ffmpegStreamThrottleResetScript = pkgs.writeShellScript "lx-annotate-ffmpeg-stream-throttle-reset" ''
    set -euo pipefail

    ${pkgs.systemd}/bin/systemctl set-property --runtime \
      ${lib.escapeShellArg ffmpegStreamThrottleWorkerUnit} \
      CPUQuota=${lib.escapeShellArg cfg.runtime.workerPools.ffmpeg.cpuQuota} \
      CPUWeight=${lib.escapeShellArg (toString cfg.runtime.workerPools.ffmpeg.cpuWeight)} \
      IOWeight=${lib.escapeShellArg (toString cfg.runtime.workerPools.ffmpeg.ioWeight)}
    ${pkgs.coreutils}/bin/rm -f ${lib.escapeShellArg ffmpegStreamThrottleStateFile}

    echo "Reset FFmpeg worker runtime controls to the declared worker-pool profile."
  '';

  runtimeEnvScript = pkgs.writeShellScript "lx-annotate-runtime-env" ''
    set -euo pipefail

    install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${endoreg-service-user-home}
    install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeRootPath}
    install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
    install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envDataDir}

    source_pwd="${cfg.database.endoregLocalUserPasswordFile}"
    target_pwd="${envConfDir}/db_pwd"
    if [ -f "$source_pwd" ]; then
      cp "$source_pwd" "$target_pwd"
      chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$target_pwd"
      chmod 0600 "$target_pwd"
    else
      echo "WARNING: lx-annotate database password file $source_pwd not found" >&2
    fi

    [ -f "${toString cfg.django.keycloakSecretFile}" ] && chgrp ${config.luxnix.generic-settings.sensitiveServiceGroupName} "${toString cfg.django.keycloakSecretFile}" || true
    [ -f "${toString cfg.django.keycloakSecretFile}" ] && chmod 0640 "${toString cfg.django.keycloakSecretFile}" || true

    tmp_file="${envSystemdFilePath}.tmp"
    cat > "$tmp_file" <<'EOF'
    ${envContract.commonSystemdEnvText}
    EOF

    install -m 0640 -o root -g ${endoreg-service-group-name} "$tmp_file" "${envSystemdFilePath}"
    cp -f "${envSystemdFilePath}" "${envDataDir}/.env.systemd"
    chown root:${endoreg-service-group-name} "${envDataDir}/.env.systemd"
    chmod 0640 "${envDataDir}/.env.systemd"
    rm -f "$tmp_file"
  '';

  dataCleanupScript = pkgs.writeShellScriptBin "runLxAnnotateDataCleanup" ''
    set -euo pipefail

    runtime_root="${envDataDir}"
    archive_root="${cfg.dataCleanup.archiveDir}"
    persisting_mount="${config.roles.endoreg-client.paths.storagePersistingMountPoint}"
    marker_dir="$runtime_root/logs"
    marker_file="$marker_dir/data_cleanup_latest.log"

    mkdir -p "$marker_dir"

    if [ ! -d "$runtime_root" ]; then
      echo "Skipping cleanup; runtime root missing: $runtime_root"
      exit 0
    fi

    if ! ${pkgs.util-linux}/bin/mountpoint -q "$persisting_mount"; then
      echo "ERROR: refusing cleanup because persisting storage is not a mounted filesystem: $persisting_mount" >&2
      exit 1
    fi

    resolved_mount="$(${pkgs.coreutils}/bin/realpath -m "$persisting_mount")"
    resolved_archive="$(${pkgs.coreutils}/bin/realpath -m "$archive_root")"
    case "$resolved_archive/" in
      "$resolved_mount/"*) ;;
      *)
        echo "ERROR: refusing cleanup because archive is outside the persisting mount: $resolved_archive" >&2
        exit 1
        ;;
    esac
    ${pkgs.coreutils}/bin/install -d -m 0750 "$archive_root"
    if [ "$(${pkgs.util-linux}/bin/findmnt -n -o TARGET --target "$resolved_archive" 2>/dev/null || true)" != "$resolved_mount" ]; then
      echo "ERROR: refusing cleanup because archive does not resolve to the configured persisting mount: $resolved_archive" >&2
      exit 1
    fi

    mkdir -p "$archive_root"

    moved_count=0
    skipped_count=0

    move_duplicate_tree() {
      local source_root="$1"
      local runtime_target_root="$2"
      local label="$3"

      if [ ! -d "$source_root" ]; then
        echo "Skipping $label source; directory not present: $source_root"
        return 0
      fi

      while IFS= read -r -d "" source_file; do
        local rel_path runtime_file archive_file archive_dir

        rel_path="''${source_file#"$source_root"/}"
        runtime_file="$runtime_target_root/$rel_path"
        if [ ! -f "$runtime_file" ]; then
          skipped_count=$((skipped_count + 1))
          continue
        fi

        if ! ${pkgs.diffutils}/bin/cmp -s "$source_file" "$runtime_file"; then
          skipped_count=$((skipped_count + 1))
          continue
        fi

        archive_file="$archive_root/$label/$rel_path"
        archive_dir="$(${pkgs.coreutils}/bin/dirname "$archive_file")"
        ${pkgs.coreutils}/bin/mkdir -p "$archive_dir"

        if [ -e "$archive_file" ]; then
          if ${pkgs.diffutils}/bin/cmp -s "$source_file" "$archive_file"; then
            ${pkgs.coreutils}/bin/rm -f "$source_file"
          else
            archive_file="$archive_file.$(${pkgs.coreutils}/bin/date +%s)"
            ${pkgs.coreutils}/bin/mv "$source_file" "$archive_file"
          fi
        else
          ${pkgs.coreutils}/bin/mv "$source_file" "$archive_file"
        fi

        moved_count=$((moved_count + 1))
      done < <(${pkgs.findutils}/bin/find "$source_root" -type f -print0)

      ${pkgs.findutils}/bin/find "$source_root" -depth -type d -empty -delete || true
    }

    move_duplicate_tree "${cfg.dataCleanup.legacyProcessedReportDir}" "${cfg.dataCleanup.runtimeProcessedReportDir}" "legacy-data/${processedReportDirName}"
    move_duplicate_tree "${cfg.dataCleanup.legacyProcessedVideoDir}" "${cfg.dataCleanup.runtimeProcessedVideoDir}" "legacy-data/${processedVideoDirName}"
    move_duplicate_tree "${cfg.dataCleanup.legacyMediaProcessedReportDir}" "${cfg.dataCleanup.runtimeProcessedReportDir}" "legacy-media/${processedReportDirName}"
    move_duplicate_tree "${cfg.dataCleanup.legacyMediaProcessedVideoDir}" "${cfg.dataCleanup.runtimeProcessedVideoDir}" "legacy-media/${processedVideoDirName}"

    {
      printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
      printf 'runtime_root=%s\n' "$runtime_root"
      printf 'archive_root=%s\n' "$archive_root"
      printf 'moved_count=%s\n' "$moved_count"
      printf 'skipped_count=%s\n' "$skipped_count"
    } > "$marker_file"

    chmod 0640 "$marker_file"

    echo "Cleanup completed. moved=$moved_count skipped=$skipped_count archive=$archive_root"
  '';

  storageReliefScripts = import ./scripts/storage-relief.nix args;
  inherit (storageReliefScripts)
    emergencyStorageReliefConfig
    ;
  lxAnnotateScripts = import ./scripts.nix (
    args
    // {
      inherit
        effectiveRuntimePackage
        envContract
        ;
    }
  );
  inherit (lxAnnotateScripts.packages)
    lxAnnotateMigrateVideoStreamableStorageScript
    runLocalDataRecoveryScript
    runLocalHlsMaterializationScript
    runLocalMasterKeyCheckScript
    ;
  inherit (lxAnnotateScripts.serviceOrdering)
    fileMoverAfter
    fileMoverRequires
    fileMoverWants
    ;
  emergencyStorageReliefScript = pkgs.writeShellScriptBin "runLxAnnotateEmergencyStorageRelief" ''
    set -euo pipefail

    external_mount_point=${lib.escapeShellArg cfg.storageRelief.externalMountPoint}
    expected_device_id=${
      lib.escapeShellArg (
        if cfg.storageRelief.expectedDeviceId == null then "" else cfg.storageRelief.expectedDeviceId
      )
    }
    expected_device_part=${lib.escapeShellArg cfg.storageRelief.expectedDevicePart}
    expected_fs_uuid=${
      lib.escapeShellArg (
        if cfg.storageRelief.expectedFsUuid == null then "" else cfg.storageRelief.expectedFsUuid
      )
    }

    if [ "${boolString cfg.storageRelief.requireExternalMount}" = "true" ]; then
      if [ -z "$expected_device_id" ] && [ -z "$expected_fs_uuid" ]; then
        echo "ERROR: storageRelief requires expectedDeviceId or expectedFsUuid" >&2
        exit 1
      fi

      if ! "${pkgs.util-linux}/bin/mountpoint" -q "$external_mount_point"; then
        echo "ERROR: external relief mount is not mounted: $external_mount_point" >&2
        exit 1
      fi

      actual_source="$("${pkgs.util-linux}/bin/findmnt" -n -o SOURCE --target "$external_mount_point" || true)"
      if [ -z "$actual_source" ]; then
        echo "ERROR: unable to resolve mounted source for $external_mount_point" >&2
        exit 1
      fi
      actual_source_resolved="$("${pkgs.coreutils}/bin/readlink" -f "$actual_source" 2>/dev/null || printf '%s' "$actual_source")"

      if [ -n "$expected_device_id" ]; then
        expected_path="/dev/disk/by-id/$expected_device_id-$expected_device_part"
        if [ ! -e "$expected_path" ]; then
          echo "ERROR: configured relief device path does not exist: $expected_path" >&2
          exit 1
        fi
        expected_resolved="$("${pkgs.coreutils}/bin/readlink" -f "$expected_path")"
        if [ "$actual_source_resolved" != "$expected_resolved" ]; then
          echo "ERROR: mounted source $actual_source_resolved does not match expected $expected_resolved" >&2
          exit 1
        fi
      fi

      if [ -n "$expected_fs_uuid" ]; then
        actual_fs_uuid="$("${pkgs.util-linux}/bin/findmnt" -n -o UUID --target "$external_mount_point" 2>/dev/null || true)"
        if [ -z "$actual_fs_uuid" ]; then
          actual_fs_uuid="$("${pkgs.util-linux}/bin/blkid" -s UUID -o value "$actual_source_resolved" 2>/dev/null || true)"
        fi
        if [ "$actual_fs_uuid" != "$expected_fs_uuid" ]; then
          echo "ERROR: mounted filesystem UUID $actual_fs_uuid does not match expected $expected_fs_uuid" >&2
          exit 1
        fi
      fi
    fi

    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage emergency_storage_relief --config ${lib.escapeShellArg (toString emergencyStorageReliefConfig)}
  '';

  hubBackupScripts = import ./scripts/hub-backup.nix args;
  inherit (hubBackupScripts) runLocalHubBackupScript;
  encryptedDataScripts = import ./scripts/encrypted-data.nix args;
  inherit (encryptedDataScripts)
    lxAnnotateEncryptedDataMountScript
    lxAnnotateEncryptedDataUmountScript
    ;
  workerSubservice = import ./subservices/workers.nix {
    inherit workerServices workerTimers;
  };
in
{
  config = mkIf cfg.enable (mkMerge [
    {
      services.luxnix.lxAnnotateLocal.hub.enable = mkDefault (config.networking.hostName == "gs-02");
      services.luxnix.lxAnnotateLocal.runtime.deploymentRole = mkDefault (
        if cfg.hub.enable then "central_hub" else "site_node"
      );
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.clientCertificateFile =
        mkIf vaultClientHubPkiEnabled (mkDefault config.luxnix.vault.client.hubPki.certificateFile);
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.clientKeyFile = mkIf vaultClientHubPkiEnabled (
        mkDefault config.luxnix.vault.client.hubPki.keyFile
      );
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.sourceNodeSecretFile =
        mkIf vaultClientHubPkiEnabled (mkDefault config.luxnix.vault.client.hubPki.nodeSecretFile);
      services.luxnix.lxAnnotateLocal.runtime.celeryBroker.requireSecureTransport = mkDefault (
        cfg.runtime.clustered.enable
        || (externalRedisConfigured && !isLocalRedisUrl cfg.runtime.externalServices.redisUrl)
      );
      services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = mkIf (
        cfg.runtime.deploymentRole == "central_hub"
      ) (mkDefault true);
      services.luxnix.ollama.enable = mkIf (cfg.runtime.llmInferenceWorker.mode == "always") (
        mkDefault true
      );

      services.luxnix.fileMover = {
        serviceDependencies = {
          after = mkAfter fileMoverAfter;
          wants = mkAfter fileMoverWants;
          requires = mkAfter fileMoverRequires;
        };
        paths = {
          destinationVideoDir = mkDefault runtimeWatcherVideoDirPath;
          destinationReportDir = mkDefault runtimeWatcherReportDirPath;
          stagingDir = mkDefault runtimeMoverStagingDirPath;
        };
        desktop.links = {
          preanonymized_import = mkDefault desktopPreanonymizedLinkTarget;
          sap_import = mkDefault desktopSapImportLinkTarget;
        };
        videoTranscodeFallback = {
          command = mkDefault lxAnnotateFileMoverTranscodeCommand;
          workingDir = mkDefault runtimeDataRootPath;
          environmentScript = mkDefault lxAnnotateFileMoverTranscodeEnv;
        };
      };

      assertions = [
        {
          assertion = builtins.length lxAnnotateEndoregDbDependencies == 1;
          message = "The pinned lx-annotate source must declare exactly one endoreg-db== dependency for feature-registry attestation.";
        }
        {
          assertion = !useWheelRuntime || cfg.runtime.wheelPath != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set in wheel mode.";
        }
        {
          assertion = !useWheelRuntime || packageVersion != "";
          message = "services.luxnix.lxAnnotateLocal.runtime.packageVersion must be set or inferable from the wheel filename in wheel mode.";
        }
        {
          assertion = terminologyPathStaysInsideEncryptedData terminologyRegistryPath;
          message = "services.luxnix.lxAnnotateLocal.runtime.terminology.registryPath must stay inside runtime.encryptedDataDir.";
        }
        {
          assertion = terminologyPathStaysInsideEncryptedData terminologyImportRoot;
          message = "services.luxnix.lxAnnotateLocal.runtime.terminology.importRoot must stay inside runtime.encryptedDataDir.";
        }
        {
          assertion =
            terminologyInitialBundle == null
            || (terminologyInitialBundle.moduleName != "" && terminologyInitialBundle.version != "");
          message = "services.luxnix.lxAnnotateLocal.runtime.terminology.initialBundle requires non-empty moduleName and version.";
        }
        {
          assertion = terminologyInitialBundle == null || useWheelRuntime;
          message = "services.luxnix.lxAnnotateLocal.runtime.terminology.initialBundle is currently supported only in wheel mode.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || cfg.runtime.externalServices.redisUrl != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.externalServices.redisUrl.";
        }
        {
          assertion = cfg.runtime.llmInferenceWorker.mode != "always" || config.services.luxnix.ollama.enable;
          message = "services.luxnix.lxAnnotateLocal.runtime.llmInferenceWorker.mode = \"always\" requires services.luxnix.ollama.enable = true.";
        }
        {
          assertion =
            !cfg.runtime.celeryBroker.requireSecureTransport
            || cfg.runtime.celeryBroker.secureTransportConfirmed
            || brokerUrlUsesSecureTransport celeryBrokerUrl;
          message = "services.luxnix.lxAnnotateLocal.runtime.celeryBroker.requireSecureTransport requires a rediss:// or amqps:// broker URL, or runtime.celeryBroker.secureTransportConfirmed = true.";
        }
        {
          assertion = cfg.runtime.deploymentRole != "central_hub" || cfg.hub.enable;
          message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.enable = true. LuxNix servers/central nodes use central_hub; laptop center nodes use site_node.";
        }
        {
          assertion =
            cfg.runtime.deploymentRole != "central_hub" || cfg.hub.transferApi.requireSecureTransport;
          message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.transferApi.requireSecureTransport = true to match lx-annotate production settings.";
        }
        {
          assertion = cfg.runtime.deploymentRole != "central_hub" || cfg.hub.transferApi.requireMtls;
          message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.transferApi.requireMtls = true to match lx-annotate production settings.";
        }
        {
          assertion =
            cfg.runtime.deploymentRole != "central_hub"
            || (cfg.hub.transferApi.mtlsMetaKey != "" && cfg.hub.transferApi.mtlsMetaValue != "");
          message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires non-empty hub.transferApi.mtlsMetaKey and mtlsMetaValue.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || !isLocalRedisUrl cfg.runtime.externalServices.redisUrl;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a non-local Redis URL.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || cfg.runtime.externalServices.postgresHost != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.externalServices.postgresHost.";
        }
        {
          assertion =
            !cfg.runtime.clustered.enable || !isLocalPostgresHost cfg.runtime.externalServices.postgresHost;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a non-local PostgreSQL host.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || cfg.runtime.clustered.sharedStorage;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.clustered.sharedStorage = true.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || cfg.runtime.clustered.sharedMasterKeyFile != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.clustered.sharedMasterKeyFile.";
        }
        {
          assertion =
            !cfg.runtime.clustered.enable
            || cfg.runtime.masterKeyFile == cfg.runtime.clustered.sharedMasterKeyFile;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.masterKeyFile to match runtime.clustered.sharedMasterKeyFile.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || !cfg.runtime.autoGenerateMasterKey;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.autoGenerateMasterKey = false.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || !cfg.runtime.managedEncryptedData.enable;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable does not support per-host managedEncryptedData.";
        }
        {
          assertion = !cfg.runtime.clustered.enable || !cfg.runtime.vaultManagedEncryptedData.enable;
          message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a shared workload master key, not hostname-scoped vaultManagedEncryptedData.";
        }
        {
          assertion =
            !lib.hasPrefix "${repoDir}/" cfg.runtime.encryptedDataDir
            && cfg.runtime.encryptedDataDir != repoDir
            && !lib.hasPrefix "${runtimeWheelRootPath}/" cfg.runtime.encryptedDataDir
            && cfg.runtime.encryptedDataDir != runtimeWheelRootPath;
          message = "services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir must stay outside the repo/app path.";
        }
        {
          assertion =
            !cfg.runtime.managedEncryptedData.enable
            || cfg.runtime.managedEncryptedData.luksUuid != null
            || cfg.runtime.managedEncryptedData.luksUuidFile != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuid or luksUuidFile must be set when managedEncryptedData.enable = true.";
        }
        {
          assertion =
            !cfg.runtime.managedEncryptedData.enable || cfg.runtime.managedEncryptedData.keyFile != null;
          message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile must be set when managedEncryptedData.enable = true.";
        }
        {
          assertion =
            !cfg.runtime.managedEncryptedData.enable
            || cfg.runtime.encryptionService == null
            || cfg.runtime.encryptionService == managedEncryptedDataServiceName;
          message = "services.luxnix.lxAnnotateLocal.runtime.encryptionService must stay unset or equal to lx-annotate-encrypted-data.service when managedEncryptedData.enable = true.";
        }
        {
          assertion = !cfg.runtime.vaultManagedEncryptedData.enable || config.networking.hostName != "";
          message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires networking.hostName to be set.";
        }
        {
          assertion =
            !cfg.runtime.vaultManagedEncryptedData.enable
            || (
              config.luxnix.vault.enable
              && (
                config.luxnix.vault.client.auth.method != "none"
                || config.luxnix.vault.client.environmentFile != null
              )
            );
          message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires luxnix.vault client configuration, either via auth bootstrap or a declared environmentFile.";
        }
        {
          assertion =
            cfg.runtime.masterKeyFile != null
            || cfg.runtime.autoGenerateMasterKey
            || (
              cfg.runtime.vaultManagedEncryptedData.enable
              && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
            );
          message = "services.luxnix.lxAnnotateLocal requires an application master key for encrypted storage. Set runtime.masterKeyFile, keep runtime.autoGenerateMasterKey = true, or enable vaultManagedEncryptedData.manageMasterKey.";
        }
        {
          assertion = !cfg.hub.backup.enable || cfg.hub.enable;
          message = "services.luxnix.lxAnnotateLocal.hub.backup.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
        }
        {
          assertion = !cfg.hub.backup.enable || config.services.postgresqlBackup.enable;
          message = "services.luxnix.lxAnnotateLocal.hub.backup.enable requires services.postgresqlBackup.enable so every published media snapshot contains a fresh database dump.";
        }
        {
          assertion = !cfg.hub.transferApi.enable || cfg.hub.enable;
          message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
        }
        {
          assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireSecureTransport;
          message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireSecureTransport = true.";
        }
        {
          assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireMtls;
          message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = true.";
        }
        {
          assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.clientCaFile != null;
          message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.clientCaFile to be set.";
        }
        {
          assertion = !cfg.hub.outboundTransfer.enable || cfg.runtime.deploymentRole == "site_node";
          message = "services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable requires runtime.deploymentRole = \"site_node\".";
        }
        {
          assertion = !cfg.hub.outboundTransfer.enable || cfg.hub.outboundTransfer.requireMtls;
          message = "services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable requires outboundTransfer.requireMtls = true.";
        }
        {
          assertion =
            !cfg.hub.outboundTransfer.enable || cfg.hub.outboundTransfer.clientCertificateFile != null;
          message = "services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable requires an outbound client certificate file.";
        }
        {
          assertion = !cfg.hub.outboundTransfer.enable || cfg.hub.outboundTransfer.clientKeyFile != null;
          message = "services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable requires an outbound client key file.";
        }
        {
          assertion =
            !cfg.hub.outboundTransfer.enable || cfg.hub.outboundTransfer.sourceNodeSecretFile != null;
          message = "services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable requires a source-node secret file.";
        }
        {
          assertion = !cfg.hub.nodeProvisioning.enable || cfg.hub.nodeProvisioning.nodes != [ ];
          message = "hub.nodeProvisioning.enable requires at least one NetworkNode specification.";
        }
        {
          assertion =
            let
              keys = map (node: node.nodeKey) cfg.hub.nodeProvisioning.nodes;
            in
            builtins.length keys == builtins.length (lib.unique keys);
          message = "hub.nodeProvisioning.nodes requires unique nodeKey values.";
        }
        {
          assertion = lib.all (
            node: node.role != "central_hub" || lib.hasPrefix "https://" node.baseUrl
          ) cfg.hub.nodeProvisioning.nodes;
          message = "Every provisioned central_hub NetworkNode requires an HTTPS baseUrl.";
        }
        {
          assertion =
            !cfg.hub.transferApi.enable
            || (cfg.hub.transferApi.mtlsMetaKey != "" && cfg.hub.transferApi.mtlsMetaValue != "");
          message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires non-empty mTLS meta key and value.";
        }
        {
          assertion =
            !cfg.hub.backup.enable
            || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.incomingDir;
          message = "services.luxnix.lxAnnotateLocal.hub.backup.incomingDir must stay inside runtime.encryptedDataDir.";
        }
        {
          assertion =
            !cfg.hub.backup.enable
            || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.snapshotDir;
          message = "services.luxnix.lxAnnotateLocal.hub.backup.snapshotDir must stay inside runtime.encryptedDataDir.";
        }
        {
          assertion =
            !cfg.hub.backup.enable
            || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.manifestDir;
          message = "services.luxnix.lxAnnotateLocal.hub.backup.manifestDir must stay inside runtime.encryptedDataDir.";
        }
        {
          assertion =
            !cfg.storageRelief.enable
            || !cfg.storageRelief.requireExternalMount
            || cfg.storageRelief.expectedDeviceId != null
            || cfg.storageRelief.expectedFsUuid != null;
          message = "services.luxnix.lxAnnotateLocal.storageRelief requires expectedDeviceId or expectedFsUuid when requireExternalMount = true.";
        }
        {
          assertion =
            !cfg.storageRelief.enable
            || cfg.storageRelief.archiveDir == cfg.storageRelief.externalMountPoint
            || lib.hasPrefix "${cfg.storageRelief.externalMountPoint}/" cfg.storageRelief.archiveDir;
          message = "services.luxnix.lxAnnotateLocal.storageRelief.archiveDir must stay inside storageRelief.externalMountPoint.";
        }
        {
          assertion =
            !cfg.storageRelief.enable
            || cfg.storageRelief.manifestDir == cfg.storageRelief.archiveDir
            || lib.hasPrefix "${cfg.storageRelief.archiveDir}/" cfg.storageRelief.manifestDir;
          message = "services.luxnix.lxAnnotateLocal.storageRelief.manifestDir must stay inside storageRelief.archiveDir.";
        }
        {
          assertion =
            !cfg.storageRelief.enable
            || cfg.storageRelief.stagingDir == cfg.storageRelief.archiveDir
            || lib.hasPrefix "${cfg.storageRelief.archiveDir}/" cfg.storageRelief.stagingDir;
          message = "services.luxnix.lxAnnotateLocal.storageRelief.stagingDir must stay inside storageRelief.archiveDir.";
        }
      ];

      services.luxnix.lxAnnotateLocal.django.extraSettings.IS_CENTRAL_NODE = mkIf cfg.hub.enable (
        mkForce true
      );
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable (mkDefault true);
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable (
          mkDefault cfg.runtime.vaultManagedEncryptedData.keyFilePath
        );
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuidFile =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable (
          mkDefault cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath
        );
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.after =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable
          (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.requires =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable
          (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
      services.luxnix.lxAnnotateLocal.runtime.masterKeyFile = mkDefault (
        if cfg.runtime.clustered.enable && cfg.runtime.clustered.sharedMasterKeyFile != null then
          cfg.runtime.clustered.sharedMasterKeyFile
        else if
          cfg.runtime.vaultManagedEncryptedData.enable
          && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
        then
          cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath
        else if cfg.runtime.autoGenerateMasterKey then
          cfg.runtime.autoGeneratedMasterKeyFilePath
        else
          null
      );
      services.luxnix.lxAnnotateLocal.database.host = mkIf (
        cfg.runtime.externalServices.postgresHost != null
      ) (mkForce cfg.runtime.externalServices.postgresHost);
      services.luxnix.lxAnnotateLocal.database.port = mkIf (
        cfg.runtime.externalServices.postgresPort != null
      ) (mkForce cfg.runtime.externalServices.postgresPort);

      roles.managed-secrets.runBefore = mkAfter [
        "lx-annotate-runtime-env.service"
        "lx-annotate-master-key-check.service"
        "lx-annotate.service"
      ];

      roles.managed-secrets.customSecrets.lx_annotate_master_key_local =
        mkIf
          (
            cfg.runtime.autoGenerateMasterKey
            && !cfg.runtime.vaultManagedEncryptedData.enable
            && (
              cfg.runtime.masterKeyFile == null
              || cfg.runtime.masterKeyFile == cfg.runtime.autoGeneratedMasterKeyFilePath
            )
          )
          {
            path = toString cfg.runtime.autoGeneratedMasterKeyFilePath;
            owner = "root";
            group = config.luxnix.generic-settings.sensitiveServiceGroupName;
            permissions = "640";
            description = "Per-machine application master key for lx-annotate encrypted storage";
            generator = "${pkgs.openssl}/bin/openssl rand -base64 32 | tr -d '\n'";
          };

      roles.managed-secrets.customSecrets.lx_annotate_luks_key =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable
          {
            path = toString cfg.runtime.vaultManagedEncryptedData.keyFilePath;
            owner = "root";
            group = "root";
            permissions = "400";
            description = "Vault-backed LUKS key for lx-annotate encrypted data";
            customScript = true;
            refreshOnBoot = true;
            generator = ''
              HOSTNAME=${lib.escapeShellArg config.networking.hostName}
              VAULT_PATH=${
                lib.escapeShellArg (
                  lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                    cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
                )
              }
              ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
                | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultKeyField}' \
                > "$TARGET_FILE"
            '';
          };

      roles.managed-secrets.customSecrets.lx_annotate_luks_uuid =
        mkIf cfg.runtime.vaultManagedEncryptedData.enable
          {
            path = toString cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath;
            owner = "root";
            group = "root";
            permissions = "400";
            description = "Vault-backed LUKS UUID for lx-annotate encrypted data";
            customScript = true;
            refreshOnBoot = true;
            generator = ''
              HOSTNAME=${lib.escapeShellArg config.networking.hostName}
              VAULT_PATH=${
                lib.escapeShellArg (
                  lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                    cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
                )
              }
              ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
                | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultUuidField}' \
                | tr -d '\n' > "$TARGET_FILE"
            '';
          };

      roles.managed-secrets.customSecrets.lx_annotate_master_key =
        mkIf
          (
            cfg.runtime.vaultManagedEncryptedData.enable
            && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
          )
          {
            path = toString cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath;
            owner = "root";
            group = config.luxnix.generic-settings.sensitiveServiceGroupName;
            permissions = "640";
            description = "Vault-backed application master key for lx-annotate encrypted storage";
            customScript = true;
            refreshOnBoot = true;
            generator = ''
              HOSTNAME=${lib.escapeShellArg config.networking.hostName}
              VAULT_PATH=${
                lib.escapeShellArg (
                  lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                    cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
                )
              }
              ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
                | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultMasterKeyField}' \
                | tr -d '\n' > "$TARGET_FILE"
              if [ ! -s "$TARGET_FILE" ]; then
                echo "ERROR: Vault returned an empty lx-annotate application master key from $VAULT_PATH."
                exit 1
              fi
              if [ -f "$SECRET_FILE" ] && ! ${pkgs.diffutils}/bin/cmp -s "$SECRET_FILE" "$TARGET_FILE"; then
                echo "ERROR: Vault lx-annotate application master key differs from the existing local key at $SECRET_FILE."
                echo "Refusing to replace it during managed-secrets refresh because that would break decryption of existing app-layer encrypted data."
                exit 1
              fi
            '';
          };

      services.luxnix.lxAnnotateLocal.django.djangoAllowedHosts = mkAfter [
        cfg.django.hostname
      ];
      services.luxnix.lxAnnotateLocal.django.sslCertificatePath = mkDefault defaultSslCertificatePath;
      services.luxnix.lxAnnotateLocal.django.sslKeyPath = mkDefault defaultSslKeyPath;
      services.luxnix.lxSsl.enable = mkDefault true;

      services.lx-annotate = {
        enable = true;
        package = effectiveRuntimePackage;
        user = endoreg-service-user-name;
        group = endoreg-service-group-name;
        host = "127.0.0.1";
        port = cfg.django.port;
        deploymentRole = cfg.runtime.deploymentRole;
        encryptedDataDir = cfg.runtime.encryptedDataDir;
        dataDir = cfg.runtime.encryptedDataDir;
        settingsModule = "lx_annotate.settings.settings_prod";
        environmentFile = envSystemdFilePath;
        extraEnv = commonExtraEnv;
      };

      services.nginx = {
        enable = true;
        recommendedProxySettings = true;
        recommendedTlsSettings = true;

        virtualHosts."${cfg.django.hostname}" = {
          forceSSL = true;
          sslCertificate = sslCertPath;
          sslCertificateKey = sslKeyPath;
          extraConfig = ''
            client_max_body_size 50G;
            proxy_request_buffering off;
          ''
          + optionalString sslCfg.enable ''
            ssl_stapling off;
            ssl_stapling_verify off;
            ${optionalString cfg.hub.transferApi.enable ''
              ssl_verify_client optional;
              ssl_client_certificate ${toString cfg.hub.transferApi.clientCaFile};
            ''}
          '';
          locations."/static/" = {
            alias = "${packageStaticRoot}/";
            extraConfig = "expires 30d; add_header Cache-Control 'public';";
          };
          locations."/media/" = {
            alias = "${envDataDir}/";
            extraConfig = "sendfile on; tcp_nopush on;";
          };
          locations."/protected_media/" = {
            alias = "${runtimeStorageRootPath}/";
            extraConfig = "internal; sendfile on; tcp_nopush on;";
          };
          locations."/api/media/videos/" = {
            proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
            proxyWebsockets = true;
            extraConfig = videoStreamProxyExtraConfig;
          };
          locations."/endoreg-api/media/videos/" = {
            proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
            proxyWebsockets = true;
            extraConfig = videoStreamProxyExtraConfig;
          };
          locations."/api/media/hub/transfers/" = mkIf cfg.hub.transferApi.enable {
            proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
            extraConfig = hubTransferProxyExtraConfig;
          };

          # Canonical lx-annotate API prefix. Keep the /api/ route above for
          # compatibility with the existing HubTransferClient.
          locations."/endoreg-api/media/hub/transfers/" = mkIf cfg.hub.transferApi.enable {
            proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
            extraConfig = hubTransferProxyExtraConfig;
          };

          locations."/" = {
            proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
            proxyWebsockets = true;
            extraConfig = ''
              proxy_set_header X-Client-Cert-Verified $ssl_client_verify;
              proxy_read_timeout 600s;
              proxy_send_timeout 600s;
              proxy_buffering off;
            '';
          };
        };
      };

      fileSystems = mkIf streamableExternalStorageEnabled {
        "${runtimeStreamableVideoRootPath}" = {
          device = streamableExternalStorageRoot;
          fsType = "none";
          options = [
            "bind"
            "x-systemd.requires-mounts-for=${streamableExternalStorageRoot}"
          ];
        };
      };

      luxnix.generic-settings.postgres.enable = mkDefault (!externalPostgresConfigured);
      services.redis.servers."lx-annotate" = mkIf (!externalRedisConfigured) {
        enable = true;
        port = 6379;
        bind = "127.0.0.1";
        openFirewall = false;
        appendOnly = true;
        appendFsync = "everysec";
      };

      users.users.${endoreg-service-user-name} = {
        home = mkForce endoreg-service-user-home;
        group = mkForce endoreg-service-group-name;
      };
      users.users.nginx.extraGroups = mkAfter [ endoreg-service-group-name ];

      systemd.tmpfiles.rules =
        lib.optional streamableExternalStorageEnabled "d ${streamableExternalStorageRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
        ++ [
          "d ${endoreg-service-user-home} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeWheelRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeWheelRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeWheelVenvPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeWheelVenvPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${envDataDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${envDataDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${terminologyRegistryDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${terminologyRegistryDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${terminologyImportRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${terminologyImportRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${envConfDir} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeWatcherVideoDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeWatcherVideoDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeWatcherReportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeWatcherReportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeWatcherPreanonymizedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeWatcherPreanonymizedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeSapImportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeSapImportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeSapImportProcessedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeSapImportProcessedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeSapImportFailedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeSapImportFailedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeMoverStagingDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "L ${serviceUserIoAccessLinkPath} - - - - ${runtimeIoImportRootPath}"
          "d ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${cfg.runtime.modelTrainingStagingRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} 7d -"
          "z ${cfg.runtime.modelTrainingStagingRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${hubRootPath}/backup 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${hubRootPath}/backup 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "z ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
          "d ${sslCfg.sslDir} 0750 root nginx - -"
          "z ${sslCfg.sslDir} 0750 root nginx - -"
          "d /run/lx-annotate 0755 root root - -"
        ]
        ++ lib.optionals (!config.roles.endoreg-client.enable) [
          "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
        ];

      system.activationScripts.lxAnnotateRuntimePathMigration = ''
        hub_backup_dir="${hubRootPath}/backup"
        old_ssl_dir="/var/lib/lx-annotate/ssl"
        new_ssl_dir="${toString sslCfg.sslDir}"

        if [ -d "${hubRootPath}" ]; then
          ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} "$hub_backup_dir"
        fi

        if [ "$old_ssl_dir" != "$new_ssl_dir" ] && [ -d "$old_ssl_dir" ]; then
          ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g nginx "$new_ssl_dir"
          ${pkgs.findutils}/bin/find "$old_ssl_dir" -maxdepth 1 -type f -exec ${pkgs.coreutils}/bin/cp -n -- {} "$new_ssl_dir"/ \;
          ${pkgs.coreutils}/bin/chown -R root:nginx "$new_ssl_dir"
          [ -f "${toString sslCfg.keyPath}" ] && ${pkgs.coreutils}/bin/chmod 0640 "${toString sslCfg.keyPath}"
          [ -f "${toString sslCfg.certPath}" ] && ${pkgs.coreutils}/bin/chmod 0644 "${toString sslCfg.certPath}"
        fi
      '';

      systemd.services.lx-annotate-runtime-env = {
        description = "Prepare LuxNix runtime environment for lx-annotate";
        before = [
          "lx-annotate.service"
          "lx-annotate-master-key-check.service"
        ];
        after = [
          "systemd-tmpfiles-setup.service"
        ]
        ++ managedSecretsSetupUnits
        ++ localPostgresSetupUnits;
        wants = managedSecretsSetupUnits ++ localPostgresSetupUnits;
        requires = managedSecretsSetupUnits;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = "root";
          ExecStart = runtimeEnvScript;
          LogNamespace = lxAnnotateJournalNamespace;
        };
      };

      systemd.services.lx-annotate-feature-registry-guard = {
        description = "Attest LX-Annotate against the pinned EndoReg feature registry";
        wantedBy = [ "multi-user.target" ];
        before = [
          "lx-annotate.service"
          "lx-annotate-migrate.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
          "lx-annotate-preflight.service"
        ]
        ++ alwaysWorkerServiceUnits;
        after = [
          "lx-annotate-runtime-env.service"
          "systemd-tmpfiles-setup.service"
        ];
        wants = [ "lx-annotate-runtime-env.service" ];
        requires = [ "lx-annotate-runtime-env.service" ];
        restartTriggers = [
          effectiveRuntimePackage
          endoregFeatureRegistry
        ];
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
          WorkingDirectory = runtimeDataRootPath;
          EnvironmentFile = envSystemdFilePath;
          LogNamespace = lxAnnotateJournalNamespace;
          ExecStart = pkgs.writeShellScript "lx-annotate-feature-registry-guard" ''
            set -euo pipefail
            test -r ${lib.escapeShellArg "${featureRegistryPath}/manifest.json"}
            exec ${effectiveRuntimePackage}/bin/lx-annotate-manage shell -c ${lib.escapeShellArg ''
              import json
              from importlib.metadata import version

              expected = "${lxAnnotateEndoregDbVersion}"
              actual = version("endoreg-db")
              if actual != expected:
                  raise SystemExit(
                      f"endoreg-db version mismatch: installed={actual} lx-annotate={expected}"
                  )
              print(json.dumps({
                  "event": "endoreg.feature_registry_attested",
                  "endoreg_db_version": actual,
                  "feature_registry_revision": "${endoregDbRevision}",
                  "feature_registry_source_version": "${endoregDbVersion}",
                  "lx_annotate_revision": "${lxAnnotateRevision}",
                  "registry_path": "${featureRegistryPath}",
              }, sort_keys=True))
            ''}
          '';
          TimeoutStartSec = "10min";
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-data-recovery = mkIf cfg.dataRecovery.enable (mkLxAnnotateAppService {
        description = "Recover legacy LX-Annotate data into the runtime storage root";
        wantedBy = [ ];
        before = [
          "lx-annotate-migrate.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${runLocalDataRecoveryScript}/bin/runLxAnnotateDataRecovery";
          TimeoutStartSec = "2h";
        };
      });

      systemd.services.lx-annotate-migrate = mkLxAnnotateAppService {
        description = "Run LX-Annotate database migrations";
        before = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
          "lx-annotate.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput";
          TimeoutStartSec = "2h";
        };
      };

      systemd.services.lx-annotate-terminology-bootstrap = mkIf useWheelRuntime (mkLxAnnotateAppService {
        description = "Best-effort provisioning of LX-Annotate terminology";
        after = [ "lx-annotate.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = terminologyBootstrapScript;
          TimeoutStartSec = "10min";
        };
      });

      systemd.services.lx-annotate-load-base-data = mkLxAnnotateAppService {
        description = "Load LX-Annotate base data";
        after = [ "lx-annotate-migrate.service" ];
        wants = [ "lx-annotate-migrate.service" ];
        requires = [ "lx-annotate-migrate.service" ];
        before = [
          "lx-annotate-master-key-check.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = loadBaseDataServiceScript;
          TimeoutStartSec = "10min";
        };
      };

      systemd.services.lx-annotate-center-admin-bootstrap =
        mkIf (cfg.centerAdminBootstrap.username != null)
          (mkLxAnnotateAppService {
            description = "Bootstrap an authorized LX-Annotate center administrator";
            after = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
            ];
            wants = [ "lx-annotate-load-base-data.service" ];
            requires = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
            ];
            before = [ "lx-annotate.service" ];
            serviceConfig = {
              Type = "oneshot";
              RemainAfterExit = true;
              ExecStart = lib.escapeShellArgs [
                "${effectiveRuntimePackage}/bin/lx-annotate-manage"
                "bootstrap_center_admin"
                "--username"
                cfg.centerAdminBootstrap.username
              ];
              TimeoutStartSec = "5min";
            };
          });

      systemd.services.lx-annotate-hub-node-provisioning =
        mkIf cfg.hub.nodeProvisioning.enable
          (mkLxAnnotateAppService {
            description = "Idempotently provision LX-Annotate hub NetworkNode records";
            after = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
            ];
            wants = [ "lx-annotate-load-base-data.service" ];
            requires = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
            ];
            before = [
              "lx-annotate.service"
              "lx-annotate-celery-hub-transfer-worker.service"
            ];
            serviceConfig = {
              Type = "oneshot";
              RemainAfterExit = true;
              ExecStart = hubNodeProvisioningScript;
            };
          });

      systemd.services.lx-annotate-encrypted-data = mkIf cfg.runtime.managedEncryptedData.enable {
        description = "Unlock and mount encrypted data volume for lx-annotate";
        wantedBy = [ "multi-user.target" ];
        before = [ "lx-annotate.service" ];
        after = [ "systemd-tmpfiles-setup.service" ] ++ cfg.runtime.managedEncryptedData.after;
        requires = cfg.runtime.managedEncryptedData.requires;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = "root";
          Group = "root";
          ExecStart = "${lxAnnotateEncryptedDataMountScript}/bin/lx-annotate-encrypted-data-mount";
          ExecStop = "${lxAnnotateEncryptedDataUmountScript}/bin/lx-annotate-encrypted-data-umount";
          LogNamespace = lxAnnotateJournalNamespace;
          TimeoutStartSec = "2min";
          TimeoutStopSec = "2min";
        };
        path = [
          pkgs.coreutils
          pkgs.cryptsetup
          pkgs.util-linux
        ];
      };

      systemd.services.lx-annotate-filewatcher = mkLxAnnotateAppService {
        description = "Process pending LX-Annotate import files";
        wantedBy = [ ];
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [ "lx-annotate-load-base-data.service" ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-watch --once";
          Restart = "no";
        };
      };

      systemd.paths.lx-annotate-filewatcher = {
        description = "Trigger LX-Annotate file watcher when import files arrive";
        wantedBy = [ "multi-user.target" ];
        pathConfig = {
          PathChanged = [
            runtimeWatcherVideoDirPath
            runtimeWatcherReportDirPath
            runtimeWatcherPreanonymizedDirPath
          ];
          Unit = "lx-annotate-filewatcher.service";
          MakeDirectory = true;
        };
      };

      systemd.timers.lx-annotate-filewatcher = {
        description = "Periodically retry pending LX-Annotate import files";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "2m";
          OnUnitActiveSec = "5m";
          RandomizedDelaySec = "30s";
          Persistent = true;
          Unit = "lx-annotate-filewatcher.service";
        };
      };

      systemd.services.lx-annotate-hub-export-recovery =
        mkIf cfg.hub.outboundTransfer.enable
          (mkLxAnnotateAppService {
            description = "Dispatch bounded recovery for LX-Annotate outbound hub transfers";
            wantedBy = [ ];
            after = [
              "network-online.target"
              "lx-annotate-celery-hub-transfer-worker.service"
            ];
            wants = [
              "network-online.target"
              "lx-annotate-celery-hub-transfer-worker.service"
            ];
            serviceConfig = {
              Type = "oneshot";
              ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage dispatch_hub_export_recovery";
              TimeoutStartSec = "2m";
            };
          });

      systemd.timers.lx-annotate-hub-export-recovery = mkIf cfg.hub.outboundTransfer.enable {
        description = "Periodically recover LX-Annotate outbound hub transfers";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "5m";
          OnUnitActiveSec = cfg.hub.outboundTransfer.recoveryInterval;
          RandomizedDelaySec = "30s";
          Persistent = true;
          Unit = "lx-annotate-hub-export-recovery.service";
        };
      };

      systemd.services.lx-annotate-hub-export-health =
        mkIf cfg.hub.outboundTransfer.enable
          (mkLxAnnotateAppService {
            description = "Classify LX-Annotate outbound hub transfer health";
            wantedBy = [ ];
            after = [
              "lx-annotate-celery-hub-transfer-worker.service"
              "lx-annotate-hub-node-provisioning.service"
            ];
            wants = [ "lx-annotate-celery-hub-transfer-worker.service" ];
            serviceConfig = {
              Type = "oneshot";
              ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage check_hub_export_health";
              TimeoutStartSec = "2m";
            };
          });

      systemd.timers.lx-annotate-hub-export-health = mkIf cfg.hub.outboundTransfer.enable {
        description = "Alert on classified LX-Annotate hub transfer failures";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "7m";
          OnUnitActiveSec = cfg.hub.outboundTransfer.recoveryInterval;
          RandomizedDelaySec = "30s";
          Persistent = true;
          Unit = "lx-annotate-hub-export-health.service";
        };
      };

      systemd.services.lx-annotate-sap-import = mkLxAnnotateAppService {
        description = "Convert SAP IS-H zip drops into preanonymized watcher payload";
        wantedBy = [ ];
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [ "lx-annotate-load-base-data.service" ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = sapImportServiceScript;
        };
      };

      systemd.paths.lx-annotate-sap-import = {
        description = "Trigger SAP IS-H zip conversion when SAP drops exist";
        wantedBy = [ "multi-user.target" ];
        pathConfig = {
          PathExistsGlob = [ "${runtimeSapImportDirPath}/*.zip" ];
          Unit = "lx-annotate-sap-import.service";
          MakeDirectory = true;
        };
      };

      systemd.services.lx-annotate-export-frames = mkLxAnnotateAppService {
        description = "Export annotated frames for LX-Annotate";
        wantedBy = [ ];
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [ "lx-annotate-load-base-data.service" ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        environment = {
          LX_ANNOTATE_EXPORT_FRAMES_OUTPUT_DIR = "${runtimeStorageRootPath}/export/frames";
        };
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-export-frames";
        };
      };

      systemd.services.lx-annotate = {
        aliases = [ "lx-annotate-boot.service" ];
        wants = [
          "nginx.service"
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-preflight.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ localRedisServiceUnits
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
          "lx-annotate-preflight.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        after = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
          "lx-annotate-preflight.service"
          "endoreg-django-setup.service"
          "systemd-tmpfiles-setup.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ localRedisServiceUnits
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        unitConfig = encryptedDataMountUnitConfig;
        serviceConfig = {
          TimeoutStartSec = "5min";
          Restart = "on-failure";
          RestartSec = mkDefault 5;
          LogNamespace = lxAnnotateJournalNamespace;
          MemoryHigh = cfg.runtime.limits.memoryHigh;
          MemoryMax = cfg.runtime.limits.memoryMax;
          CPUQuota = cfg.runtime.limits.cpuQuota;
          Nice = 10;
          IOSchedulingClass = "best-effort";
          IOSchedulingPriority = 6;
          OOMScoreAdjust = 250;
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-master-key-check = {
        description = "Validate lx-annotate application master key against encrypted storage";
        wantedBy = [ "multi-user.target" ];
        before = [ "lx-annotate.service" ];
        after = [
          "systemd-tmpfiles-setup.service"
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
        ]
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-load-base-data.service"
        ]
        ++ localPostgresServiceUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
        ]
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        restartTriggers = [ effectiveRuntimePackage ];
        unitConfig = encryptedDataMountUnitConfig;
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
          WorkingDirectory = runtimeDataRootPath;
          ExecStart = "${runLocalMasterKeyCheckScript}/bin/runLocalMasterKeyCheck";
          EnvironmentFile = envSystemdFilePath;
          LogNamespace = lxAnnotateJournalNamespace;
          TimeoutStartSec = "10min";
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-preflight = {
        description = "Gate LX-Annotate web and workers on production runtime readiness";
        before = [ "lx-annotate.service" ] ++ alwaysWorkerServiceUnits;
        after = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ localPostgresServiceUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ]
        ++ dataRecoveryServiceUnits
        ++ hlsBackfillServiceUnits
        ++ hubNodeProvisioningServiceUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        restartTriggers = [ effectiveRuntimePackage ];
        unitConfig = encryptedDataMountUnitConfig;
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
          WorkingDirectory = runtimeDataRootPath;
          EnvironmentFile = envSystemdFilePath;
          LogNamespace = lxAnnotateJournalNamespace;
          ExecStart = pkgs.writeShellScript "lx-annotate-preflight" ''
            set -euo pipefail
            ${effectiveRuntimePackage}/bin/lx-annotate-manage check --fail-level CRITICAL
            ${effectiveRuntimePackage}/bin/lx-annotate-manage verify_encrypted_storage
            test -s ${lib.escapeShellArg "${packageStaticRoot}/.vite/manifest.json"}
          '';
          TimeoutStartSec = "10min";
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-video-streamable-migration = mkIf cfg.streamableMigration.enable {
        description = "Backfill LX-Annotate streamable video artifacts";
        wantedBy = [ ];
        after = [
          "systemd-tmpfiles-setup.service"
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ]
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-load-base-data.service"
        ]
        ++ localPostgresServiceUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ]
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        restartTriggers = [ effectiveRuntimePackage ];
        unitConfig = encryptedDataMountUnitConfig;
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];
          WorkingDirectory = runtimeDataRootPath;
          ExecStart = lib.escapeShellArgs [
            "${lxAnnotateMigrateVideoStreamableStorageScript}/bin/lx-annotate-migrate-video-streamable-storage"
          ];
          EnvironmentFile = envSystemdFilePath;
          TimeoutStartSec = "infinity";
          Nice = 15;
          IOSchedulingClass = "best-effort";
          IOSchedulingPriority = 6;
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-hls-materialization =
        mkIf cfg.hlsMaterialization.enable
          (mkLxAnnotateAppService {
            description = "Dispatch local encrypted HLS materialization for LX-Annotate videos";
            wantedBy = [ ];
            after = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
              ffmpegStreamThrottleWorkerUnit
            ];
            wants = [
              "lx-annotate-load-base-data.service"
              ffmpegStreamThrottleWorkerUnit
            ];
            requires = [
              "lx-annotate-load-base-data.service"
              "lx-annotate-master-key-check.service"
            ];
            serviceConfig = {
              Type = "oneshot";
              ExecStart = lib.escapeShellArgs (
                [
                  "${runLocalHlsMaterializationScript}/bin/runLxAnnotateHlsMaterialization"
                ]
                ++ cfg.hlsMaterialization.extraArgs
              );
              TimeoutStartSec = cfg.hlsMaterialization.timeoutStartSec;
              Nice = 15;
              IOSchedulingClass = "best-effort";
              IOSchedulingPriority = 6;
            };
          });

      systemd.services.lx-annotate-hls-backfill = mkIf cfg.hlsBackfill.enable (mkLxAnnotateAppService {
        description = "Dispatch local encrypted HLS backfill for LX-Annotate videos";
        wantedBy = [ "multi-user.target" ];
        before = [ "lx-annotate.service" ];
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [
          "lx-annotate-load-base-data.service"
        ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = lib.escapeShellArgs (
            [
              "${runLocalHlsMaterializationScript}/bin/runLxAnnotateHlsMaterialization"
            ]
            ++ cfg.hlsBackfill.extraArgs
          );
          TimeoutStartSec = cfg.hlsBackfill.timeoutStartSec;
          Nice = 15;
          IOSchedulingClass = "best-effort";
          IOSchedulingPriority = 6;
        };
      });

      systemd.services.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
        description = "Move duplicate anonymized lx-annotate payload into external archive storage";
        after = [
          "systemd-tmpfiles-setup.service"
        ]
        ++ encryptionServiceUnits;
        wants = encryptionServiceUnits;
        requires = encryptionServiceUnits;
        unitConfig = encryptedDataMountUnitConfig;
        serviceConfig = {
          Type = "oneshot";
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          WorkingDirectory = endoreg-service-user-home;
          ExecStart = "${dataCleanupScript}/bin/runLxAnnotateDataCleanup";
          ReadWritePaths = [
            endoreg-service-user-home
            envDataDir
            cfg.dataCleanup.archiveDir
            runtimeRootPath
            "/var/endoreg-service-user/lx-annotate"
            config.roles.endoreg-client.paths.storagePersistingMountPoint
          ];
        };
      };
      systemd.timers.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
        description = "Periodic duplicate cleanup for anonymized lx-annotate legacy storage";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "15m";
          OnCalendar = cfg.dataCleanup.onCalendar;
          Unit = "lx-annotate-data-cleanup.service";
        };
      };

      systemd.services.lx-annotate-emergency-storage-relief = mkIf cfg.storageRelief.enable {
        description = "Emergency lx-annotate storage relief to verified external archive";
        after = [
          "systemd-tmpfiles-setup.service"
          "lx-annotate-runtime-env.service"
        ]
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits

        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-runtime-env.service"
        ]

        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
        ]

        ++ encryptionServiceUnits;
        unitConfig = {
          RequiresMountsFor = [
            envDataDir
          ]
          ++ lib.optionals cfg.storageRelief.requireExternalMount [
            cfg.storageRelief.externalMountPoint
          ];
        };
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          WorkingDirectory = runtimeDataRootPath;
          ExecStart = "${emergencyStorageReliefScript}/bin/runLxAnnotateEmergencyStorageRelief";
          EnvironmentFile = envSystemdFilePath;
          TimeoutStartSec = "infinity";
          Nice = 19;
          IOSchedulingClass = "idle";
          OOMScoreAdjust = 900;
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = [
            endoreg-service-user-home
            envDataDir
            envConfDir
            runtimeRootPath
            cfg.storageRelief.externalMountPoint
          ];
        };
        path = [
          pkgs.coreutils
          pkgs.findutils
          pkgs.util-linux
        ];
      };
      systemd.timers.lx-annotate-emergency-storage-relief =
        mkIf (cfg.storageRelief.enable && cfg.storageRelief.timer.enable)
          {
            description = "Periodic emergency lx-annotate storage relief";
            wantedBy = [ "timers.target" ];
            timerConfig = {
              OnBootSec = "20m";
              OnCalendar = cfg.storageRelief.timer.onCalendar;
              Unit = "lx-annotate-emergency-storage-relief.service";
            };
          };

      systemd.services.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
        description = "Create coupled PostgreSQL and protected lx-annotate hub runtime snapshots";
        after = [
          "lx-annotate.service"
          "postgresqlBackup.service"
        ] ++ encryptionServiceUnits;
        wants = [ "lx-annotate.service" ] ++ encryptionServiceUnits;
        requires = [ "postgresqlBackup.service" ] ++ encryptionServiceUnits;
        unitConfig = encryptedDataMountUnitConfig;
        serviceConfig = {
          Type = "oneshot";
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          WorkingDirectory = runtimeDataRootPath;
          ExecStart = "${runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
          LoadCredential = [
            "hub-postgresql.sql.gz:${config.services.postgresqlBackup.location}/all.sql.gz"
          ];
          ReadWritePaths = [
            envDataDir
            cfg.hub.backup.incomingDir
            cfg.hub.backup.snapshotDir
            cfg.hub.backup.manifestDir
            runtimeRootPath
          ];
        };
        path = [
          pkgs.coreutils
          pkgs.findutils
          pkgs.gzip
          pkgs.jq
          pkgs.rsync
        ];
      };
      systemd.timers.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
        description = "Periodic protected snapshots for the lx-annotate hub node";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "10m";
          OnCalendar = cfg.hub.backup.onCalendar;
          Unit = "lx-annotate-hub-backup.service";
        };
      };

      systemd.services.lx-annotate-acceptance = {
        description = "Run LX-Annotate live web, worker, storage, and static acceptance checks";
        after = [
          "lx-annotate-preflight.service"
          "lx-annotate.service"
          "nginx.service"
        ]
        ++ alwaysWorkerServiceUnits
        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-preflight.service"
          "lx-annotate.service"
          "nginx.service"
        ]
        ++ alwaysWorkerServiceUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-preflight.service"
          "lx-annotate.service"
          "nginx.service"
        ]
        ++ alwaysWorkerServiceUnits
        ++ encryptionServiceUnits;
        unitConfig = encryptedDataMountUnitConfig;
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          User = endoreg-service-user-name;
          Group = endoreg-service-group-name;
          WorkingDirectory = runtimeDataRootPath;
          EnvironmentFile = envSystemdFilePath;
          ExecStart = pkgs.writeShellScript "lx-annotate-acceptance" ''
            set -euo pipefail
            ${effectiveRuntimePackage}/bin/lx-annotate-manage check --fail-level CRITICAL
            ${effectiveRuntimePackage}/bin/lx-annotate-manage verify_encrypted_storage
            required_workers=( ${lib.concatMapStringsSep " " lib.escapeShellArg alwaysWorkerServiceUnits} )
            for worker_unit in "''${required_workers[@]}"; do
              ${pkgs.systemd}/bin/systemctl is-active --quiet "$worker_unit"
            done
            ${pkgs.curl}/bin/curl --fail --silent --show-error \
              --cacert "${publicSslCertificatePath}" \
              --resolve "${cfg.django.hostname}:443:127.0.0.1" \
              "https://${cfg.django.hostname}/static/.vite/manifest.json" >/dev/null
          '';
          ReadWritePaths = appReadWritePaths;
        };
      };

      systemd.services.lx-annotate-ffmpeg-stream-throttle = mkIf cfg.runtime.ffmpegStreamThrottle.enable {
        description = "Apply stream-aware runtime throttling to the LX-Annotate FFmpeg worker";
        after = [
          "lx-annotate-runtime-env.service"
          "lx-annotate-migrate.service"
          ffmpegStreamThrottleWorkerUnit
        ]
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        wants = [
          "lx-annotate-runtime-env.service"
        ]
        ++ localPostgresServiceUnits
        ++ localPostgresSetupUnits
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        requires = [
          "lx-annotate-runtime-env.service"
        ]
        ++ managedSecretsSetupUnits
        ++ encryptionServiceUnits;
        unitConfig = encryptedDataMountUnitConfig;
        environment = commonExtraEnv;
        serviceConfig = {
          Type = "oneshot";
          WorkingDirectory = runtimeDataRootPath;
          EnvironmentFile = envSystemdFilePath;
          ExecStart = ffmpegStreamThrottleScript;
          ProtectSystem = "full";
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = appReadWritePaths ++ [ "/run/lx-annotate" ];
        };
        path = [
          pkgs.coreutils
          pkgs.systemd
        ];
      };

      systemd.timers.lx-annotate-ffmpeg-stream-throttle = mkIf cfg.runtime.ffmpegStreamThrottle.enable {
        description = "Periodically reconcile stream-aware FFmpeg worker throttling";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = cfg.runtime.ffmpegStreamThrottle.interval;
          OnUnitActiveSec = cfg.runtime.ffmpegStreamThrottle.interval;
          AccuracySec = "10s";
          Unit = "lx-annotate-ffmpeg-stream-throttle.service";
        };
      };

      systemd.services.lx-annotate-ffmpeg-stream-throttle-reset =
        mkIf (!cfg.runtime.ffmpegStreamThrottle.enable)
          {
            description = "Reset runtime controls left by LX-Annotate FFmpeg stream throttling";
            wantedBy = [ "multi-user.target" ];
            after = [ ffmpegStreamThrottleWorkerUnit ];
            serviceConfig = {
              Type = "oneshot";
              RemainAfterExit = true;
              ExecStart = ffmpegStreamThrottleResetScript;
              ProtectSystem = "full";
              PrivateTmp = true;
              NoNewPrivileges = true;
              ReadWritePaths = [ "/run/lx-annotate" ];
            };
          };

      systemd.services.move-my-files = mkIf config.services.luxnix.fileMover.enable {
        after = mkAfter [ "lx-annotate-runtime-env.service" ];
        wants = mkAfter [ "lx-annotate-runtime-env.service" ];
      };

      systemd.services.nginx.serviceConfig = {
        Nice = -5;
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 0;
        OOMScoreAdjust = -500;
      };
    }
    workerSubservice
  ]);
}
