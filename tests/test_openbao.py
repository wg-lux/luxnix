"""Evaluate the additive backend and its failure boundaries without activation."""
import json
import subprocess
import shlex

import pytest

from lx_administration import secret_storage
from pathlib import Path


def test_openbao_isolation_and_guards():
    expression = r'''
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      lib = f.inputs.nixpkgs.lib;
      base = f.nixosConfigurations.gs-02;
      enabled = extra: (base.extendModules { modules = [ ({ ... }: {
        luxnix.openbao.enable = true;
        fileSystems."/var/lib/openbao" = {
          device = "/dev/mapper/openbao-test";
          fsType = "ext4";
        };
      }) extra ]; }).config;
      good = enabled {};
      bad = enabled { luxnix.openbao.apiAddress = "http://localhost:8300";
        luxnix.openbao.tlsKeyFile = "/nix/store/unsafe-key"; };
      missing = (base.extendModules { modules = [{ luxnix.openbao.enable = true; }]; }).config;
      errors = c: map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
    in {
      defaults = builtins.mapAttrs (_: v: v.config.services.openbao.enable) f.nixosConfigurations;
      vaultUnchanged = good.services.vault == base.config.services.vault;
      settings = good.services.openbao.settings;
      unit = good.systemd.services.openbao;
      goodErrors = errors good;
      badErrors = errors bad;
      missingErrors = errors missing;
      version = good.services.openbao.package.version;
    }
    '''
    # Select service fields to avoid serializing internal NixOS option functions.
    expression = expression.replace('unit = good.systemd.services.openbao;', '''unit = {
      inherit (good.systemd.services.openbao) bindsTo requires restartIfChanged;
      inherit (good.systemd.services.openbao.serviceConfig) LoadCredential ExecStartPre LimitCORE;
    };''')
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        check=True, timeout=180,
    )
    data = json.loads(result.stdout)
    assert not any(data["defaults"].values())
    assert data["vaultUnchanged"]
    assert data["goodErrors"] == []
    assert any("HTTPS" in e for e in data["badErrors"])
    assert any("runtime paths" in e for e in data["badErrors"])
    assert any("encrypted mount" in e for e in data["missingErrors"])
    assert data["settings"]["audit"][0]["file"]["release"]["options"]["file_path"] == "/var/lib/openbao/audit.jsonl"
    listener = data["settings"]["listener"]["release"]
    assert listener["address"] == "127.0.0.1:8300"
    assert listener["tls_disable"] is False
    assert listener["tls_disable_client_certs"] is False
    assert data["settings"]["storage"]["raft"]["path"] == "/var/lib/openbao"
    assert data["unit"]["bindsTo"] == ["var-lib-openbao.mount"]
    assert data["unit"]["restartIfChanged"] is False
    assert data["unit"]["LimitCORE"] == 0
    assert "verify-openbao-storage" in str(data["unit"]["ExecStartPre"])
    assert len(data["unit"]["LoadCredential"]) == 2
    checks = data["unit"]["ExecStartPre"]
    assert len(checks) == 2
    assert shlex.split(checks[0])[1:] == ["/var/lib/openbao"]
    assert shlex.split(checks[1])[1:] == ["--allow-runtime", "/etc/secrets/openbao/server-key.pem"]


def test_openbao_persistent_state_rejects_tmpfs(monkeypatch):
    monkeypatch.setattr(secret_storage, "_require_protected_swap", lambda: None)
    monkeypatch.setattr(secret_storage, "_mounted_filesystem",
                        lambda path: {"source": "tmpfs", "fstype": "tmpfs"})
    with pytest.raises(ValueError, match="Persistent secrets require encrypted block storage"):
        secret_storage.encrypted_storage(Path("/var/lib/openbao"))
    secret_storage.encrypted_storage(Path("/run/openbao/server-key.pem"), allow_runtime=True)
