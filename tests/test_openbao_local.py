"""Bootstrap rejection tests; these do not establish physical TPM acceptance."""

import base64
import json
from pathlib import Path
import struct
import subprocess

import pytest

from lx_administration.storage import openbao_local as local


def credential(key_type=local.TPM_ONLY, mask=128):
    return base64.b64encode(
        key_type
        + struct.pack("<IIII", 32, 1, 12, 16)
        + bytes(16)
        + struct.pack("<Q", mask)
        + bytes(48)
    )


@pytest.mark.parametrize(
    "blob",
    [
        b"plaintext",
        b"",
        credential(bytes(16)),
        credential(mask=0),
        credential(mask=1 << 24),
        credential(bytes.fromhex("5a1c6a86df9d4096b1d5a65e0862f19a")),
    ],
)
def test_reject_software_or_unbound_credential(blob):
    with pytest.raises(ValueError):
        local.validate_credential(blob)


def test_header_filter_does_not_decrypt(monkeypatch, tmp_path):
    monkeypatch.setattr(local, "read_private", lambda _: credential())
    local.preflight(tmp_path / "seal.cred")


def test_private_file_rejects_symlink_and_public_mode(tmp_path):
    target = tmp_path / "key"
    target.write_bytes(credential())
    link = tmp_path / "link"
    link.symlink_to(target)
    for path in (target, link):
        with pytest.raises(ValueError):
            local.read_private(path)


