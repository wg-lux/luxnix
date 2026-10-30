"""Evaluate monitoring port wiring independently of the retired Promtail service."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_monitoring_proxies_follow_effective_listener_ports() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        nixpkgs = flake.inputs.nixpkgs;
        lib = nixpkgs.lib.extend (final: _: {
          luxnix = import ./lib/module/default.nix { lib = final; };
        });
        evaluate = overrides:
          let
            cfg = (lib.evalModules {
              specialArgs = { inherit lib; };
              modules = [
                # The pinned NixOS release removed Promtail. This harness tests
                # the real stack module's wiring, not deployment compatibility.
                ({ lib, ... }: {
                  options = {
                    sops.secrets = lib.mkOption {
                      type = lib.types.attrsOf lib.types.anything;
                    };
                    services = lib.genAttrs
                      [ "traefik" "loki" "promtail" "postgresql" "grafana" ]
                      (_: lib.mkOption {
                        type = lib.types.attrsOf lib.types.anything;
                      }) // {
                        prometheus = lib.mkOption {
                          type = lib.types.submodule {
                            freeformType = lib.types.attrsOf lib.types.anything;
                            options.alertmanager = lib.mkOption {
                              type = lib.types.submodule {
                                freeformType = lib.types.attrsOf lib.types.anything;
                                options.port = lib.mkOption {
                                  type = lib.types.port;
                                  default = 9093;
                                };
                              };
                            };
                          };
                        };
                      };
                  };
                })
                ./modules/nixos/services/monitoring/default.nix
                { services.luxnix.monitoring.enable = true; }
                overrides
              ];
            }).config;
          in {
            ports = {
              prometheus = cfg.services.prometheus.port;
              grafana = cfg.services.grafana.settings.server.http_port;
              promtail = cfg.services.promtail.configuration.server.http_listen_port;
              alertmanager = cfg.services.prometheus.alertmanager.port;
            };
            upstreams = lib.mapAttrs (_: service:
              (builtins.head service.loadBalancer.servers).url
            ) cfg.services.traefik.dynamicConfigOptions.http.services;
          };
      in {
        defaults = evaluate {};
        overrides = evaluate {
          services.prometheus.port = lib.mkForce 13020;
          services.grafana.settings.server.http_port = lib.mkForce 13010;
          services.promtail.configuration.server.http_listen_port = lib.mkForce 13031;
          services.prometheus.alertmanager.port = 19093;
        };
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    cases = json.loads(result.stdout)
    defaults = {
        "prometheus": 3020,
        "grafana": 3010,
        "promtail": 3031,
        "alertmanager": 9093,
    }
    for name, offset in (("defaults", 0), ("overrides", 10000)):
        ports = {service: port + offset for service, port in defaults.items()}
        assert cases[name] == {
            "ports": ports,
            "upstreams": {
                service: f"http://localhost:{port}" for service, port in ports.items()
            },
        }
