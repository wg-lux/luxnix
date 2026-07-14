{
  config,
  lib,
  pkgs,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.lxSsl;
  annotateCfg = config.services.luxnix.lxAnnotateLocal;

  sslDir = cfg.sslDir;
  sslKeyPath = cfg.keyPath;
  sslCertPath = cfg.certPath;
  trustStoreCfg = cfg.trustStore;
  useTrustFile = trustStoreCfg.certificateFile != null;
  useTrustPem = trustStoreCfg.certificatePem != null;
  trustFilePath = toString trustStoreCfg.certificateFile;
  generatedCertPath = toString sslCertPath;
  certificateDnsNames = lib.unique ([ annotateCfg.django.hostname ] ++ cfg.extraDnsNames);
  certificateSubjectAltName = lib.concatMapStringsSep "," (name: "DNS:${name}") certificateDnsNames;
in
{
  options.services.luxnix.lxSsl = {
    enable = mkBoolOpt false "Enable self-signed SSL generation for lx-annotate.";

    sslDir = mkOption {
      type = types.path;
      default = "/var/lib/lx-annotate-ssl";
      description = "Directory where lx-annotate SSL assets are stored.";
    };

    keyPath = mkOption {
      type = types.path;
      default = "${sslDir}/lx-annotate-selfsigned.key";
      readOnly = true;
      description = "Path to the generated private key.";
    };

    certPath = mkOption {
      type = types.path;
      default = "${sslDir}/lx-annotate-selfsigned.crt";
      readOnly = true;
      description = "Path to the generated certificate.";
    };

    extraDnsNames = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Additional DNS subjectAltName entries for the generated certificate.";
    };

    trustStore = {
      enable = mkBoolOpt false "Add a local CA certificate for lx-annotate to the system trust store.";

      certificateFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        example = literalExpression "./certs/lx-annotate-local-ca.pem";
        description = ''
          Path to a PEM-encoded CA certificate file. Prefer a file that is tracked in this
          repository. Do not point to the runtime-generated certificate under
          ${sslDir}.
        '';
      };

      certificatePem = mkOption {
        type = types.nullOr types.lines;
        default = null;
        description = ''
          PEM-encoded CA certificate content added directly to the system trust store.
        '';
      };
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      systemd.services."generate-lx-ssl" = {
        description = "Generate Self-Signed SSL for LxAnnotate if missing";
        requiredBy = [ "nginx.service" ];
        before = [ "nginx.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          set -euo pipefail
          umask 027

          mkdir -p ${sslDir}
          chown root:nginx ${sslDir}
          chmod 750 ${sslDir}

          certificate_valid=true
          if [ ! -s "${sslKeyPath}" ] || [ ! -s "${sslCertPath}" ] \
            || ! ${pkgs.openssl}/bin/openssl x509 -in "${sslCertPath}" -noout -checkend 86400; then
            certificate_valid=false
          fi
          ${lib.concatMapStringsSep "\n" (name: ''
            if [ "$certificate_valid" = true ] \
              && ! ${pkgs.openssl}/bin/openssl x509 -in "${sslCertPath}" -noout -checkhost ${lib.escapeShellArg name}; then
              certificate_valid=false
            fi
          '') certificateDnsNames}

          if [ "$certificate_valid" != true ]; then
            key_tmp="$(${pkgs.coreutils}/bin/mktemp "${sslDir}/.lx-ssl-key.XXXXXX")"
            cert_tmp="$(${pkgs.coreutils}/bin/mktemp "${sslDir}/.lx-ssl-cert.XXXXXX")"
            cleanup() {
              rm -f "$key_tmp" "$cert_tmp"
            }
            trap cleanup EXIT
            ${pkgs.openssl}/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
              -keyout "$key_tmp" \
              -out "$cert_tmp" \
              -subj "/CN=${annotateCfg.django.hostname}" \
              -addext ${lib.escapeShellArg "subjectAltName=${certificateSubjectAltName}"}

            chown root:nginx "$key_tmp" "$cert_tmp"
            chmod 640 "$key_tmp"
            chmod 644 "$cert_tmp"
            mv -f "$key_tmp" "${sslKeyPath}"
            mv -f "$cert_tmp" "${sslCertPath}"
            trap - EXIT
            printf '{"event":"lx_ssl.certificate_generated","common_name":"%s"}\n' ${lib.escapeShellArg annotateCfg.django.hostname}
          else
            printf '{"event":"lx_ssl.certificate_valid","common_name":"%s"}\n' ${lib.escapeShellArg annotateCfg.django.hostname}
          fi
        '';
      };

      services.nginx.virtualHosts."${annotateCfg.django.hostname}" = {
        forceSSL = mkDefault true;
        sslCertificate = mkDefault sslCertPath;
        sslCertificateKey = mkDefault sslKeyPath;
      };
    }

    (mkIf trustStoreCfg.enable {
      assertions = [
        {
          assertion = useTrustFile || useTrustPem;
          message = "services.luxnix.lxSsl.trustStore.enable requires either trustStore.certificateFile or trustStore.certificatePem.";
        }
        {
          assertion = !(useTrustFile && useTrustPem);
          message = "services.luxnix.lxSsl.trustStore: set exactly one of certificateFile or certificatePem.";
        }
        {
          assertion = !(useTrustFile && trustFilePath == generatedCertPath);
          message = ''
            services.luxnix.lxSsl.trustStore.certificateFile must not point to ${generatedCertPath}.
            That file is runtime-generated. Use a certificate file from this repository or certificatePem.
          '';
        }
      ];
    })

    (mkIf (trustStoreCfg.enable && useTrustFile) {
      security.pki.certificateFiles = [ trustStoreCfg.certificateFile ];
    })

    (mkIf (trustStoreCfg.enable && useTrustPem) {
      security.pki.certificates = [ trustStoreCfg.certificatePem ];
    })
  ]);
}
