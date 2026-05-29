from __future__ import annotations

import json
import subprocess
from typing import Any


REPO_ROOT = "/home/admin/dev/luxnix"
HOST = "gc-02"


def _nix_eval_json(attr: str) -> Any:
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--json",
            f".#nixosConfigurations.{HOST}.{attr}",
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _nix_eval_raw(attr: str) -> str:
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--raw",
            f".#nixosConfigurations.{HOST}.{attr}",
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _nix_eval_expr_json(expr: str) -> Any:
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expr, "--show-trace"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_gc_02_top_level_evaluates() -> None:
    drv_path = _nix_eval_raw("config.system.build.toplevel.drvPath")

    assert drv_path.startswith("/nix/store/")
    assert drv_path.endswith(".drv")
    assert "nixos-system-gc-02" in drv_path


def test_lx_annotate_tmpfiles_rules_evaluate_with_runtime_storage_paths() -> None:
    rules = _nix_eval_json("config.systemd.tmpfiles.rules")

    assert any(
        "/var/lib/lx-annotate/data/storage/streamable_videos " in rule for rule in rules
    )
    assert any(
        "/var/lib/lx-annotate/data/storage/streamable_videos/raw " in rule
        for rule in rules
    )
    assert any(
        "/var/lib/lx-annotate/data/storage/streamable_videos/processed " in rule
        for rule in rules
    )
    assert any(
        "/var/lib/lx-annotate/data/hub/backup/incoming " in rule for rule in rules
    )


def test_lx_annotate_boot_service_config_evaluates() -> None:
    service_config = _nix_eval_json(
        "config.systemd.services.lx-annotate-boot.serviceConfig"
    )

    assert service_config["Type"] == "exec"
    assert (
        service_config["WorkingDirectory"]
        == "/var/endoreg-service-user/lx-annotate-wheel"
    )
    assert service_config["ExecStart"].endswith("/bin/runLocalLxAnnotate")
    assert "/var/lib/lx-annotate/data" in service_config["ReadWritePaths"]
    assert (
        "/var/endoreg-service-user/lx-annotate-wheel/.venv"
        in service_config["ReadWritePaths"]
    )


def test_wheel_boot_script_runs_migrations_before_daphne() -> None:
    source = open(
        "/home/admin/dev/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix",
        encoding="utf-8",
    ).read()

    marker = 'runLocalLxAnnotateWheelScript = pkgs.writeShellScriptBin "${scriptName}"'
    start = source.find(marker)
    assert start != -1
    body_start = source.find("''\n", start)
    assert body_start != -1
    body_start += 3
    body_end = source.find("\n  '';", body_start)
    assert body_end != -1
    body = source[body_start:body_end]

    assert (
        'run_installed_django_command "${runtimeWheelVenvPath}/bin/python" migrate --noinput'
        in body
    )
    assert (
        'run_installed_django_command "${runtimeWheelVenvPath}/bin/python" load_base_db_data'
        in body
    )
    assert 'printf \'%s\\n\' "$install_hash" > "$bootstrap_stamp_file"' in body
    assert body.index(
        'run_installed_django_command "${runtimeWheelVenvPath}/bin/python" migrate --noinput'
    ) < body.index('exec "${runtimeWheelVenvPath}/bin/daphne"')


def test_lx_annotate_wheel_filewatcher_command_uses_django_module_entrypoint() -> None:
    command = _nix_eval_raw(
        "config.roles.endoreg-client.lxAnnotate.runtime.commands.fileWatcher"
    )

    assert "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django start_filewatcher" in command
    assert "--settings=lx_annotate.settings.settings_prod" in command
    assert "manage.py" not in command


