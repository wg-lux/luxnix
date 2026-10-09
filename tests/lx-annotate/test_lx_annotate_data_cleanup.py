"""Run the cleanup shell against disposable trees; never mount or use host data."""

from pathlib import Path
import re
import shlex
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


@pytest.mark.parametrize("layout", ["distinct", "same", "symlink", "child", "parent", "missing"])
def test_cleanup_preserves_active_storage(tmp_path: Path, layout: str) -> None:
    runtime = tmp_path / "runtime"
    target = runtime / "processed"
    target.mkdir(parents=True)
    payload = target / "payload"
    payload.write_bytes(b"disposable-test-payload")
    source = tmp_path / "legacy"
    if layout == "same":
        source = target
    elif layout == "symlink":
        source.symlink_to(target, target_is_directory=True)
    elif layout == "child":
        source = target / "child"
        source.mkdir()
    elif layout == "parent":
        source = runtime
    else:
        source.mkdir()
        (source / "payload").write_bytes(payload.read_bytes())
    archive = tmp_path / "archive"
    config = (REPO_ROOT / "modules/nixos/services/lx-annotate-local/config.nix").read_text()
    script = config.split('dataCleanupScript = pkgs.writeShellScriptBin "runLxAnnotateDataCleanup" \'\'', 1)[1].split("\n  '';", 1)[0]
    values = {
        "envDataDir": runtime if layout != "missing" else tmp_path / "absent",
        "cfg.dataCleanup.archiveDir": archive,
        "config.roles.endoreg-client.paths.storagePersistingMountPoint": tmp_path,
        "processedReportDirName": "reports",
        "processedVideoDirName": "videos",
    }
    for name in ("legacyProcessedReportDir", "legacyProcessedVideoDir", "legacyMediaProcessedReportDir", "legacyMediaProcessedVideoDir"):
        values[f"cfg.dataCleanup.{name}"] = source if name == "legacyProcessedReportDir" else tmp_path / "no-legacy"
    for name in ("runtimeProcessedReportDir", "runtimeProcessedVideoDir"):
        values[f"cfg.dataCleanup.{name}"] = target
    for name, value in values.items():
        script = script.replace("${" + name + "}", str(value))
    script = re.sub(r"\$\{pkgs\.[\w-]+\}/bin/", "", script).replace("''${", "${")
    probes = f"mountpoint() {{ return 0; }}\nfindmnt() {{ printf '%s\\n' {shlex.quote(str(tmp_path))}; }}\n"
    result = subprocess.run(["bash", "-c", probes + script], capture_output=True, text=True)
    assert payload.read_bytes() == b"disposable-test-payload"
    if layout == "distinct":
        assert result.returncode == 0, result.stderr
        assert not (source / "payload").exists()
        assert (archive / "legacy-data/reports/payload").read_bytes() == payload.read_bytes()
    else:
        assert result.returncode != 0
        assert "refusing cleanup" in result.stderr
        assert not (runtime / "logs/data_cleanup_latest.log").exists()
        assert not (tmp_path / "absent").exists()


def test_cleanup_allows_absent_archive_and_legacy_checkout() -> None:
    result = eval_json('''
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.gc-02.config;
      in { unit = c.systemd.services.lx-annotate-data-cleanup.serviceConfig;
           archive = c.services.luxnix.lxAnnotateLocal.dataCleanup.archiveDir;
           runtime = c.services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir; }
    ''')
    assert "-" + result["archive"] in result["unit"]["ReadWritePaths"]
    assert "-/var/endoreg-service-user/lx-annotate" in result["unit"]["ReadWritePaths"]
    assert result["unit"]["WorkingDirectory"] == result["runtime"]
