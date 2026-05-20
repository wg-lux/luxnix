{ config, lib, pkgs, ... }:

with lib;
with lib.luxnix; let
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
          mkdir -p ${sslDir}
          chown root:nginx ${sslDir}
          chmod 750 ${sslDir}

          if [ ! -f "${sslKeyPath}" ] || [ ! -f "${sslCertPath}" ]; then
            echo "Generating fresh self-signed SSL certificate..."
            ${pkgs.openssl}/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
              -keyout "${sslKeyPath}" \
              -out "${sslCertPath}" \
              -subj "/CN=${annotateCfg.django.hostname}"

            chown root:nginx "${sslKeyPath}" "${sslCertPath}"
            chmod 640 "${sslKeyPath}"
            chmod 644 "${sslCertPath}"
            echo "SSL generation complete."
          else
            echo "SSL certificate already exists. Skipping generation."
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
