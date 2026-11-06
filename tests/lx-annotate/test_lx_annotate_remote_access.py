from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from nix_eval_helpers import eval_json as _nix_eval_expr_json

_REMOTE_ACCESS_MODULE = """
  services.luxnix.lxAnnotateLocal.remoteAccess = {
    machines = [
      {
        key = "gs-02";
        displayName = "gs-02 central hub";
        baseUrl = "https://gs-02.intern";
        deploymentRole = "central_hub";
      }
    ];
    restrictToVpn = {
      enable = true;
      allowedClientCidrs = [ "172.16.255.0/24" ];
    };
  };
"""


def _eval_gs_02(module: str, expression: str) -> Any:
    return _nix_eval_expr_json(
        f"""
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = (flake.nixosConfigurations.gs-02.extendModules {{
            modules = [ ({{ ... }}: {{ {module} }}) ];
          }}).config;
        in {expression}
        """
    )


@lru_cache(maxsize=None)
def _restricted_gs_02() -> dict[str, Any]:
    return _eval_gs_02(
        _REMOTE_ACCESS_MODULE,
        """
        let
          vhost = cfg.services.nginx.virtualHosts.${cfg.services.luxnix.lxAnnotateLocal.django.hostname};
        in {
          vhostConfig = vhost.extraConfig;
          browserLocation = vhost.locations."/".extraConfig;
          transferLocation = vhost.locations."/endoreg-api/media/hub/transfers/".extraConfig;
          env = cfg.systemd.services.lx-annotate.environment.LX_ANNOTATE_REMOTE_MACHINES or null;
          failedAssertions = map (a: a.message) (builtins.filter (a: !a.assertion) cfg.assertions);
        }
        """,
    )


def test_remote_machines_render_typed_environment() -> None:
    rendered = _restricted_gs_02()["env"]

    assert json.loads(rendered) == [
        {
            "key": "gs-02",
            "display_name": "gs-02 central hub",
            "base_url": "https://gs-02.intern",
            "deployment_role": "central_hub",
        }
    ]


def test_vpn_restriction_limits_browser_vhost_to_allowed_cidrs() -> None:
    contract = _restricted_gs_02()

    assert "allow 172.16.255.0/24;" in contract["vhostConfig"]
    assert "deny all;" in contract["vhostConfig"]
    assert "allow all;" not in contract["browserLocation"]
    assert not [
        message
        for message in contract["failedAssertions"]
        if "remoteAccess" in message
    ]


def test_vpn_restriction_keeps_transfer_api_behind_mtls_only() -> None:
    transfer = _restricted_gs_02()["transferLocation"]

    assert "allow all;" in transfer
    assert "if ($ssl_client_verify != SUCCESS)" in transfer
    assert transfer.index("$ssl_client_verify != SUCCESS") < transfer.index("allow all;")


def test_remote_access_is_inactive_by_default() -> None:
    contract = _eval_gs_02(
        "",
        """
        let
          vhost = cfg.services.nginx.virtualHosts.${cfg.services.luxnix.lxAnnotateLocal.django.hostname};
        in {
          hasEnv = cfg.systemd.services.lx-annotate.environment ? LX_ANNOTATE_REMOTE_MACHINES;
          deniesAll = builtins.match ".*deny all;.*" vhost.extraConfig != null;
        }
        """,
    )

    assert contract == {"hasEnv": False, "deniesAll": False}


def test_vpn_restriction_requires_explicit_cidrs() -> None:
    failed = _eval_gs_02(
        "services.luxnix.lxAnnotateLocal.remoteAccess.restrictToVpn.enable = true;",
        "map (a: a.message) (builtins.filter (a: !a.assertion) cfg.assertions)",
    )

    assert any("allowedClientCidrs" in message for message in failed)
