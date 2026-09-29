from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json

MODULE_ROOT = REPO_ROOT / "modules/nixos/services/lx-annotate-local"
spec = importlib.util.spec_from_file_location(
    "wheel_downgrade_guard", MODULE_ROOT / "scripts/wheel-downgrade-guard.py"
)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def report(name: str, version: str) -> dict:
    return {
        "version": "1",
        "install": [{"metadata": {"name": name, "version": version}}],
    }


@pytest.mark.parametrize("name", sorted(guard.PROTECTED_PACKAGES))
def test_each_protected_distribution_rejects_downgrade(name: str) -> None:
    with pytest.raises(ValueError, match="Refusing shared-runtime downgrade"):
        guard.validate_report(report(name, "1.1"), {name: guard.Version("1.2")})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"version": "1"},
        {"version": "2", "install": []},
        {"version": "1", "install": [{}]},
        {"version": "1", "install": [{"metadata": {"name": "lx-dtypes"}}]},
    ],
)
def test_missing_or_malformed_reports_fail_closed(payload: object) -> None:
    with pytest.raises(ValueError):
        guard.validate_report(payload, {})


def test_local_versions_and_unchanged_packages_are_preserved() -> None:
    installed = {
        "lx-dtypes": guard.Version("0.2.35+reviewed.1"),
        "endoreg-db": guard.Version("1.1.7"),
    }
    with pytest.raises(ValueError, match="downgrade"):
        guard.validate_report(report("lx_dtypes", "0.2.35"), installed)
    assert (
        guard.validate_report({"version": "1", "install": []}, installed) == installed
    )


def test_application_wheel_metadata_checked_before_resolver(tmp_path: Path) -> None:
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "lx_annotate-1.2.2.dist-info/METADATA",
            "Name: lx-annotate\nVersion: 1.2.2\n",
        )
    with pytest.raises(ValueError, match="downgrade"):
        guard.validate_wheel(wheel, "1.2.2", {"lx-annotate": guard.Version("1.3.1")})
    with pytest.raises(ValueError, match="configured packageVersion"):
        guard.validate_wheel(wheel, "1.3.1", {})


def test_override_resolution_exposes_an_already_installed_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    def resolve(command, **kwargs):
        captured.append(command)
        # pip must report even a requested version already installed before the
        # application step; otherwise the projected .36 -> .34 downgrade hides.
        assert "--force-reinstall" in command
        return subprocess.CompletedProcess(
            command, 0, json.dumps(report("lx-dtypes", "0.2.34")), ""
        )

    monkeypatch.setattr(guard.subprocess, "run", resolve)
    with pytest.raises(ValueError, match="0.2.36 -> 0.2.34"):
        guard.check_plan(
            ["lx-dtypes==0.2.34"],
            ["--no-index", "--find-links", "/wheelhouse"],
            {"lx-dtypes": guard.Version("0.2.36")},
            no_deps=True,
        )
    assert captured[0][-5:] == [
        "lx-dtypes==0.2.34",
        "--dry-run",
        "--report",
        "-",
        "--quiet",
    ]


def test_resolver_failure_never_becomes_empty_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        guard.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "private resolver diagnostics"
        ),
    )
    with pytest.raises(ValueError, match="no packages installed"):
        guard.check_plan(["candidate.whl"], [], {})


def test_constraints_publish_exact_local_versions_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lx_administration.utils import file_operations

    monkeypatch.setitem(sys.modules, "wheel_guard_file_operations", file_operations)
    target = tmp_path / "application.constraints"
    guard.write_constraints(target, {"lx-dtypes": guard.Version("0.2.35+reviewed.1")})
    assert target.read_text() == "lx-dtypes==0.2.35+reviewed.1\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [target]


def test_installs_use_separate_validated_constraints() -> None:
    source = (MODULE_ROOT / "config.nix").read_text()
    guard_position = source.index("${wheelDowngradeGuard}/guard.py")
    installs = [
        line
        for line in source.splitlines()
        if '/bin/pip"}' in line and " install " in line
    ]
    assert len(installs) == 3
    assert all(source.index(line) > guard_position for line in installs)
    assert all(
        '--constraint "$application_constraints"' in line for line in installs[:2]
    )
    assert '--constraint "$override_constraints"' in installs[2]
    assert "--force-reinstall" in installs[2]


def test_schema_compatibility_precedes_migration_and_legacy_repair() -> None:
    source = (MODULE_ROOT / "subservices/lx-annotate-migrate.nix").read_text()
    script = source[source.index("set -euo pipefail") :]
    assert script.index("check_migration_compatibility") < script.index(
        "migrate --noinput"
    )
    assert script.rindex("check_migration_compatibility") < script.index(
        'call_command("repair_legacy_migration_history"'
    )
    assert (
        "check_migration_compatibility"
        in (MODULE_ROOT / "subservices/lx-annotate-preflight.nix").read_text()
    )


