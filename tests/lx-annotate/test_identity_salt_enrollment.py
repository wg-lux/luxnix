from __future__ import annotations

import subprocess
import os
from pathlib import Path

from nix_eval_helpers import eval_json


def _enrollment_contract() -> dict:
    return eval_json('''
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        host = flake.nixosConfigurations.gc-02.extendModules {
          modules = [{ services.luxnix.lxAnnotateLocal.django.enrollLegacyDefaultSalt = true; }];
        };
        c = host.config;
        secrets = c.roles.managed-secrets.customSecrets;
      in {
        keyring = c.services.luxnix.lxAnnotateLocal.django.identitySaltKeyringFile;
        active = secrets.lx_annotate_identity_active;
        legacy = secrets.lx_annotate_identity_legacy;
        manifest = secrets.lx_annotate_identity_manifest;
        beat = { inherit (c.systemd.services.lx-annotate-celery-beat) after requires; };
        user = c.systemd.services.lx-annotate.serviceConfig.User;
        envScript = builtins.readFile c.systemd.services.lx-annotate-runtime-env.serviceConfig.ExecStart;
      }
    ''')


def test_identity_enrollment_is_private_explicit_and_reaches_runtime():
    contract = _enrollment_contract()
    for name in ("active", "legacy", "manifest"):
        secret = contract[name]
        assert secret["permissions"] == "600"
        assert secret["owner"] == contract["user"]
        assert secret["forceRegenerate"] is False
    assert contract["keyring"] == contract["manifest"]["path"]
    assert "DJANGO_IDENTITY_SALT_KEYRING_FILE" in contract["envScript"]
    assert contract["keyring"] in contract["envScript"]
    for edge in ("after", "requires"):
        assert "lx-annotate-load-base-data.service" in contract["beat"][edge]
        assert "lx-annotate-master-key-check.service" in contract["beat"][edge]


def test_active_salt_cannot_be_replaced_after_manifest_publication(tmp_path: Path):
    contract = _enrollment_contract()
    manifest = tmp_path / "identity.yml"
    generator = contract["active"]["generator"].replace(
        contract["keyring"], str(manifest)
    )
    assert contract["active"]["customScript"] is True
    target = tmp_path / "active"
    env = dict(os.environ, TARGET_FILE=str(target))
    first = subprocess.run(["bash", "-eu", "-c", generator], capture_output=True, env=env)
    assert first.returncode == 0, first.stderr
    assert not first.stdout
    original = target.read_bytes()
    assert len(original.strip()) == 64
    assert original.strip() != b"default_salt"
    manifest.write_text("published test manifest")
    refused = subprocess.run(["bash", "-eu", "-c", generator], capture_output=True, env=env)
    assert refused.returncode != 0
    assert not refused.stdout
    assert b"Refusing to replace" in refused.stderr
    assert target.read_bytes() == original


def test_enrollment_requires_host_opt_in():
    configured = eval_json('''
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
      in {
        default = (f.nixosConfigurations.gc-02.options.services.luxnix.lxAnnotateLocal.django.type.getSubOptions []).enrollLegacyDefaultSalt.default;
        gs-02 = f.nixosConfigurations.gs-02.config.services.luxnix.lxAnnotateLocal.django.enrollLegacyDefaultSalt;
      }
    ''')
    assert configured == {"default": False, "gs-02": False}
