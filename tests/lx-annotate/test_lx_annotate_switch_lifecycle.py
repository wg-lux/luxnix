"""Startup preparation must survive a NixOS switch's stop phase.

A switch stops changed units before activation and daemon-reload. Timer and
path triggers that fire in that window queue jobs from the outgoing generation.
If preparation was inactive, those jobs re-ran it from the outgoing generation;
it then failed the new release check and failed every start job the switch had
merged into it, leaving the web service down after the switch.
"""

from nix_eval_helpers import eval_json


# Periodic repair unit upstream of the runtime environment. It does not use the
# wheel and keeps its own timer, which an active RemainAfterExit unit would
# turn into a no-op.
PERIODIC_PREREQUISITES = {"lx-annotate-identity-salts.service"}

EXPECTED_PREPARATION_UNITS = {
    "lx-annotate-runtime-env.service",
    "lx-annotate-wheel-runtime.service",
    "lx-annotate-migrate.service",
    "lx-annotate-load-base-data.service",
    "lx-annotate-master-key-check.service",
    "lx-dtypes-kb-bootstrap.service",
    "lx-annotate-hub-node-provisioning.service",
    "lx-annotate-hub-envelope-key-preflight.service",
}


def _units() -> dict:
    return eval_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = flake.nixosConfigurations.gc-10.config;
          owned = name: builtins.match "(lx-annotate.*|lx-dtypes.*)" name != null;
          names = builtins.filter owned (builtins.attrNames cfg.systemd.services);
          select = name: let s = cfg.systemd.services.${name}; in {
            inherit (s) requires wantedBy stopIfChanged;
            type = s.serviceConfig.Type or "simple";
            remainAfterExit = s.serviceConfig.RemainAfterExit or false;
            unitText = cfg.systemd.units."${name}.service".text;
          };
        in builtins.listToAttrs (map (name: {
          name = "${name}.service";
          value = select name;
        }) names)
        """
    )


def _long_running(units: dict) -> list[str]:
    return [
        name
        for name, unit in units.items()
        if unit["type"] != "oneshot" and "multi-user.target" in unit["wantedBy"]
    ]


def _required_closure(units: dict, roots: list[str]) -> set[str]:
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        for dependency in units[pending.pop()]["requires"]:
            if dependency in units and dependency not in seen:
                seen.add(dependency)
                pending.append(dependency)
    return seen


def _preparation_closure(units: dict) -> set[str]:
    closure = _required_closure(units, _long_running(units))
    return {name for name in closure if units[name]["type"] == "oneshot"}


def test_preparation_chain_matches_documented_units() -> None:
    closure = _preparation_closure(_units())

    assert closure - PERIODIC_PREREQUISITES == EXPECTED_PREPARATION_UNITS


def test_preparation_units_stay_active_and_restart_after_reload() -> None:
    units = _units()

    for name in EXPECTED_PREPARATION_UNITS:
        unit = units[name]
        assert unit["remainAfterExit"] is True, name
        assert unit["stopIfChanged"] is False, name
        assert "X-StopIfChanged=false" in unit["unitText"], name


def test_application_units_restart_with_wheel_preparation() -> None:
    units = _units()
    # The request throttle is a socket proxy that does not run wheel code.
    application = [
        name
        for name in _long_running(units)
        if name != "lx-annotate-request-throttle.service"
    ]

    assert "lx-annotate.service" in application
    for name in application:
        closure = _required_closure(units, [name])
        assert "lx-annotate-wheel-runtime.service" in closure, name
