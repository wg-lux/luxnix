"""Evaluate Redis endpoint propagation through the real NixOS modules."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_redis_proxy_and_firewall_follow_effective_server_port() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        nixpkgs = flake.inputs.nixpkgs;
        lib = nixpkgs.lib.extend (final: _: {
          luxnix = import ./lib/module/default.nix { lib = final; };
        });
        evaluate = overrides:
          let
            cfg = (import (nixpkgs + "/nixos/lib/eval-config.nix") {
              system = "x86_64-linux";
              specialArgs = { inherit lib; };
              modules = [
                ./modules/nixos/luxnix/generic-settings/network/default.nix
                ./modules/nixos/services/redis/default.nix
                { services.luxnix.redis.enable = true; }
                overrides
              ];
            }).config;
          in {
            inherit (cfg.services.redis.servers.main) port bind openFirewall;
            backend = (builtins.head
              cfg.services.traefik.dynamicConfigOptions.tcp.services.redis.loadBalancer.servers
            ).address;
            firewall = cfg.networking.firewall.allowedTCPPorts;
          };
      in {
        defaults = evaluate {};
        policy = evaluate { luxnix.generic-settings.network.redis.port = 6390; };
        forced = evaluate { services.redis.servers.main.port = lib.mkForce 6391; };
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
    for name, port in (("defaults", 6380), ("policy", 6390), ("forced", 6391)):
        assert cases[name] == {
            "port": port,
            "bind": "0.0.0.0",
            "openFirewall": True,
            "backend": f"127.0.0.1:{port}",
            "firewall": [port],
        }
