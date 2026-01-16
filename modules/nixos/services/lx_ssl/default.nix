{ config, lib, pkgs, ... }:

with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.lxSsl;
  annotateCfg = config.services.luxnix.lxAnnotateLocal;

  sslDir = cfg.sslDir;
  sslKeyPath = cfg.keyPath;
  sslCertPath = cfg.certPath;
in {
  options.services.luxnix.lxSsl = {
    enable = mkBoolOpt false "Enable self-signed SSL generation for lx-annotate.";

    sslDir = mkOption {
      type = types.path;
      default = "/var/lib/lx-annotate/ssl";
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
  };

  config = mkIf cfg.enable {
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
        chmod 700 ${sslDir}

        if [ ! -f "${sslKeyPath}" ] || [ ! -f "${sslCertPath}" ]; then
          echo "Generating fresh self-signed SSL certificate..."
          ${pkgs.openssl}/bin/openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "${sslKeyPath}" \
            -out "${sslCertPath}" \
            -subj "/CN=${annotateCfg.django.hostname}"

          chmod 600 "${sslKeyPath}"
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
  };
}
