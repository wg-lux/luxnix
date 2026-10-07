"""Cache-friendly OBS selection must preserve recording and GPU configuration."""

from functools import lru_cache
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def contract():
    expression = """
      let
        f = builtins.getFlake "git+file://__ROOT__";
        lib = f.inputs.nixpkgs.lib;
        h = f.nixosConfigurations.gc-02;
        c = h.config;
        selected = c.programs.obs-studio.package;
        original = h.pkgs.obs-studio;
        stock = (import f.inputs.nixpkgs {
          system = "x86_64-linux"; config.allowUnfree = true;
        }).obs-studio;
      in {
        usesStock = selected.drvPath == stock.drvPath;
        sameFeatures = selected.cmakeFlags == original.cmakeFlags;
        sameDependencies =
          map toString selected.buildInputs == map toString original.buildInputs;
        sameDriverFixup = selected.postFixup == original.postFixup;
        hasDriverFixup = lib.hasInfix "addDriverRunpath" selected.postFixup;
        cuda = h.pkgs.config.cudaSupport;
        prime = c.hardware.nvidia.prime.sync.enable;
        plasma = c.services.desktopManager.plasma6.enable;
        waylandGreeter = c.services.displayManager.sddm.wayland.enable;
        session = c.services.displayManager.defaultSession;
        overrideWorks = (h.extendModules { modules = [{
          programs.obs-studio.package = stock;
        }]; }).config.programs.obs-studio.package.drvPath == stock.drvPath;
        defaultCachesOnly = (h.extendModules { modules = [{
          luxnix.generic-settings.nix = {
            extraSubstituters = lib.mkForce [];
            extraTrustedPublicKeys = lib.mkForce [];
          };
        }]; }).config.nix.settings.substituters;
        hosts = lib.mapAttrs (_: host: {
          caches = host.config.nix.settings.substituters;
          keys = host.config.nix.settings.trusted-public-keys;
        }) f.nixosConfigurations;
        caches = (import (f.outPath + "/flake.nix")).nixConfig.extra-substituters;
        keys = (import (f.outPath + "/flake.nix")).nixConfig.extra-trusted-public-keys;
      }
    """.replace("__ROOT__", str(ROOT))
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_obs_reuses_stock_derivation_without_changing_features():
    data = contract()
    for field in (
        "usesStock",
        "sameFeatures",
        "sameDependencies",
        "sameDriverFixup",
        "hasDriverFixup",
        "overrideWorks",
    ):
        assert data[field], field


def test_obs_optimization_preserves_gpu_and_wayland_configuration():
    data = contract()
    assert data["cuda"] and data["prime"]
    assert data["plasma"] and data["waylandGreeter"]
    assert data["session"] == "plasma"


def test_fleet_and_flake_use_matching_current_cuda_cache():
    data = contract()
    for config in [data, *data["hosts"].values()]:
        assert "https://cache.nixos-cuda.org" in config["caches"]
        assert (
            "cache.nixos-cuda.org:74DUi4Ye579gUqzH4ziL9IyiJBlDpMRn9MBN8oNan9M="
            in config["keys"]
        )
        assert not any(
            "cuda-maintainers.cachix.org" in value
            for value in config["caches"] + config["keys"]
        )


def test_empty_extra_caches_preserve_nixos_default():
    assert contract()["defaultCachesOnly"] == ["https://cache.nixos.org/"]
