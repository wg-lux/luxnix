"""Evaluate browser trust against the actual server publication contract."""

from nix_eval_helpers import REPO_ROOT, eval_json


def test_firefox_imports_the_local_server_public_certificate():
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
