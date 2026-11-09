"""LX-Annotate consumes paths; LuxNix owns either encrypted storage layout."""

import pytest

from nix_eval_helpers import eval_json


@pytest.mark.parametrize(
    "host,layout", [("gc-02", "boot-luks"), ("gc-10", "legacy-containers")]
)
def test_storage_layout_is_owned_by_luxnix(host, layout):
    state = eval_json(
        """
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.HOST.config;
          app = c.services.luxnix.lxAnnotateLocal;
      in {
        layout = c.luxnix.storage.operatorUnlocked.layout;
        path = app.runtime.encryptedDataDir;
        upstreamPath = c.services.lx-annotate.dataDir;
        upstreamCompatPath = c.services.lx-annotate.encryptedDataDir;
        mounts = c.systemd.services.lx-annotate.unitConfig.RequiresMountsFor;
        requires = c.systemd.services.lx-annotate.requires;
        ownsUnlock = c.systemd.services ? lx-annotate-encrypted-data;
        generator = c.roles.managed-secrets.customSecrets.lx_annotate_master_key_local.generator;
        failures = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      }
    """.replace("HOST", host)
    )
    assert state["layout"] == layout
    assert state["path"] == state["upstreamPath"] == state["upstreamCompatPath"]
    assert state["path"] in state["mounts"]
    assert not state["ownsUnlock"]
    assert any("storage" in unit for unit in state["requires"])
    assert state["failures"] == []
    if layout == "boot-luks":
        assert "restore the existing key" in state["generator"]
        assert "openssl" not in state["generator"]
