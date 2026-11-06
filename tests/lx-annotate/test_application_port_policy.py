"""Evaluate the application listener and every proxy consumer of its port."""

from nix_eval_helpers import eval_json, eval_result


def test_application_port_alias_and_consumers() -> None:
    cases = eval_json("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        lib = flake.inputs.nixpkgs.lib;
        inspect = host: let
          cfg = host.config;
          app = cfg.services.luxnix.lxAnnotateLocal;
          locations = cfg.services.nginx.virtualHosts.${app.django.hostname}.locations;
        in {
          role = cfg.roles.endoreg-client.api.port;
          service = app.django.port;
          listener = cfg.services.lx-annotate.port;
          environment = cfg.services.lx-annotate.extraEnv.DJANGO_PORT;
          proxies = lib.mapAttrs (_: location: location.proxyPass)
            (lib.filterAttrs (_: location: location.proxyPass != null) locations);
        };
        evaluate = overrides: inspect (flake.nixosConfigurations.gc-02.extendModules {
          modules = [ overrides ];
        });
      in {
        defaults = lib.mapAttrs (_: inspect) (lib.filterAttrs (_: host:
          host.config.services.luxnix.lxAnnotateLocal.enable
        ) flake.nixosConfigurations);
        role = evaluate { roles.endoreg-client.api.port = 8222; };
        service = evaluate { services.luxnix.lxAnnotateLocal.django.port = 8333; };
        equal = evaluate {
          roles.endoreg-client.api.port = 8444;
          services.luxnix.lxAnnotateLocal.django.port = 8444;
        };
      }
    """)
    assert "gc-02" in cases["defaults"] and "gs-02" in cases["defaults"]
    expected = [(case, 8117) for case in cases["defaults"].values()]
    expected += [
        (cases[name], port)
        for name, port in (("role", 8222), ("service", 8333), ("equal", 8444))
    ]
    for case, port in expected:
        assert case["role"] == case["service"] == case["listener"] == port
        assert case["environment"] == str(port)
        assert "/" in case["proxies"]
        assert "/api/media/videos/" in case["proxies"]
        assert set(case["proxies"].values()) == {f"http://127.0.0.1:{port}"}


def test_conflicting_application_port_names_fail_evaluation() -> None:
    result = eval_result("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        host = flake.nixosConfigurations.gc-02.extendModules {
          modules = [{
            roles.endoreg-client.api.port = 8222;
            services.luxnix.lxAnnotateLocal.django.port = 8333;
          }];
        };
      in host.config.services.luxnix.lxAnnotateLocal.django.port
    """)
    assert result.returncode != 0
    assert "conflicting definition values" in result.stderr
    assert "lxAnnotateLocal.django.port" in result.stderr