def test_rendered_guard_ships_filesystem_helper_and_schema_gates() -> None:
    rendered = eval_json(
        """
        let
          f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = f.nixosConfigurations.gc-02.config;
        in {
          runtime = builtins.readFile
            "${c.services.lx-annotate.package}/libexec/lx-annotate-wheel-runtime-lib";
          migrate = builtins.readFile
            c.systemd.services.lx-annotate-migrate.serviceConfig.ExecStart;
          preflight = builtins.readFile
            c.systemd.services.lx-annotate-preflight.serviceConfig.ExecStart;
        }
        """
    )
    match = re.search(r"(/nix/store/[^\s]+/guard.py)", rendered["runtime"])
    assert match
    guard_path = Path(match[1])
    assert (
        guard_path.read_bytes()
        == (MODULE_ROOT / "scripts/wheel-downgrade-guard.py").read_bytes()
    )
    assert (
        guard_path.with_name("wheel_guard_file_operations.py").read_bytes()
        == (REPO_ROOT / "lx_administration/utils/file_operations.py").read_bytes()
    )
    helper_spec = importlib.util.spec_from_file_location(
        "rendered_guard_helpers", guard_path.with_name("wheel_guard_file_operations.py")
    )
    assert helper_spec and helper_spec.loader
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    assert callable(helper.atomic_write_file)
    assert rendered["migrate"].index("check_migration_compatibility") < rendered[
        "migrate"
    ].index("migrate --noinput")
    assert "check_migration_compatibility" in rendered["preflight"]


@pytest.mark.parametrize(
    ("stderr", "category"),
    [
        (
            "ERROR: No matching distribution found for endoreg-db==1.3.15",
            "distribution_unavailable",
        ),
        ("ERROR: ResolutionImpossible", "dependency_conflict"),
        ("CERTIFICATE_VERIFY_FAILED", "tls_verification_failed"),
        (
            "NewConnectionError\n"
            "ERROR: No matching distribution found for endoreg-db==1.3.15",
            "index_unreachable",
        ),
        ("No space left on device", "storage_full"),
        ("Permission denied", "permission_denied"),
        ("private build failure", "resolver_error"),
    ],
)
def test_resolver_errors_have_safe_actionable_categories(
    stderr: str, category: str
) -> None:
    summary = guard.resolver_failure_summary(stderr)
    assert f"category={category}" in summary
    assert "private" not in summary


def test_missing_requirement_is_reported_without_index_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = (
        "Looking in indexes: https://user:secret@index.invalid/simple?token=secret\n"
        "ERROR: No matching distribution found for endoreg-db==1.3.15\n"
    )
    monkeypatch.setattr(
        guard.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", stderr),
    )
    with pytest.raises(ValueError) as error:
        guard.check_plan(["candidate.whl"], [], {})
    assert "requirements=endoreg-db==1.3.15" in str(error.value)
    assert "phase=application" in str(error.value)
    assert "secret" not in str(error.value)
    assert "index.invalid" not in str(error.value)
    assert "no packages installed" in str(error.value)


@pytest.mark.parametrize(
    "requirement",
    [
        "package @ https://user:secret@example.invalid/wheel.whl",
        "/private/secret.whl",
        "package==1.0 https://user:secret@example.invalid",
    ],
)
def test_unrecognized_requirement_text_is_never_echoed(requirement: str) -> None:
    summary = guard.resolver_failure_summary(
        "ERROR: No matching distribution found for " + requirement
    )
    assert "secret" not in summary
    assert "example.invalid" not in summary
    assert "requirements=" not in summary


def test_check_only_does_not_write_constraints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guard.py",
            "--wheel",
            str(tmp_path / "candidate.whl"),
            "--expected-version",
            "1.3.13",
            "--check-only",
        ],
    )
    monkeypatch.setattr(guard, "installed_versions", lambda: {})
    monkeypatch.setattr(guard, "validate_wheel", lambda *args: None)
    monkeypatch.setattr(guard, "check_plan", lambda *args, **kwargs: {})

    def unexpected_write(*args):
        raise AssertionError("Read-only admission wrote constraints")

    monkeypatch.setattr(guard, "write_constraints", unexpected_write)
    guard.main()
    assert list(tmp_path.iterdir()) == []


def test_online_preparation_waits_for_network_and_offline_does_not() -> None:
    rendered = eval_json("""
      let
        f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        c = f.nixosConfigurations.gc-02.config;
        offline = (f.nixosConfigurations.gc-02.extendModules {
          modules = [({ lib, ... }: {
            services.luxnix.lxAnnotateLocal.runtime.wheelhousePath =
              lib.mkForce /var/lib/lx-annotate/wheelhouse;
          })];
        }).config;
      in {
        onlineAfter = c.systemd.services.lx-annotate-wheel-runtime.after;
        onlineWants = c.systemd.services.lx-annotate-wheel-runtime.wants;
        offlineAfter = offline.systemd.services.lx-annotate-wheel-runtime.after;
        requires = c.systemd.services.lx-annotate-wheel-runtime.requires;
      }
    """)
    assert "network-online.target" in rendered["onlineAfter"]
    assert "network-online.target" in rendered["onlineWants"]
    assert "network-online.target" not in rendered["offlineAfter"]
    assert "lx-annotate-runtime-env.service" in rendered["requires"]
