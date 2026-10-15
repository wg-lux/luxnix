from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = REPO_ROOT / "modules/nixos/services/lx-annotate-local"


def test_monitoring_configuration_is_typed_and_host_owned() -> None:
    options = (MODULE_ROOT / "options/monitoring.nix").read_text(encoding="utf-8")
    config = (MODULE_ROOT / "config.nix").read_text(encoding="utf-8")
    environment = (MODULE_ROOT / "scripts/env.nix").read_text(encoding="utf-8")

    assert "schema_version = 1;" in config
    assert 'systemctl_path = "${pkgs.systemd}/bin/systemctl";' in config
    assert "systemctl_timeout_seconds" in config
    assert "disk_warning_free_percent" in config
    assert "disk_error_free_percent" in config
    assert "pending_warning_seconds" in config
    assert "recent_failure_window_seconds" in config
    assert "types.ints.between 1 99" in options
    assert "types.ints.between 1 5" in options
    assert options.count("types.ints.between 60 604800") == 2
    assert 'types.strMatching "[0-9a-f]{7,64}"' in options
    assert 'environment.etc."lx-annotate/monitoring.json"' in config
    assert (
        "LX_ANNOTATE_MONITORING_CONFIG_FILE = monitoringConfigFile;"
        in environment
    )
    assert (
        'builtins.hasAttr "LX_ANNOTATE_MONITORING_CONFIG_FILE" '
        "cfg.runtime.extraEnvironment"
    ) in config


def test_monitoring_inventory_has_only_fixed_service_and_storage_keys() -> None:
    config = (MODULE_ROOT / "config.nix").read_text(encoding="utf-8")

    for service_key in (
        "web",
        "worker_default",
        "worker_pipeline",
        "worker_ffmpeg",
        "worker_frame_extraction",
        "scheduler",
        "reverse_proxy",
    ):
        assert f'key = "{service_key}";' in config
    for storage_key in (
        "protected_data",
        "application_storage",
        "import_intake",
        "hls_raw",
        "hls_processed",
    ):
        assert f'key = "{storage_key}";' in config

    forbidden_dynamic_fields = (
        "video_id",
        "upload_job_id",
        "task_id",
        "filename",
        "source_content_hash",
    )
    monitoring_start = config.index(
        'monitoringConfig = pkgs.writeText "lx-annotate-monitoring-config-v1.json"'
    )
    monitoring_end = config.index("envContract = import", monitoring_start)
    monitoring_source = config[monitoring_start:monitoring_end]
    assert not any(field in monitoring_source for field in forbidden_dynamic_fields)


def test_monitoring_is_enabled_for_every_gpu_role() -> None:
    group_vars = REPO_ROOT / "ansible/inventory/group_vars"

    for group_name in ("gpu_client", "gpu_server"):
        group_config = (group_vars / f"{group_name}.yml").read_text(encoding="utf-8")
        assert (
            'luxnix.lxAnnotateLocal.runtime.monitoring.enable: "true"'
            in group_config
        )
