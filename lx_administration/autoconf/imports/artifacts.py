"""Atomically publish validated Autoconf intermediate artifacts."""

import os
import tempfile
from pathlib import Path

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.permissions import ensure_private_directory
from lx_administration.yaml import PRIVATE_FILE_MODE, dump_yaml, format_yaml

from ..layout import AutoconfOutputLayout

HostVariables = dict[str, object]
ValidatedHosts = list[tuple[str, HostVariables]]


def _stage_merged_host_variables(
    staging_dir: Path,
    validated_hosts: ValidatedHosts,
) -> None:
    """Serialize a complete host set into a private staging directory."""
    ensure_private_directory(staging_dir)
    for hostname, merged_variables in validated_hosts:
        dump_yaml(
            merged_variables,
            staging_dir / f"{hostname}.yml",
            format_yaml,
            file_mode=PRIVATE_FILE_MODE,
        )


def _publish_merged_host_variables(
    staging_dir: Path,
    output_dir: Path,
    validated_hosts: ValidatedHosts,
) -> None:
    """Publish a staged host set and then remove stale generated files."""
    current_hostnames = {hostname for hostname, _ in validated_hosts}
    ensure_private_directory(output_dir)
    for hostname, _ in validated_hosts:
        os.replace(
            staging_dir / f"{hostname}.yml",
            output_dir / f"{hostname}.yml",
        )

    for stale_file in output_dir.glob("*.yml"):
        if stale_file.stem not in current_hostnames:
            stale_file.unlink()


def write_merged_host_variables(
    output_dir: Path,
    validated_hosts: ValidatedHosts,
) -> None:
    """Stage a complete private host set before publishing it."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_dir.parent,
        prefix=f".{output_dir.name}.",
    ) as staging_name:
        staging_dir = Path(staging_name)
        _stage_merged_host_variables(staging_dir, validated_hosts)
        _publish_merged_host_variables(staging_dir, output_dir, validated_hosts)


def write_system_intermediates(
    inventory: AnsibleInventory,
    autoconf_out: Path,
    validated_hosts: ValidatedHosts,
) -> None:
    """Stage inventory and merged system variables before publishing either."""
    layout = AutoconfOutputLayout(autoconf_out)
    autoconf_out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=autoconf_out,
        prefix=".system-intermediates.",
    ) as staging_name:
        staging_root = ensure_private_directory(staging_name)
        staged_inventory = staging_root / "inventory.yml"
        staged_merged_vars = staging_root / "merged_vars"

        inventory.save_to_file(
            staged_inventory,
            file_mode=PRIVATE_FILE_MODE,
        )
        _stage_merged_host_variables(staged_merged_vars, validated_hosts)

        os.replace(staged_inventory, layout.inventory_file)
        _publish_merged_host_variables(
            staged_merged_vars,
            layout.system_vars_dir,
            validated_hosts,
        )
