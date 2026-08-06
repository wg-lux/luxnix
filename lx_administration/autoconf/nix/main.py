"""Render NixOS and Home Manager configurations from merged Autoconf data."""

import logging
from pathlib import Path

from jinja2 import TemplateError

from lx_administration.logging import log_heading
from lx_administration.models import MergedHostVars

from ..config import AutoconfConfig
from ..errors import AutoconfPipelineError
from ..layout import NixTemplateLayout
from .home import render_home_outputs
from .template_renderer import render_nix_template
from .utils import RenderedNixOutput, write_nix_outputs


def get_template_dir_for_host(
    templates: NixTemplateLayout,
    host_platform: str,
    template_name: str,
) -> Path:
    template_dir = templates.system_template_dir(host_platform, template_name)
    if not template_dir.is_dir():
        raise AutoconfPipelineError(
            f"Nix system template directory not found: {template_dir}"
        )
    return template_dir


def render_default_nix(
    hostname: str,
    merged_vars: MergedHostVars,
    host_platform: str,
    config: AutoconfConfig,
    logger: logging.Logger | None = None,
) -> RenderedNixOutput:
    """Render one system configuration without writing it."""
    if logger is not None:
        log_heading(logger, f"Generating default.nix for {hostname}")

    template_dir = get_template_dir_for_host(
        config.template_layout,
        host_platform,
        merged_vars.template_name or "main",
    )

    exported_host_config = {
        **merged_vars.export_host_config(logger=logger),
        "hostname": hostname,
    }
    default_nix = render_nix_template(
        str(template_dir), "default.nix.j2", exported_host_config
    )
    default_nix_path = config.nix_output_layout.system_file(host_platform, hostname)

    return default_nix_path, default_nix


def render_configurations(
    config: AutoconfConfig,
    logger: logging.Logger | None = None,
) -> None:
    """Render all outputs using the central Autoconf configuration."""
    layout = config.output_layout

    render_hosts: list[tuple[str, MergedHostVars, str]] = []
    for merged_vars_file in sorted(layout.system_vars_dir.glob("*.yml")):
        hostname = merged_vars_file.stem
        try:
            merged_vars = MergedHostVars.load_from_file(merged_vars_file, logger=logger)
            host_platform = merged_vars.get_host_platform(logger=logger)
            get_template_dir_for_host(
                config.template_layout,
                host_platform,
                merged_vars.template_name or "main",
            )
        except (ValueError, FileNotFoundError) as exc:
            raise AutoconfPipelineError(
                f"Cannot render system configuration for {hostname} "
                f"({type(exc).__name__})"
            ) from exc
        render_hosts.append((hostname, merged_vars, host_platform))

    rendered_outputs: list[RenderedNixOutput] = []
    for hostname, merged_vars, host_platform in render_hosts:
        try:
            rendered_outputs.append(
                render_default_nix(
                    hostname,
                    merged_vars,
                    host_platform=host_platform,
                    config=config,
                    logger=logger,
                )
            )
        except (TypeError, ValueError, TemplateError) as exc:
            raise AutoconfPipelineError(
                f"Cannot render system configuration for {hostname} "
                f"({type(exc).__name__})"
            ) from exc

    rendered_outputs.extend(
        render_home_outputs(
            config,
            logger=logger,
        )
    )
    write_nix_outputs(rendered_outputs, logger=logger)
