"""Evaluate browser trust against the actual server publication contract."""

import os
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


@pytest.fixture(scope="module")
def tls_config():
    result = eval_json('''
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        home = flake.homeConfigurations."admin@gc-02".config;
        host = (flake.inputs.nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          specialArgs.lib = flake.inputs.nixpkgs.lib.extend (_: previous: {
            luxnix = import (builtins.toPath "__REPO__/lib/module") { lib = previous; };
          });
          modules = [
            (builtins.toPath "__REPO__/modules/nixos/services/lx_ssl")
            ({ lib, ... }: {
              options.services.luxnix.lxAnnotateLocal = lib.mkOption {
                default.django.hostname = "lx-annotate.local";
                type = lib.types.attrs;
              };
              config.services.luxnix.lxSsl.enable = true;
            })
          ];
        }).config;
      in {
        enabled = home.programs.firefox.enable;
        installed = home.programs.firefox.policies.Certificates.Install;
        published = toString host.services.luxnix.lxSsl.publicCertPath;
        generator = host.systemd.services.generate-lx-ssl.script;
        ordering = host.systemd.services.generate-lx-ssl.before;
      }
    '''.replace("__REPO__", str(REPO_ROOT)))
    return result


def test_firefox_imports_the_local_server_public_certificate(tls_config):
    result = tls_config
    assert result["enabled"]
    assert result["installed"] == [result["published"]]
    assert 'install -m 0644' in result["generator"]
    assert result["published"] in result["generator"]
    assert "nginx.service" in result["ordering"]


def test_firefox_certificate_list_can_be_replaced_or_disabled():
    result = eval_json('''
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        evaluate = certificates:
          (flake.inputs.home-manager.lib.homeManagerConfiguration {
            pkgs = flake.homeConfigurations."admin@gc-02".pkgs;
            modules = [
              (__LUXNIX_MODULE__)
              {
                home.username = "test";
                home.homeDirectory = "/home/test";
                home.stateVersion = "26.05";
                browsers.firefox.enable = true;
                browsers.firefox.certificateFiles = certificates;
              }
            ];
          }).config.programs.firefox.policies.Certificates.Install;
      in {
        disabled = evaluate [];
        custom = evaluate ["/etc/site-pki/ca.pem"];
      }
    '''.replace("__LUXNIX_MODULE__", str(REPO_ROOT / "modules/home/browsers/firefox")))
    assert result == {"disabled": [], "custom": ["/etc/site-pki/ca.pem"]}


@pytest.mark.parametrize("legacy_ca", [False, True])
def test_generated_certificate_is_a_server_identity(tls_config, tmp_path, legacy_ca):
    ssl_dir = tmp_path / "private"
    ssl_dir.mkdir()
    public = tmp_path / "public.crt"
    cert = ssl_dir / "lx-annotate-selfsigned.crt"
    key = ssl_dir / "lx-annotate-selfsigned.key"

    def run(*args):
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout

    if legacy_ca:
        run("openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-days", "365", "-keyout", str(key), "-out", str(cert),
            "-subj", "/CN=lx-annotate.local",
            "-addext", "subjectAltName=DNS:lx-annotate.local",
            "-addext", "basicConstraints=critical,CA:TRUE")
    script = (tls_config["generator"]
              .replace("/var/lib/lx-annotate-ssl", str(ssl_dir))
              .replace(tls_config["published"], str(public))
              .replace("root:nginx", f"{os.getuid()}:{os.getgid()}"))
    assert "certificate_generated" in run("bash", "-c", script)
    extensions = run("openssl", "x509", "-in", str(cert), "-noout", "-text")
    assert "CA:FALSE" in extensions
    assert "TLS Web Server Authentication" in extensions
    run("openssl", "verify", "-CAfile", str(cert), "-purpose", "sslserver",
        "-verify_hostname", "lx-annotate.local", str(cert))
    assert public.read_bytes() == cert.read_bytes()
    original = cert.read_bytes(), key.read_bytes()
    assert "certificate_valid" in run("bash", "-c", script)
    assert original == (cert.read_bytes(), key.read_bytes())
    assert key.stat().st_mode & 0o777 == 0o640