def test_lx_annotate_filewatcher_service_config_uses_wheel_runtime_paths() -> None:
    service_config = _nix_eval_json(
        "config.systemd.services.lx-annotate-filewatcher.serviceConfig"
    )

    assert (
        service_config["WorkingDirectory"]
        == "/var/endoreg-service-user/lx-annotate-wheel"
    )
    assert service_config["ExecStart"].endswith("/bin/runLocalFileWatcher")
    assert (
        "/var/endoreg-service-user/lx-annotate-wheel"
        in service_config["ReadWritePaths"]
    )
    assert (
        "/var/endoreg-service-user/lx-annotate-wheel/.venv"
        in service_config["ReadWritePaths"]
    )
    assert "/var/lib/lx-annotate/data" in service_config["ReadWritePaths"]


def test_lx_annotate_acceptance_service_config_evaluates() -> None:
    service_config = _nix_eval_json(
        "config.systemd.services.lx-annotate-acceptance.serviceConfig"
    )

    assert service_config["Type"] == "oneshot"
    assert (
        service_config["WorkingDirectory"]
        == "/var/endoreg-service-user/lx-annotate-wheel"
    )
    assert service_config["ExecStart"].endswith("/bin/runLocalAcceptance")
    assert any(
        entry
        == "NIX_PATH=nixpkgs=/nix/store/d1rani8y6rh6d62khqx9s4r7lv1f2vpk-9zpnbb6xbnv2yl1f4ss577figjxvsfjv-source"
        or entry.startswith("NIX_PATH=nixpkgs=/nix/store/")
        for entry in service_config["Environment"]
    )


def test_wheel_acceptance_script_uses_installed_django_not_manage_py() -> None:
    source = open(
        "/home/admin/dev/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix",
        encoding="utf-8",
    ).read()

    marker = 'runLocalAcceptanceWheelScript = pkgs.writeShellScriptBin "${acceptanceScriptName}"'
    start = source.find(marker)
    assert start != -1
    body_start = source.find("''\n", start)
    assert body_start != -1
    body_start += 3
    body_end = source.find("\n  '';", body_start)
    assert body_end != -1
    body = source[body_start:body_end]

    assert (
        'run_installed_django_command "${runtimeWheelVenvPath}/bin/python" check --fail-level CRITICAL'
        in body
    )
    assert (
        'run_installed_django_command "${runtimeWheelVenvPath}/bin/python" verify_encrypted_storage'
        in body
    )
    assert "${runtimeWheelRootPath}/manage.py" not in body


def test_lx_annotate_streamable_migration_service_config_evaluates() -> None:
    service_config = _nix_eval_json(
        "config.systemd.services.lx-annotate-video-streamable-migration.serviceConfig"
    )

    assert service_config["Type"] == "oneshot"
    assert (
        service_config["WorkingDirectory"]
        == "/var/endoreg-service-user/lx-annotate-wheel"
    )
    assert service_config["ExecStart"].endswith(
        "/bin/lx-annotate-migrate-video-streamable-storage"
    )
    assert "/var/lib/lx-annotate/data" in service_config["ReadWritePaths"]


def test_lx_annotate_streamable_migration_unit_runs_after_boot_by_default() -> None:
    after = _nix_eval_json(
        "config.systemd.services.lx-annotate-video-streamable-migration.after"
    )
    wanted_by = _nix_eval_json(
        "config.systemd.services.lx-annotate-video-streamable-migration.wantedBy"
    )
    requires = _nix_eval_json(
        "config.systemd.services.lx-annotate-video-streamable-migration.requires"
    )

    assert "lx-annotate-boot.service" in after
    assert "lx-annotate-boot.service" in requires
    assert "multi-user.target" in wanted_by