def test_local_and_hub_are_independent():
    root = Path(__file__).resolve().parents[1]
    expression = r"""
    let
      f = builtins.getFlake ("git+file://" + builtins.toString ./.);
      base = f.nixosConfigurations.gs-02;
      c = (base.extendModules { modules = [{
        luxnix.openbao.local.enable = true;
        luxnix.openbao.enable = true;
        # Production platform prerequisites are mandatory for enrollment.
        system.boot.secureBoot = f.inputs.nixpkgs.lib.mkForce true;
        luxnix.storage.operatorUnlocked = {
          unlockMethod = "local-openbao";
          migration.enable = f.inputs.nixpkgs.lib.mkForce false;
          volumes = f.inputs.nixpkgs.lib.mkForce { luxnix-secrets = {
            container = "/var/lib/test.luks"; mountPoint = "/var/lib/test";
            luksUUID = "11111111-1111-1111-1111-111111111111";
          }; };
          bindMounts = f.inputs.nixpkgs.lib.mkForce {};
          guardedServices = f.inputs.nixpkgs.lib.mkForce {};
          startupServices = f.inputs.nixpkgs.lib.mkForce [];
        };
        fileSystems."/var/lib/openbao" = {
          device = "/dev/mapper/test"; fsType = "ext4";
        };
      }]; }).config;
      unit = c.systemd.services.openbao-local;
      unlock = c.systemd.services.luxnix-storage-unlock-luxnix-secrets;
    in {
      errors = map (a: a.message) (builtins.filter (a: !a.assertion) c.assertions);
      inherit (unit) requires after restartIfChanged;
      service = unit.serviceConfig;
      assertions = unit.unitConfig;
      hub = c.services.openbao.settings.storage.raft.path;
      unlock = {
        inherit (unlock) requires after;
        inherit (unlock.serviceConfig) LoadCredentialEncrypted TimeoutStartSec;
      };
      switchChecks = builtins.attrNames c.system.preSwitchChecks;
      inherit (unit) wantedBy;
      tool = let
        tools = builtins.filter (p: (p.name or "") == "luxnix-openbao-local") c.environment.systemPackages;
      in map (p: p.text) tools;
      # Enrollment stage: tool present, no boot dependency, no activation gate yet.
      staged = let
        s = (base.extendModules { modules = [{ luxnix.openbao.local.enable = true; }]; }).config;
      in {
        wantedBy = s.systemd.services.openbao-local.wantedBy;
        gated = s.system.preSwitchChecks ? openbaoLocalPreflight;
        tool = builtins.any (p: (p.name or "") == "luxnix-openbao-local") s.environment.systemPackages;
      };
      vaultUnchanged = c.services.vault == base.config.services.vault;
      defaultEnabled = base.options.luxnix.openbao.local.enable.default;
      fleet = builtins.mapAttrs (_: v: {
        localEnabled = v.config.luxnix.openbao.local.enable;
        unlockMethod = v.config.luxnix.storage.operatorUnlocked.unlockMethod;
        bootWanted = v.config.systemd.services.openbao-local.wantedBy or [];
      }) f.nixosConfigurations;
    }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    data = json.loads(result.stdout)
    # Shared EndoReg policy deliberately blocks unattended production profiles;
    # this evaluation still verifies independent service wiring beneath the gate.
    assert data["errors"] == [
        "EndoReg unattended unlock is blocked until authenticated system and "
        "application runtime acceptance is implemented."
    ]
    assert data["defaultEnabled"] is False
    for settings in data["fleet"].values():
        if settings["unlockMethod"] != "local-openbao":
            assert settings["bootWanted"] == []
    assert data["vaultUnchanged"]
    assert data["hub"] == "/var/lib/openbao"
    assert data["service"]["StateDirectory"] == "openbao-local"
    assert data["service"]["RuntimeDirectoryMode"] == "0700"
    assert data["service"]["PrivateNetwork"] is True
    assert data["service"]["LoadCredentialEncrypted"] == [
        "seal.key:/var/lib/openbao-bootstrap/seal.cred"
    ]
    assert data["requires"] == ["openbao-local-preflight.service"]
    assert data["after"] == data["requires"]
    assert data["assertions"]["AssertPathExists"].endswith("/raft/raft.db")
    assert data["restartIfChanged"] is False
    assert data["unlock"]["requires"] == ["openbao-local.service"]
    assert data["unlock"]["after"] == ["openbao-local.service"]
    assert data["unlock"]["TimeoutStartSec"] == "90s"
    assert "openbaoLocalPreflight" in data["switchChecks"]
    assert data["unlock"]["LoadCredentialEncrypted"] == [
        "volume.unlock:/var/lib/openbao-bootstrap/volume-unlock.cred"
    ]
    assert data["wantedBy"] == ["multi-user.target"]
    assert len(data["tool"]) == 1 and "--require-secure-boot" not in data["tool"][0]
    assert data["staged"] == {"wantedBy": [], "gated": False, "tool": True}


CREDENTIAL = json.dumps({"role_id": "role-1", "secret_id": "secret-1"}).encode()


class FakeBao:
    """Records API calls; answers seal status, AppRole login and one record read."""

    def __init__(self, record, sealed_polls=0):
        self.record = record
        self.sealed_polls = sealed_polls
        self.calls = []

    def __call__(self, method, path, data=None, token=None, socket_path=None, timeout=5):
        self.calls.append((method, path, token))
        if path == "sys/seal-status":
            self.sealed_polls -= 1
            return {"initialized": True, "sealed": self.sealed_polls >= 0}
        if path == "sys/health":
            return {}
        if path == "auth/approle/login":
            if data != {"role_id": "role-1", "secret_id": "secret-1"}:
                raise local.DeniedError("denied")
            return {"auth": {"client_token": "s.short-lived"}}
        if path == "auth/token/revoke-self":
            return {}
        return self.record


def test_volume_key_waits_unsealed_logs_in_and_revokes(monkeypatch):
    monkeypatch.setattr(local, "read_private", lambda _: CREDENTIAL)
    monkeypatch.setattr(local.time, "sleep", lambda _: None)
    key = bytes(range(32))
    bao = FakeBao({"data": {"data": {"key": base64.b64encode(key).decode(), "luks_uuid": "a-b"}}},
                  sealed_polls=1)
    monkeypatch.setattr(local, "call", bao)
    assert local.volume_key("host", "data", "a-b", "/run/credential") == key
    reads = [c for c in bao.calls if c[1].startswith("volume-release/")]
    assert reads == [("GET", "volume-release/data/host/data/a-b", "s.short-lived")]
    # Seal status was polled while sealed, and the single-use token is revoked last.
    assert [c[1] for c in bao.calls].count("sys/seal-status") == 2
    assert bao.calls[-1] == ("POST", "auth/token/revoke-self", "s.short-lived")


@pytest.mark.parametrize(
    "response",
    [
        {"data": {"data": {"key": "YWJj", "luks_uuid": "a-b"}}},
        {"data": {"data": {"key": base64.b64encode(bytes(32)).decode(), "luks_uuid": "wrong"}}},
        {"data": None},
    ],
)
def test_bad_volume_response_never_falls_back(monkeypatch, response):
    monkeypatch.setattr(local, "read_private", lambda _: CREDENTIAL)
    bao = FakeBao(response)
    monkeypatch.setattr(local, "call", bao)
    with pytest.raises(ValueError):
        local.volume_key("host", "data", "a-b", "/run/credential")
    assert bao.calls[-1][1] == "auth/token/revoke-self"


@pytest.mark.parametrize(
    "credential",
    [b"raw-token", json.dumps({"role_id": "role-1"}).encode(),
     json.dumps({"role_id": "role-1", "secret_id": "other"}).encode(),
     json.dumps({"role_id": "role 1", "secret_id": "secret-1"}).encode()],
)
def test_rejected_or_malformed_credential_reads_nothing(monkeypatch, credential):
    monkeypatch.setattr(local, "read_private", lambda _: credential)
    bao = FakeBao({"data": {"data": {}}})
    monkeypatch.setattr(local, "call", bao)
    with pytest.raises(ValueError):
        local.volume_key("host", "data", "a-b", "/run/credential")
    assert not any(c[1].startswith("volume-release/") for c in bao.calls)


def test_unseal_wait_is_bounded(monkeypatch):
    monkeypatch.setattr(local, "read_private", lambda _: CREDENTIAL)
    monkeypatch.setattr(local.time, "sleep", lambda _: None)
    bao = FakeBao({}, sealed_polls=10**6)
    monkeypatch.setattr(local, "call", bao)
    with pytest.raises(ValueError, match="deadline"):
        local.volume_key("host", "data", "a-b", "/run/credential", timeout=0)
    assert not any(c[1] == "auth/approle/login" for c in bao.calls)


@pytest.fixture
def platform(tmp_path, monkeypatch):
    from types import SimpleNamespace

    tpm = tmp_path / "tpm0"
    (tpm / "device").mkdir(parents=True)
    (tpm / "tpm_version_major").write_text("2")
    driver = tmp_path / "drivers/tpm_crb"
    driver.mkdir(parents=True)
    (tpm / "device/driver").symlink_to(driver)
    secure_boot = tmp_path / "SecureBoot"
    secure_boot.write_bytes(b"\x06\x00\x00\x00\x01")
    monkeypatch.setattr(local, "TPM", tpm)
    monkeypatch.setattr(local, "SECURE_BOOT", secure_boot)
    results = {"systemd-creds": (0, b"yes"), "systemd-detect-virt": (1, b"none\n")}
    def run(args, **kwargs):
        code, out = results[args[0]]
        return SimpleNamespace(returncode=code, stdout=out)
    monkeypatch.setattr(local.subprocess, "run", run)
    return tpm, secure_boot, results


def test_physical_platform_requires_live_secure_boot(platform):
    tpm, secure_boot, results = platform
    assert local.platform_preflight()["physical_tpm"] is True
    secure_boot.write_bytes(b"\x06\x00\x00\x00\x00")
    with pytest.raises(ValueError, match="secure-boot-disabled"):
        local.platform_preflight()
    secure_boot.unlink()
    with pytest.raises(ValueError, match="secure-boot-disabled"):
        local.platform_preflight()


@pytest.mark.parametrize(
    "virtual", [(0, b"kvm"), (0, b"docker"), (1, b""), (2, b"none")]
)
def test_virtual_or_failed_detection_rejected(platform, virtual):
    platform[2]["systemd-detect-virt"] = virtual
    with pytest.raises(ValueError, match="tpm-not-physical"):
        local.platform_preflight()


@pytest.mark.parametrize("driver", ["tpm_vtpm_proxy", "tpm_tis_spi", "unknown"])
def test_unknown_or_software_tpm_driver_rejected(platform, driver):
    tpm, _, _ = platform
    link = tpm / "device/driver"
    target = link.resolve().parent / driver
    target.mkdir()
    link.unlink()
    link.symlink_to(target)
    with pytest.raises(ValueError, match="tpm-not-physical"):
        local.platform_preflight()


def test_missing_tpm_and_wrong_tpm_version_rejected(platform):
    tpm, _, results = platform
    results["systemd-creds"] = (1, b"partial")
    with pytest.raises(ValueError, match="tpm-missing"):
        local.platform_preflight()
    results["systemd-creds"] = (0, b"yes")
    (tpm / "tpm_version_major").write_text("1")
    with pytest.raises(ValueError, match="tpm-not-physical"):
        local.platform_preflight()