def test_hub_transfer_api_extend_modules_enables_nginx_and_backup_surfaces() -> None:
    evaluated = _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "/home/admin/dev/luxnix";
          cfg = (flake.nixosConfigurations.gc-02.extendModules {
            modules = [
              ({ ... }: {
                services.luxnix.lxAnnotateLocal.hub.enable = true;
                services.luxnix.lxAnnotateLocal.hub.backup.enable = true;
                services.luxnix.lxAnnotateLocal.hub.transferApi.enable = true;
                services.luxnix.lxAnnotateLocal.hub.transferApi.requireSecureTransport = true;
                services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = true;
                services.luxnix.lxAnnotateLocal.hub.transferApi.clientCaFile = "/tmp/client-ca.pem";
                services.luxnix.lxAnnotateLocal.hub.transferApi.mtlsMetaKey = "X-Client-Cert-Subject";
                services.luxnix.lxAnnotateLocal.hub.transferApi.mtlsMetaValue = "$ssl_client_s_dn";
              })
            ];
          }).config;
        in {
          hostName = cfg.services.luxnix.lxAnnotateLocal.django.hostname;
          hubEnable = cfg.services.luxnix.lxAnnotateLocal.hub.enable;
          hostExtraConfig = cfg.services.nginx.virtualHosts.${cfg.services.luxnix.lxAnnotateLocal.django.hostname}.extraConfig;
          rootLocationExtraConfig = cfg.services.nginx.virtualHosts.${cfg.services.luxnix.lxAnnotateLocal.django.hostname}.locations."/".extraConfig;
          tmpfiles = cfg.systemd.tmpfiles.rules;
          isCentralNode = cfg.services.luxnix.lxAnnotateLocal.django.extraSettings.IS_CENTRAL_NODE;
          hubBackupExecStart = cfg.systemd.services.lx-annotate-hub-backup.serviceConfig.ExecStart;
        }
        """
    )

    assert evaluated["hubEnable"] is True
    assert any(
        directive in evaluated["hostExtraConfig"]
        for directive in ("ssl_verify_client optional;", "ssl_verify_client on;")
    )
    assert "ssl_client_certificate /tmp/client-ca.pem;" in evaluated["hostExtraConfig"]
    assert any(
        header in evaluated["rootLocationExtraConfig"]
        for header in (
            "proxy_set_header X-Client-Cert-Verified $ssl_client_verify;",
            "proxy_set_header X-client-cert-subject $ssl_client_verify;",
        )
    )
    assert any(
        "/var/lib/lx-annotate/data/hub " in rule for rule in evaluated["tmpfiles"]
    )
    assert any(
        "/var/lib/lx-annotate/data/hub/backup/incoming " in rule
        for rule in evaluated["tmpfiles"]
    )
    assert any(
        "/var/lib/lx-annotate/data/hub/backup/snapshots " in rule
        for rule in evaluated["tmpfiles"]
    )
    assert any(
        "/var/lib/lx-annotate/data/hub/backup/manifests " in rule
        for rule in evaluated["tmpfiles"]
    )
    assert evaluated["hubBackupExecStart"].endswith("/bin/runLxAnnotateHubBackup")


def test_endoreg_client_default_center_key_flows_to_lx_annotate_runtime_env() -> None:
    evaluated = _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "/home/admin/dev/luxnix";
          cfg = (flake.nixosConfigurations.gc-02.extendModules {
            modules = [
              ({ ... }: {
                endoreg-client.defaultCenterKey = "university_hospital_wuerzburg";
              })
            ];
          }).config;
        in {
          djangoDefaultCenter = cfg.services.luxnix.lxAnnotateLocal.django.extraSettings.DEFAULT_CENTER;
          djangoDefaultCenterKey = cfg.services.luxnix.lxAnnotateLocal.django.extraSettings.DEFAULT_CENTER_KEY;
          fileWatcherEnvironment = cfg.systemd.services.lx-annotate-filewatcher.serviceConfig.Environment;
        }
        """
    )

    assert evaluated["djangoDefaultCenterKey"] == "university_hospital_wuerzburg"
    assert (
        "LX_ANNOTATE_DEFAULT_CENTER=university_hospital_wuerzburg"
        in evaluated["fileWatcherEnvironment"]
    )
